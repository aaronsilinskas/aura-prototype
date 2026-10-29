"""Behaviour-driven tests for the shared ``device_storage`` fixture (root ``conftest.py``).

Each test runs a small suite through ``pytester`` against a copy of the real
root conftest, so a later inner test can observe what an earlier one's
teardown left behind.
"""

from pathlib import Path

ROOT_CONFTEST = Path(__file__).resolve().parents[3] / "conftest.py"


def _run_with_root_conftest(pytester, test_source: str):
    pytester.makeconftest(ROOT_CONFTEST.read_text())
    pytester.makepyfile(test_source)
    return pytester.runpytest("-p", "no:cacheprovider")


def test_device_storage_is_rooted_at_a_card_directory_inside_tmp_path(pytester):
    result = _run_with_root_conftest(
        pytester,
        """
        from pathlib import Path

        def test_root(device_storage, tmp_path):
            assert Path(device_storage.mount_root) == tmp_path / "card"
            assert Path(device_storage.mount_root).is_dir()
        """,
    )

    result.assert_outcomes(passed=1)


def test_a_card_pack_imported_during_a_test_is_evicted_after_it(pytester):
    result = _run_with_root_conftest(
        pytester,
        """
        import importlib
        import sys
        from pathlib import Path

        seen = {}

        def test_imports_a_card_pack(device_storage):
            root = Path(device_storage.mount_root)
            (root / "aura_packs" / "rules").mkdir(parents=True)
            (root / "aura_packs" / "__init__.py").touch()
            (root / "aura_packs" / "rules" / "__init__.py").touch()
            sys.path.append(device_storage.mount_root)
            importlib.import_module("aura_packs.rules")
            seen["mount_root"] = device_storage.mount_root

        def test_nothing_from_that_card_remains():
            assert not [name for name in sys.modules if name.split(".")[0] == "aura_packs"]
            assert seen["mount_root"] not in sys.path
        """,
    )

    result.assert_outcomes(passed=2)
