"""Tests for release gate script."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"


def _load_release_gate():
    spec = importlib.util.spec_from_file_location(
        "release_gate", _SCRIPTS_DIR / "release_gate.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def rg():
    return _load_release_gate()


class TestReleaseLine:
    def test_stable_version_unchanged(self, rg):
        assert rg.release_line("0.1.3") == "0.1.3"

    def test_rc_version_stripped(self, rg):
        assert rg.release_line("0.1.3rc1") == "0.1.3"

    def test_rc_multi_digit(self, rg):
        assert rg.release_line("1.2.3rc10") == "1.2.3"

    def test_no_rc_change(self, rg):
        assert rg.release_line("0.1.2") == "0.1.2"

    def test_rc_version_with_pyproject_match(self, rg):
        """RC version 0.1.3rc1 release_line equals pyproject release line 0.1.3."""
        assert rg.release_line("0.1.3rc1") == rg.release_line("0.1.3")


class TestReadPyprojectVersion:
    def test_reads_current_project_version(self, rg):
        v = rg.read_pyproject_version()
        assert "." in v
        assert v.startswith("0.1")


class TestRepoHygiene:
    def test_no_env_files_tracked(self):
        result = subprocess.run(
            ["git", "ls-files", "-z"], capture_output=True, text=True,
        )
        env_files = [
            p for p in result.stdout.split("\0")
            if p and p.endswith(".env") and p != ".env.example"
        ]
        assert len(env_files) == 0, f"Tracked .env files: {env_files}"

    def test_no_database_files_tracked(self):
        result = subprocess.run(
            ["git", "ls-files", "-z"], capture_output=True, text=True,
        )
        db_exts = (".sqlite", ".sqlite3", ".db", ".sqlite-wal", ".sqlite-shm")
        db_files = [
            p for p in result.stdout.split("\0")
            if p and p.endswith(db_exts)
        ]
        assert len(db_files) == 0, f"Tracked DB files: {db_files}"

    def test_no_private_keys_tracked(self):
        result = subprocess.run(
            ["git", "ls-files", "-z"], capture_output=True, text=True,
        )
        key_patterns = [".pem", ".key", "id_rsa", "id_ed25519", "id_ecdsa"]
        key_files = [
            p for p in result.stdout.split("\0")
            if p and any(kw in Path(p).name.lower() for kw in key_patterns)
        ]
        assert len(key_files) == 0, f"Tracked key files: {key_files}"
