from pathlib import Path

from scripts.ship_list import ShipEntry, governed_mount_files, ship_list


def write(root: Path, *rel_paths: str) -> None:
    for rel in rel_paths:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")


def test_python_module_ships_compiled_to_mpy_at_its_repo_path(tmp_path: Path) -> None:
    write(tmp_path, "engine/timer.py")

    assert ship_list(tmp_path).modules == [
        ShipEntry(Path("engine/timer.py"), Path("engine/timer.mpy"), compiled=True)
    ]


def test_json_text_and_wav_files_ship_raw_at_their_repo_paths(tmp_path: Path) -> None:
    write(tmp_path, "packs/core/effects.json", "packs/core/notes.txt", "packs/core/zap.wav")

    assert ship_list(tmp_path).modules == [
        ShipEntry(Path("packs/core/effects.json"), Path("packs/core/effects.json"), False),
        ShipEntry(Path("packs/core/notes.txt"), Path("packs/core/notes.txt"), False),
        ShipEntry(Path("packs/core/zap.wav"), Path("packs/core/zap.wav"), False),
    ]


def test_files_with_other_suffixes_do_not_ship(tmp_path: Path) -> None:
    write(tmp_path, "effects/render.mpy", "effects/README.md", "effects/sound.mp3")

    assert ship_list(tmp_path).modules == []


def test_tests_directories_do_not_ship(tmp_path: Path) -> None:
    write(tmp_path, "engine/tests/test_timer.py", "engine/tests/effects/fixture.json")

    assert ship_list(tmp_path).modules == []


def test_pycache_directories_do_not_ship(tmp_path: Path) -> None:
    write(tmp_path, "effects/__pycache__/render.py", "effects/__pycache__/cache.txt")

    assert ship_list(tmp_path).modules == []


def test_conftest_does_not_ship(tmp_path: Path) -> None:
    write(tmp_path, "magic/conftest.py")

    assert ship_list(tmp_path).modules == []


def test_simulation_test_harness_does_not_ship(tmp_path: Path) -> None:
    write(tmp_path, "app/simulation/__init__.py", "app/simulation/harness.py")

    assert ship_list(tmp_path).modules == []


def test_simulated_device_does_not_ship(tmp_path: Path) -> None:
    write(tmp_path, "hardware/simulated/__init__.py", "hardware/simulated/parts.json")

    assert ship_list(tmp_path).modules == []


def test_package_sharing_a_name_with_an_excluded_path_still_ships(tmp_path: Path) -> None:
    write(tmp_path, "engine/simulation/__init__.py", "packs/simulated/rules.json")

    assert [entry.source for entry in ship_list(tmp_path).modules] == [
        Path("engine/simulation/__init__.py"),
        Path("packs/simulated/rules.json"),
    ]


def test_parent_package_init_of_nested_module_directories_ships_once(tmp_path: Path) -> None:
    write(tmp_path, "hardware/__init__.py", "hardware/README.md")
    write(tmp_path, "hardware/circuitpython/__init__.py", "hardware/shared/__init__.py")

    assert ship_list(tmp_path).modules == [
        ShipEntry(Path("hardware/__init__.py"), Path("hardware/__init__.mpy"), True),
        ShipEntry(
            Path("hardware/circuitpython/__init__.py"),
            Path("hardware/circuitpython/__init__.mpy"),
            True,
        ),
        ShipEntry(Path("hardware/shared/__init__.py"), Path("hardware/shared/__init__.mpy"), True),
    ]


def test_board_boot_py_ships_raw_on_the_mount_root_only(tmp_path: Path) -> None:
    write(tmp_path, "hardware/circuitpython/boot.py")

    assert ship_list(tmp_path) == (
        [],
        ShipEntry(Path("hardware/circuitpython/boot.py"), Path("boot.py"), compiled=False),
    )


def test_tree_without_a_board_boot_py_has_no_boot_entry(tmp_path: Path) -> None:
    write(tmp_path, "engine/timer.py")

    assert ship_list(tmp_path).boot is None


def test_top_level_rules_directory_does_not_ship(tmp_path: Path) -> None:
    write(tmp_path, "rules/__init__.py")

    assert ship_list(tmp_path).modules == []


def test_compiled_entry_lands_as_py_when_deployed_as_source() -> None:
    entry = ShipEntry(Path("engine/timer.py"), Path("engine/timer.mpy"), compiled=True)

    assert entry.source_device == Path("engine/timer.py")


def test_raw_entry_lands_at_its_device_path_when_deployed_as_source() -> None:
    entry = ShipEntry(Path("hardware/circuitpython/boot.py"), Path("boot.py"), compiled=False)

    assert entry.source_device == Path("boot.py")


def test_list_governs_shipped_kinds_of_file_on_the_mount_including_compiled_mpy(
    tmp_path: Path,
) -> None:
    paths = ["engine/timer.py", "engine/timer.mpy", "packs/core/effects.json", "packs/a.wav"]
    write(tmp_path, *paths)

    assert governed_mount_files(tmp_path) == sorted(Path(path) for path in paths)


def test_list_does_not_govern_excluded_paths_or_other_suffixes_on_the_mount(
    tmp_path: Path,
) -> None:
    write(
        tmp_path,
        "effects/old.pyc",
        "effects/tests/old_test.mpy",
        "effects/__pycache__/render.mpy",
        "magic/conftest.py",
        "app/simulation/harness.mpy",
        "hardware/circuitpython/boot.py",
    )

    assert governed_mount_files(tmp_path) == []


def test_list_does_not_govern_mount_files_outside_its_module_directories(tmp_path: Path) -> None:
    write(tmp_path, "code.py", "boot.py", "lib/neopixel.mpy", "hardware/__init__.mpy")

    assert governed_mount_files(tmp_path) == []


def test_list_governs_every_mpy_on_the_mount_for_a_source_deploy(tmp_path: Path) -> None:
    write(tmp_path, "effects/tests/old_test.mpy", "app/simulation/harness.mpy", "effects/old.pyc")

    assert governed_mount_files(tmp_path, use_source=True) == [
        Path("app/simulation/harness.mpy"),
        Path("effects/tests/old_test.mpy"),
    ]
