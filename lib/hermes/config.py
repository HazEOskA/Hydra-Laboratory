"""Configuration loading for the Hermes control plane.

Configs are YAML in Git so they stay reviewable; loading is stdlib + PyYAML only
(PyYAML ships with Ubuntu's python3-yaml, which cloud-init already requires on
the runtime host, so this adds no new dependency).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def repo_root() -> Path:
    return Path(os.environ.get("HERMES_REPO_ROOT", REPO_ROOT))


def config_path(name: str) -> Path:
    return repo_root() / "config" / name


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"missing configuration file: {path}")
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"configuration must be a mapping: {path}")
    return data


def load_tools() -> dict[str, Any]:
    return load_yaml(config_path("tools.yaml"))


def load_models() -> dict[str, Any]:
    return load_yaml(config_path("models.yaml"))


def load_schedule() -> dict[str, Any]:
    return load_yaml(config_path("schedule.yaml"))


def state_dir() -> Path:
    """Runtime state lives outside Git. Never commit anything under this path."""
    return Path(os.environ.get("HERMES_WORKER_STATE_DIR", "/var/lib/hydra-hermes/worker"))


def soul_path() -> Path:
    return Path(os.environ.get("HERMES_SOUL_FILE", repo_root() / "SOUL.md"))
