"""Tests for CLI version command."""

from typer.testing import CliRunner
from evidence_agent.cli import app
from evidence_agent.version import get_version


def test_version_flag():
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "literature-evidence-agent" in result.output


def test_short_version_flag():
    runner = CliRunner()
    result = runner.invoke(app, ["-V"])
    assert result.exit_code == 0
    assert "literature-evidence-agent" in result.output


def test_version_string():
    v = get_version()
    assert "0.1" in v, f"Expected 0.1.x, got {v}"
