from __future__ import annotations

import datetime as _dt
import os
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import yaml


def _default_home() -> str:
    root = os.environ.get("CORPUS_HOME")
    if root:
        return os.path.abspath(root)
    # fallback to ~/.local/share/corpus (works cross-platform reasonably)
    return os.path.join(os.path.expanduser("~"), ".local", "share", "corpus")


@dataclass
class Collection:
    id: str
    name: Optional[str]
    source: str
    type: str = "auto"  # auto|bundle|dir
    tags: Optional[List[str]] = None
    added_at: Optional[str] = None


@dataclass
class Catalog:
    version: int
    collections: List[Collection]


def load_catalog(home: Optional[str] = None) -> Catalog:
    home = home or _default_home()
    os.makedirs(home, exist_ok=True)
    path = os.path.join(home, "catalog.yaml")
    if not os.path.exists(path):
        return Catalog(version=1, collections=[])
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    cols = [Collection(**c) for c in data.get("collections", [])]
    return Catalog(version=int(data.get("version", 1)), collections=cols)


def save_catalog(cat: Catalog, home: Optional[str] = None) -> str:
    home = home or _default_home()
    os.makedirs(home, exist_ok=True)
    path = os.path.join(home, "catalog.yaml")
    payload = {
        "version": cat.version,
        "collections": [asdict(c) for c in cat.collections],
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False)
    return path


def add_collection(col_id: str, source: str, name: Optional[str] = None, type: str = "auto", tags: Optional[List[str]] = None, home: Optional[str] = None) -> str:
    cat = load_catalog(home)
    # Remove existing collection if it exists (replace behavior)
    cat.collections = [c for c in cat.collections if c.id != col_id]
    col = Collection(
        id=col_id,
        name=name,
        source=os.path.abspath(source),
        type=type,
        tags=tags or [],
        added_at=_dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    )
    cat.collections.append(col)
    return save_catalog(cat, home)


def remove_collection(col_id: str, home: Optional[str] = None) -> str:
    cat = load_catalog(home)
    cat.collections = [c for c in cat.collections if c.id != col_id]
    return save_catalog(cat, home)


