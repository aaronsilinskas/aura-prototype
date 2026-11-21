import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.build import BuildError, Toolchain, VersionError
from scripts.deploy import (
    CompiledBuild,
    DeployError,
    SourceBuild,
    execute_plan,
    main,
    plan_deploy,
)
from scripts.ship_list import MODULE_DIRS, ship_list
from scripts.tests.helpers import FakeToolchain


def make_source_tree(root: Path) -> None:
    """Create a minimal fake source tree that mirrors the real repo layout."""
    (root / "effects").mkdir()
    (root / "effects" / "render.py").write_text("# render")

    (root / "engine").mkdir()
    (root / "engine" / "timer.py").write_text("# timer")

    (root / "magic").mkdir()
    (root / "magic" / "aura.py").write_text("# aura")

    (root / "hardware").mkdir()
    (root / "hardware" / "__init__.py").write_text("")
    (root / "hardware" / "shared").mkdir()
    (root / "hardware" / "shared" / "__init__.py").write_text("")
    (root / "hardware" / "shared" / "matrix_output.py").write_text("# matrix_output")
    (root / "hardware" / "circuitpython").mkdir()


def boot_py_source(root: Path) -> Path:
    """Return the fixture path for boot.py under hardware/circuitpython/."""
    return root / "hardware" / "circuitpython" / "boot.py"


def plan_and_execute(
    example_file: Path | None,
    mount: Path,
    *,
    source_root: Path,
    toolchain: Toolchain | None = None,
    scene: str | None = None,
    dry_run: bool = False,
    use_source: bool = False,
) -> None:
    """Plan a deploy (with a passing :class:`FakeToolchain` unless given one), then execute it."""
    plan = plan_deploy(
        example_file,
        mount,
        source_root,
        toolchain=toolchain if toolchain is not None else FakeToolchain(),
        scene=scene,
        dry_run=dry_run,
        use_source=use_source,
    )
    execute_plan(plan)


def test_dry_run_plans_a_compiled_deploy_without_a_mount(tmp_path: Path) -> None:
    toolchain = FakeToolchain()

    plan = plan_deploy(None, tmp_path / "nonexistent", tmp_path, dry_run=True, toolchain=toolchain)

    assert plan.build_choice == CompiledBuild(toolchain)


def test_dry_run_plan_checks_the_toolchain_version_against_the_expected_major(
    tmp_path: Path,
) -> None:
    toolchain = FakeToolchain()

    plan_deploy(None, tmp_path / "nonexistent", tmp_path, dry_run=True, toolchain=toolchain)

    assert toolchain.checked_mounts == [None]


def test_source_plan_holds_no_toolchain(tmp_path: Path) -> None:
    plan = plan_deploy(None, tmp_path, tmp_path, toolchain=FakeToolchain(), use_source=True)

    assert plan.build_choice == SourceBuild()


def test_nonexistent_mount_raises_deploy_error(tmp_path: Path) -> None:
    mount = tmp_path / "nonexistent"

    with pytest.raises(DeployError) as raised:
        plan_deploy(None, mount, tmp_path, toolchain=FakeToolchain())

    assert str(raised.value) == f"mount path '{mount}' does not exist or is not a directory."


def test_file_instead_of_directory_as_mount_raises_deploy_error(tmp_path: Path) -> None:
    mount_file = tmp_path / "not_a_dir"
    mount_file.write_text("oops")

    with pytest.raises(DeployError) as raised:
        plan_deploy(None, mount_file, tmp_path, toolchain=FakeToolchain())

    assert str(raised.value) == f"mount path '{mount_file}' does not exist or is not a directory."


def test_read_only_mount_raises_deploy_error_telling_the_user_to_stop_code_py(
    tmp_path: Path,
) -> None:
    mount = tmp_path / "mount"
    mount.mkdir()
    mount.chmod(0o555)
    try:
        with pytest.raises(DeployError) as raised:
            plan_deploy(None, mount, tmp_path, toolchain=FakeToolchain())
    finally:
        mount.chmod(0o755)

    assert str(raised.value) == (
        "CIRCUITPY is read-only. Press Ctrl+C on the device to stop code.py first."
    )


def test_read_only_mount_copies_nothing(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    mount.chmod(0o555)
    try:
        with pytest.raises(DeployError):
            plan_and_execute(None, mount, source_root=source)
        assert not list(mount.rglob("*"))
    finally:
        mount.chmod(0o755)


def test_example_file_is_deployed_as_code_py(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    example = source / "my_demo.py"
    example.write_text("# demo")

    plan_and_execute(example, mount, source_root=source)
    assert (mount / "code.py").read_text() == "# demo"


def test_example_file_is_always_deployed_even_when_up_to_date(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    example = source / "new_demo.py"
    example.write_text("# new demo")
    existing = mount / "code.py"
    existing.write_text("# old demo")
    os.utime(existing, (example.stat().st_mtime, example.stat().st_mtime))

    plan_and_execute(example, mount, source_root=source)

    assert existing.read_text() == "# new demo"


def test_no_example_file_leaves_code_py_untouched(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    existing = mount / "code.py"
    existing.write_text("# original")

    plan_and_execute(None, mount, source_root=source)

    assert existing.read_text() == "# original"


def test_boot_py_is_deployed_alongside_code_py(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    boot_py_source(source).write_text("# boot")
    mount = tmp_path / "mount"
    mount.mkdir()
    example = source / "my_demo.py"
    example.write_text("# demo")

    plan_and_execute(example, mount, source_root=source)

    assert (mount / "boot.py").read_text() == "# boot"


def test_boot_py_is_not_deployed_when_no_example_file_given(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    boot_py_source(source).write_text("# boot")
    mount = tmp_path / "mount"
    mount.mkdir()

    plan_and_execute(None, mount, source_root=source)

    assert not (mount / "boot.py").exists()


def test_boot_py_deploy_overwrites_a_stale_copy_already_on_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    boot_source = boot_py_source(source)
    boot_source.write_text("# new boot")
    mount = tmp_path / "mount"
    mount.mkdir()
    example = source / "my_demo.py"
    example.write_text("# demo")
    existing_boot = mount / "boot.py"
    existing_boot.write_text("# old boot")
    # Same mtime as the source boot.py -- would normally look "up to date".
    os.utime(existing_boot, (boot_source.stat().st_mtime, boot_source.stat().st_mtime))

    plan_and_execute(example, mount, source_root=source)

    assert existing_boot.read_text() == "# new boot"


def test_boot_py_is_never_deleted_from_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    boot_py = mount / "boot.py"
    boot_py.write_text("# running boot")

    plan_and_execute(None, mount, source_root=source)

    assert boot_py.exists()


def test_deploying_an_example_with_no_repo_boot_py_does_not_fail(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    example = source / "my_demo.py"
    example.write_text("# demo")

    plan_and_execute(example, mount, source_root=source)
    assert (mount / "code.py").read_text() == "# demo"
    assert not (mount / "boot.py").exists()


def test_boot_py_is_not_duplicated_into_mounts_hardware_circuitpython_on_compiled_path(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    boot_py_source(source).write_text("# boot")
    mount = tmp_path / "mount"
    mount.mkdir()
    example = source / "my_demo.py"
    example.write_text("# demo")

    plan_and_execute(example, mount, source_root=source)

    assert (mount / "boot.py").read_text() == "# boot"
    assert not (mount / "hardware" / "circuitpython" / "boot.py").exists()
    assert not (mount / "hardware" / "circuitpython" / "boot.mpy").exists()


def test_boot_py_is_not_duplicated_into_mounts_hardware_circuitpython_on_raw_source_path(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    boot_py_source(source).write_text("# boot")
    mount = tmp_path / "mount"
    mount.mkdir()
    example = source / "my_demo.py"
    example.write_text("# demo")

    plan_and_execute(example, mount, source_root=source, use_source=True)

    assert (mount / "boot.py").read_text() == "# boot"
    assert not (mount / "hardware" / "circuitpython" / "boot.py").exists()
    assert not (mount / "hardware" / "circuitpython" / "boot.mpy").exists()


def test_module_directories_are_synced_to_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    plan_and_execute(None, mount, source_root=source)
    assert (mount / "effects" / "render.mpy").exists()
    assert (mount / "engine" / "timer.mpy").exists()
    assert (mount / "magic" / "aura.mpy").exists()


def test_hardware_subdirectory_modules_are_deployed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    plan_and_execute(None, mount, source_root=source)

    assert (mount / "hardware" / "__init__.mpy").exists()
    assert (mount / "hardware" / "shared" / "__init__.mpy").exists()
    assert (mount / "hardware" / "shared" / "matrix_output.mpy").exists()


def test_existing_destination_file_is_not_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    dest = mount / "effects" / "render.mpy"
    dest.write_bytes(b"DEVICE_MPY")

    plan_and_execute(None, mount, source_root=source)

    assert dest.read_bytes() == b"DEVICE_MPY"


_BASE_TIME = 1_000_000.0


def test_file_within_fat32_tolerance_is_skipped(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    # The mtime skip is compared against the staging .mpy, not the source .py.
    dest = mount / "effects" / "render.mpy"
    dest.write_bytes(b"DEVICE_MPY")
    src = source / "effects" / "render.py"
    os.utime(src, (_BASE_TIME, _BASE_TIME))
    os.utime(dest, (_BASE_TIME - 1, _BASE_TIME - 1))  # 1 s behind — within tolerance

    plan_and_execute(None, mount, source_root=source)

    assert dest.read_bytes() == b"DEVICE_MPY"


def test_file_at_fat32_boundary_is_skipped(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    dest = mount / "effects" / "render.mpy"
    dest.write_bytes(b"DEVICE_MPY")
    src = source / "effects" / "render.py"
    os.utime(src, (_BASE_TIME, _BASE_TIME))
    os.utime(dest, (_BASE_TIME - 2, _BASE_TIME - 2))  # exactly 2 s — still within tolerance

    plan_and_execute(None, mount, source_root=source)

    assert dest.read_bytes() == b"DEVICE_MPY"


def test_stale_destination_file_is_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    dest = mount / "effects" / "render.mpy"
    dest.write_bytes(b"STALE_MPY")
    src = source / "effects" / "render.py"
    os.utime(src, (_BASE_TIME, _BASE_TIME))
    os.utime(dest, (_BASE_TIME - 3, _BASE_TIME - 3))  # 3 s behind — outside tolerance

    plan_and_execute(None, mount, source_root=source)

    # FakeToolchain writes "FAKE_MPY:<name>" — the stale copy must be replaced.
    assert dest.read_text() == "FAKE_MPY:render.py"


def test_dry_run_skips_mount_existence_check(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)

    plan_and_execute(None, tmp_path / "nonexistent", source_root=source, dry_run=True)

    assert "[DRY RUN] COPY  engine/timer.mpy" in capsys.readouterr().out


def test_dry_run_writes_no_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    plan_and_execute(None, mount, source_root=source, dry_run=True)

    assert list(mount.rglob("*")) == []


def test_dry_run_output_shows_dry_run_prefix_for_copies(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    plan_and_execute(None, mount, source_root=source, dry_run=True)

    captured = capsys.readouterr()
    assert "[DRY RUN] COPY" in captured.out


def test_stale_py_file_is_deleted_from_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    stale = mount / "effects" / "old_module.py"
    stale.write_text("# stale")

    plan_and_execute(None, mount, source_root=source)

    assert not stale.exists()


def test_live_mpy_file_is_not_deleted_from_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    existing = mount / "effects" / "render.mpy"
    existing.write_bytes(b"DEVICE_MPY")

    plan_and_execute(None, mount, source_root=source)

    assert existing.exists()


def test_stale_excluded_suffix_file_on_mount_is_not_pruned(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    stale_pyc = mount / "effects" / "old_module.pyc"
    stale_pyc.write_text("")

    plan_and_execute(None, mount, source_root=source)

    assert stale_pyc.exists()


def test_stale_wav_file_is_deleted_from_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    (source / "effects" / "sounds").mkdir()
    (source / "effects" / "sounds" / "active.wav").write_bytes(b"")
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects" / "sounds").mkdir(parents=True)
    stale_wav = mount / "effects" / "sounds" / "old_sound.wav"
    stale_wav.write_bytes(b"")

    plan_and_execute(None, mount, source_root=source)

    assert not stale_wav.exists()


def test_code_py_is_never_deleted_from_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    code_py = mount / "code.py"
    code_py.write_text("# running example")

    plan_and_execute(None, mount, source_root=source)

    assert code_py.exists()


def test_files_outside_module_dirs_are_not_deleted(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    lib = mount / "lib"
    lib.mkdir()
    lib_file = lib / "neopixel.py"
    lib_file.write_text("# neopixel")
    settings = mount / "settings.toml"
    settings.write_text("[wifi]")

    plan_and_execute(None, mount, source_root=source)

    assert lib_file.exists()
    assert settings.exists()


def test_excluded_path_files_on_mount_are_not_pruned(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects" / "tests").mkdir(parents=True)
    legacy_test = mount / "effects" / "tests" / "old_test.py"
    legacy_test.write_text("# legacy test")

    plan_and_execute(None, mount, source_root=source)

    assert legacy_test.exists()


def test_empty_subdirectory_is_removed_after_pruning(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects" / "steps").mkdir(parents=True)
    stale = mount / "effects" / "steps" / "old_step.py"
    stale.write_text("# stale step")

    plan_and_execute(None, mount, source_root=source)

    assert not stale.exists()
    assert not (mount / "effects" / "steps").exists()


def test_empty_subdirectory_already_on_mount_is_removed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    (mount / "effects" / "steps").mkdir(parents=True)

    plan_and_execute(None, mount, source_root=source)

    assert not (mount / "effects" / "steps").exists()


def test_module_root_removed_when_fully_pruned(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "engine").mkdir()
    (source / "engine" / "timer.py").write_text("# timer")
    (source / "magic").mkdir()
    (source / "magic" / "aura.py").write_text("# aura")
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    stale = mount / "effects" / "render.py"
    stale.write_text("# stale render")

    plan_and_execute(None, mount, source_root=source)

    assert not stale.exists()
    assert not (mount / "effects").exists()


def test_non_empty_directory_is_not_removed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects" / "steps").mkdir(parents=True)
    stale = mount / "effects" / "steps" / "old_step.py"
    stale.write_text("# stale")

    plan_and_execute(None, mount, source_root=source)

    assert (mount / "effects").exists()


def test_first_time_deploy_with_no_module_dirs_on_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    plan_and_execute(None, mount, source_root=source)

    assert (mount / "engine" / "timer.mpy").read_text() == "FAKE_MPY:timer.py"


def test_dry_run_does_not_delete_stale_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    stale = mount / "effects" / "old_module.py"
    stale.write_text("# stale")

    plan_and_execute(None, mount, source_root=source, dry_run=True)

    assert stale.exists()


def test_dry_run_prune_output_shows_dry_run_prefix(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    (mount / "effects" / "old_module.py").write_text("# stale")

    plan_and_execute(None, mount, source_root=source, dry_run=True)

    captured = capsys.readouterr()
    assert "[DRY RUN] PRUNE" in captured.out


def test_summary_includes_pruned_count(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    (mount / "effects" / "old_a.py").write_text("# stale")
    (mount / "effects" / "old_b.py").write_text("# stale")

    plan_and_execute(None, mount, source_root=source)

    captured = capsys.readouterr()
    assert "2 pruned" in captured.out


def test_scene_flag_sets_default_scene_in_existing_boot_file(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "aura-boot.json").write_text(json.dumps({"default_scene": "tag"}))

    plan_and_execute(None, mount, source_root=source, scene="red_light_green_light")

    result = json.loads((mount / "aura-boot.json").read_text())
    assert result["default_scene"] == "red_light_green_light"


def test_scene_flag_preserves_other_boot_values_when_scene_is_set(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    existing_boot_values = {"default_scene": "tag", "brightness": 0.8}
    (mount / "aura-boot.json").write_text(json.dumps(existing_boot_values))

    plan_and_execute(None, mount, source_root=source, scene="hardware_test")

    result = json.loads((mount / "aura-boot.json").read_text())
    assert result["brightness"] == 0.8


def test_scene_flag_creates_boot_file_fresh_when_absent(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    plan_and_execute(None, mount, source_root=source, scene="hardware_test")

    result = json.loads((mount / "aura-boot.json").read_text())
    assert result["default_scene"] == "hardware_test"


def test_scene_flag_writes_a_scene_deploy_token_beside_default_scene(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    plan_and_execute(None, mount, source_root=source, scene="hardware_test")

    boot_values = json.loads((mount / "aura-boot.json").read_text())
    assert boot_values["default_scene"] == "hardware_test"
    assert boot_values["scene_deploy_token"]


def test_scene_flag_leaves_an_old_aura_settings_json_untouched(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    original_content = json.dumps({"default_scene": "tag"})
    old_path = mount / "aura-settings.json"
    old_path.write_text(original_content)

    plan_and_execute(None, mount, source_root=source, scene="hardware_test")

    assert old_path.read_text() == original_content


def test_each_scene_flag_deploy_writes_a_new_scene_deploy_token(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    boot_path = mount / "aura-boot.json"

    plan_and_execute(None, mount, source_root=source, scene="tag")
    first = json.loads(boot_path.read_text())["scene_deploy_token"]
    plan_and_execute(None, mount, source_root=source, scene="tag")
    second = json.loads(boot_path.read_text())["scene_deploy_token"]

    assert first != second


def test_scene_flag_does_not_write_scene_key_into_device_config(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    existing_config = {
        "pixels": [{"type": "matrix", "cols": 13, "scope_rows": {"personal": [0, 1]}}],
        "buttons": ["D9"],
    }
    original_content = json.dumps(existing_config)
    device_config_path = mount / "aura-device.json"
    device_config_path.write_text(original_content)

    plan_and_execute(None, mount, source_root=source, scene="tag")

    assert device_config_path.read_text() == original_content


def test_omitting_scene_flag_leaves_existing_boot_file_untouched(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    original_content = json.dumps({"default_scene": "tag", "scene_deploy_token": "a1b2"})
    boot_path = mount / "aura-boot.json"
    boot_path.write_text(original_content)

    plan_and_execute(None, mount, source_root=source)

    assert boot_path.read_text() == original_content


def test_scene_flag_with_dry_run_leaves_boot_file_untouched(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    original_content = json.dumps({"default_scene": "tag"})
    boot_path = mount / "aura-boot.json"
    boot_path.write_text(original_content)

    plan_and_execute(
        None,
        mount,
        source_root=source,
        scene="hardware_test",
        dry_run=True,
    )

    assert boot_path.read_text() == original_content


def test_scene_flag_with_dry_run_creates_no_boot_file_when_absent(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    plan_and_execute(
        None,
        mount,
        source_root=source,
        scene="hardware_test",
        dry_run=True,
    )

    assert not (mount / "aura-boot.json").exists()


def test_deploy_ships_mpy_not_py_for_compiled_modules(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    plan_and_execute(None, mount, source_root=source)

    assert (mount / "effects" / "render.mpy").exists()
    assert not (mount / "effects" / "render.py").exists()


def test_deploy_ships_data_files_raw(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    (source / "packs").mkdir()
    (source / "packs" / "data.json").write_text('{"key": "value"}')
    (source / "packs" / "sounds").mkdir()
    (source / "packs" / "sounds" / "click.wav").write_bytes(b"RIFF")
    mount = tmp_path / "mount"
    mount.mkdir()

    plan_and_execute(None, mount, source_root=source)

    assert (mount / "packs" / "data.json").read_text() == '{"key": "value"}'
    assert (mount / "packs" / "sounds" / "click.wav").read_bytes() == b"RIFF"


def test_deploy_summary_includes_compiled_count(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    plan_and_execute(None, mount, source_root=source)

    captured = capsys.readouterr()
    assert "compiled" in captured.out


def test_deploy_compile_failure_raises_deploy_error_caused_by_the_build_error(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    with pytest.raises(DeployError) as raised:
        plan_and_execute(
            None, mount, source_root=source, toolchain=FakeToolchain(failing_compiles=1)
        )

    assert isinstance(raised.value.__cause__, BuildError)


def test_deploy_compile_failure_leaves_mount_untouched(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    with pytest.raises(DeployError):
        plan_and_execute(
            None, mount, source_root=source, toolchain=FakeToolchain(failing_compiles=1)
        )

    assert list(mount.rglob("*")) == []


def test_deploy_compile_failure_error_names_the_file_and_toolchain_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    toolchain = FakeToolchain(failing_compiles=1)

    with pytest.raises(DeployError) as raised:
        plan_and_execute(None, mount, source_root=source, toolchain=toolchain)

    assert str(raised.value) == f"mpy-cross failed on {toolchain.failed[0]}: SyntaxError: oops"


def test_deploy_failure_prints_no_error_line_itself(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    with pytest.raises(DeployError):
        plan_and_execute(
            None, mount, source_root=source, toolchain=FakeToolchain(failing_compiles=1)
        )

    assert capsys.readouterr().err == ""


def test_version_mismatch_with_device_mounted_raises_deploy_error_caused_by_the_version_error(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    with pytest.raises(DeployError) as raised:
        plan_and_execute(
            None, mount, source_root=source, toolchain=FakeToolchain(version_mismatch=True)
        )

    assert isinstance(raised.value.__cause__, VersionError)


def test_version_mismatch_with_device_mounted_error_carries_the_toolchain_message(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    with pytest.raises(DeployError) as raised:
        plan_and_execute(
            None, mount, source_root=source, toolchain=FakeToolchain(version_mismatch=True)
        )

    assert str(raised.value) == "mpy-cross major version 9 does not match CircuitPython 10.x"


def test_version_mismatch_with_device_mounted_writes_nothing_to_the_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    with pytest.raises(DeployError):
        plan_and_execute(
            None,
            mount,
            source_root=source,
            toolchain=FakeToolchain(version_mismatch=True),
            scene="hardware_test",
        )

    assert list(mount.rglob("*")) == []


def test_matching_toolchain_version_deploys_compiled_modules(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    plan_and_execute(None, mount, source_root=source)
    assert (mount / "effects" / "render.mpy").read_text() == "FAKE_MPY:render.py"


def test_version_mismatch_compiles_nothing(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    toolchain = FakeToolchain(version_mismatch=True)

    with pytest.raises(DeployError):
        plan_and_execute(None, mount, source_root=source, toolchain=toolchain)

    assert toolchain.compiled == []


def test_compiled_deploy_checks_the_toolchain_version_against_the_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    toolchain = FakeToolchain()

    plan_and_execute(None, mount, source_root=source, toolchain=toolchain)

    assert toolchain.checked_mounts == [mount]


def test_dry_run_version_mismatch_raises_deploy_error(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)

    with pytest.raises(DeployError):
        plan_and_execute(
            None,
            tmp_path / "nonexistent",
            source_root=source,
            toolchain=FakeToolchain(version_mismatch=True),
            dry_run=True,
        )


def test_source_mode_ships_raw_py_files_not_compiled_mpy(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    plan_and_execute(None, mount, source_root=source, use_source=True)

    assert (mount / "effects" / "render.py").exists()
    assert not (mount / "effects" / "render.mpy").exists()


def test_source_mode_prunes_orphaned_mpy_left_by_previous_compiled_deploy(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    orphaned_mpy = mount / "effects" / "render.mpy"
    orphaned_mpy.write_bytes(b"OLD_MPY")

    plan_and_execute(None, mount, source_root=source, use_source=True)

    assert not orphaned_mpy.exists()


def test_source_mode_prunes_every_mpy_under_a_module_directory(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    (mount / "effects" / "tests").mkdir(parents=True)
    orphaned_mpy = mount / "effects" / "tests" / "old_test.mpy"
    orphaned_mpy.write_bytes(b"OLD_MPY")

    plan_and_execute(None, mount, source_root=source, use_source=True)

    assert not orphaned_mpy.exists()


def test_compiled_mode_prunes_orphaned_py_left_by_previous_source_deploy(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    orphaned_py = mount / "effects" / "render.py"
    orphaned_py.write_bytes(b"OLD_PY")

    plan_and_execute(None, mount, source_root=source)

    assert not orphaned_py.exists()


def test_source_mode_deploys_intermediate_init_py_for_nested_packages(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    plan_and_execute(None, mount, source_root=source, use_source=True)

    assert (mount / "hardware" / "__init__.py").exists()


def test_source_mode_summary_reports_zero_compiled(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    plan_and_execute(None, mount, source_root=source, use_source=True)

    captured = capsys.readouterr()
    assert "0 compiled" in captured.out


@pytest.mark.parametrize("dry_run", [False, True], ids=["live", "dry_run"])
def test_source_mode_never_calls_the_toolchain(tmp_path: Path, dry_run: bool) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    toolchain = FakeToolchain(version_mismatch=True)

    plan_and_execute(
        None, mount, source_root=source, toolchain=toolchain, use_source=True, dry_run=dry_run
    )
    assert toolchain.checked_mounts == []
    assert toolchain.compiled == []


_REPO_ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize("use_source", [False, True], ids=["compiled", "source"])
def test_real_repo_tree_lands_exactly_the_ship_list_and_code_py_on_the_mount(
    tmp_path: Path, use_source: bool
) -> None:
    source = tmp_path / "source"
    for top in {Path(module).parts[0] for module in MODULE_DIRS}:
        shutil.copytree(_REPO_ROOT / top, source / top, ignore=shutil.ignore_patterns("*.pyc"))
    mount = tmp_path / "mount"
    mount.mkdir()
    example = tmp_path / "example.py"
    example.write_text("# demo")

    plan_and_execute(example, mount, source_root=source, use_source=use_source)

    landed = {path.relative_to(mount) for path in mount.rglob("*") if path.is_file()}
    shipped = ship_list(source)
    entries = [*shipped.modules, shipped.boot]
    listed = {
        entry.source_device if use_source else entry.device
        for entry in entries
        if entry is not None
    }
    hardware_init = Path("hardware/__init__.py" if use_source else "hardware/__init__.mpy")
    assert {Path("code.py"), Path("boot.py"), hardware_init} <= landed
    assert landed == listed | {Path("code.py")}


def test_main_exits_1_with_the_error_line_when_the_mount_is_missing(tmp_path: Path, capsys) -> None:
    mount = tmp_path / "nonexistent"

    with pytest.raises(SystemExit) as exited:
        main(["--mount", str(mount)])

    assert exited.value.code == 1
    assert capsys.readouterr().err == (
        f"Error: mount path '{mount}' does not exist or is not a directory.\n"
    )


def test_main_exits_1_with_the_error_line_when_the_mount_is_read_only(
    tmp_path: Path, capsys
) -> None:
    mount = tmp_path / "mount"
    mount.mkdir()
    mount.chmod(0o555)
    try:
        with pytest.raises(SystemExit) as exited:
            main(["--mount", str(mount)])
    finally:
        mount.chmod(0o755)

    assert exited.value.code == 1
    assert capsys.readouterr().err == (
        "Error: CIRCUITPY is read-only. Press Ctrl+C on the device to stop code.py first.\n"
    )


def test_main_deploys_source_modules_to_the_mount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    monkeypatch.chdir(source)

    main(["--mount", str(mount), "--source"])

    assert (mount / "engine" / "timer.py").exists()


def test_deploy_runs_as_a_script_file_outside_the_repo_root(tmp_path: Path) -> None:
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}

    result = subprocess.run(
        [sys.executable, str(_REPO_ROOT / "scripts" / "deploy.py"), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
