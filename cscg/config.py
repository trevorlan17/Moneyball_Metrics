"""Configuration loading. All CSCG knowledge lives in config/*.yaml, not in code."""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
PROJECTS_DIR = ROOT / "projects"


@functools.lru_cache(maxsize=None)
def load(name: str) -> dict[str, Any]:
    """Load a config file by stem, e.g. load('analysis_rules')."""
    path = CONFIG_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Missing config: {path}")
    with path.open() as fh:
        return yaml.safe_load(fh)


def style() -> dict[str, Any]:
    return load("presentation_style")


def rules() -> dict[str, Any]:
    return load("analysis_rules")


def charts() -> dict[str, Any]:
    return load("chart_rules")


def theme(name: str = "light") -> dict[str, str]:
    """Resolve a theme's colour tokens."""
    themes = style()["themes"]
    if name not in themes:
        raise KeyError(f"Unknown theme '{name}'. Available: {sorted(themes)}")
    return themes[name]


def resolve_colour(token: str, theme_name: str = "light") -> str:
    """Resolve a colour token ('accent') or a literal hex ('4B9CD3') to hex."""
    t = theme(theme_name)
    if token in t:
        return t[token]
    pal = style()["palette"]
    if token in pal:
        return pal[token]
    return token.lstrip("#")
