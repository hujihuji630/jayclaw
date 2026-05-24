"""Standard directory paths for jayclaw runtime files."""

from pathlib import Path

# Directory name used for all jayclaw-generated files
DIR_NAME = ".jayclaw"


def project_dir(workspace: Path) -> Path:
    """Return the .jayclaw directory inside a workspace."""
    return workspace / DIR_NAME


def global_dir() -> Path:
    """Return the global ~/.jayclaw directory."""
    return Path.home() / DIR_NAME
