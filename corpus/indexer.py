from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


TEXT_EXTS = {
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".py",
    ".js",
    ".ts",
    ".css",
    ".html",
    ".vtt",
    ".srt",
}


@dataclass
class FileEntry:
    path: str
    size: int
    lines: Optional[int] = None
    ext: Optional[str] = None


@dataclass
class Index:
    schema_version: str
    root: str
    files: List[FileEntry]
    totals: Dict[str, object]


def _is_text_ext(ext: str) -> bool:
    return ext.lower() in TEXT_EXTS


def build_index(root_dir: str, include_globs: Optional[List[str]] = None, exclude_globs: Optional[List[str]] = None) -> Index:
    from .pack import _should_include, _should_exclude  # reuse glob logic

    include_globs = include_globs or []
    exclude_globs = exclude_globs or []

    files: List[FileEntry] = []
    total_bytes = 0
    counts_by_ext: Dict[str, int] = {}

    for current, dirs, filenames in os.walk(root_dir):
        rel_root = os.path.relpath(current, root_dir)
        if rel_root == ".":
            rel_root = ""

        # prune excludes
        pruned = []
        for d in list(dirs):
            rel_d = os.path.normpath(os.path.join(rel_root, d))
            if _should_exclude(rel_d, exclude_globs):
                pruned.append(d)
        for d in pruned:
            dirs.remove(d)

        for fn in filenames:
            rel_path = os.path.normpath(os.path.join(rel_root, fn))
            abs_path = os.path.join(current, fn)
            if _should_exclude(rel_path, exclude_globs) or not _should_include(rel_path, include_globs):
                continue
            try:
                size = os.path.getsize(abs_path)
            except Exception:
                continue
            ext = os.path.splitext(rel_path)[1]
            lines = None
            if _is_text_ext(ext):
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = sum(1 for _ in f)
                except Exception:
                    lines = None
            files.append(FileEntry(path=rel_path, size=size, lines=lines, ext=ext or None))
            total_bytes += size
            key = ext.lower() or "(none)"
            counts_by_ext[key] = counts_by_ext.get(key, 0) + 1

    idx = Index(
        schema_version="1",
        root=os.path.abspath(root_dir),
        files=files,
        totals={"files": len(files), "bytes": total_bytes, "by_ext": counts_by_ext},
    )
    return idx


def write_index_json(index: Index, out_path: str) -> None:
    payload = {
        "schema_version": index.schema_version,
        "root": index.root,
        "files": [asdict(f) for f in index.files],
        "totals": index.totals,
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


