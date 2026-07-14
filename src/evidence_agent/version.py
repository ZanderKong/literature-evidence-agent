"""Version string — single source of truth from pyproject.toml."""

from importlib.metadata import PackageNotFoundError, version


def get_version() -> str:
    try:
        return version("literature-evidence-agent")
    except PackageNotFoundError:
        return "0.1.1.dev0"
