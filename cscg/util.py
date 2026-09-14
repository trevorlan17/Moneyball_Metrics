"""Small shared helpers."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def run_id(seed: str = "") -> str:
    """Timestamped run identifier, stable within a second."""
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    if seed:
        stamp += "-" + hashlib.sha1(seed.encode()).hexdigest()[:6]
    return stamp


def file_digest(path: Path) -> str:
    """SHA-256 of a file, so we can prove which raw file an analysis came from."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def write_json(path: Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        json.dump(data, fh, indent=2, default=str)
        fh.write("\n")


def read_json(path: Path) -> Any:
    with Path(path).open() as fh:
        return json.load(fh)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return s or "x"


def pct(x: float, digits: int = 0) -> str:
    """Format a proportion as a percentage string the way CSCG writes it."""
    return f"{x * 100:.{digits}f}%"
