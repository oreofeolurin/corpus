from __future__ import annotations

import base64
import gzip
import io
import json
import os
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import yaml


@dataclass
class PackConfig:
    input_dir: str = "."
    output_file: str = "corpus-out.txt"
    include_globs: List[str] = None  # type: ignore[assignment]
    exclude_globs: List[str] = None  # type: ignore[assignment]
    verbose: bool = False
    compress: bool = False
    max_compress: bool = False
    gzip_out: bool = False
    base64_out: bool = False
    # Indexing options
    write_index: bool = False
    index_only: bool = False
    index_style: str = "flat"  # flat|tree|json
    index_output: Optional[str] = None
    index_include: List[str] = None  # e.g., ["size","lines","hash"]
    index_depth: Optional[int] = None


def _fields(obj) -> List[str]:
    return [f.name for f in obj.__dataclass_fields__.values()]  # type: ignore[attr-defined]


def apply_defaults(cfg: PackConfig) -> PackConfig:
    if cfg.include_globs is None or cfg.include_globs == []:
        cfg.include_globs = []
    
    # Default excludes
    default_excludes = ["**/.git/**", "**/node_modules/**", "**/venv/**", "**/__pycache__/**", "**/bin/**"]
    
    if cfg.exclude_globs is None or cfg.exclude_globs == []:
        # No user excludes, use defaults
        cfg.exclude_globs = default_excludes.copy()
    else:
        # User provided excludes, merge with defaults
        cfg.exclude_globs = default_excludes + cfg.exclude_globs
    if cfg.base64_out and not cfg.gzip_out:
        raise ValueError("--base64 requires --gzip")
    if cfg.index_include is None:
        cfg.index_include = []
    if cfg.index_style not in {"flat", "tree", "json"}:
        cfg.index_style = "flat"
    return cfg


def load_config_file(path: str) -> PackConfig:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    data = yaml.safe_load(text) if path.endswith((".yaml", ".yml")) else json.loads(text)
    cfg = PackConfig(**data)
    return apply_defaults(cfg)


def try_load_default(path: str) -> Optional[PackConfig]:
    for name in ("cpack.yml", "cpack.yaml", "cpack.json"):
        p = os.path.join(path, name)
        if os.path.exists(p):
            return load_config_file(p)
    return None


def _match_glob(pattern: str, path: str) -> bool:
    # Convert glob to regex supporting **
    pattern = os.path.normpath(pattern)
    path = os.path.normpath(path)
    pattern_ext = os.path.splitext(pattern)[1]
    path_ext = os.path.splitext(path)[1]
    if pattern_ext and path_ext:
        pattern = pattern[: -len(pattern_ext)] + pattern_ext.lower()
        path = path[: -len(path_ext)] + path_ext.lower()
    regex = re.escape(pattern)
    regex = regex.replace(r"\*\*/", r"(?:.*/)?").replace(r"/\*\*/", r"/(?:.*/)?").replace(r"\*\*", ".*")
    regex = regex.replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
    regex = "^" + regex + "$"
    return re.compile(regex).match(path) is not None


def _should_exclude(rel_path: str, exclude: List[str]) -> bool:
    for pat in exclude:
        target = os.path.basename(rel_path) if "/" not in pat and "\\" not in pat else rel_path
        if _match_glob(pat, target):
            return True
    return False


def _should_include(rel_path: str, include: List[str]) -> bool:
    if not include:
        return True
    for pat in include:
        target = os.path.basename(rel_path) if "/" not in pat and "\\" not in pat else rel_path
        if _match_glob(pat, target):
            return True
    return False


def _compress_text(text: str, aggressive: bool = False) -> str:
    if aggressive:
        # strip //... and /* ... */
        text = re.sub(r"//.*", "", text)
        text = re.sub(r"(?s)/\*.*?\*/", "", text)
    text = " ".join(re.sub("\n", " ", text).split())
    symbols = [".", ",", ":", ";", ")", "(", "{", "}", "[", "]", "+", "-", "*", "/", "=", "<", ">", "&", "|", "!", "?"]
    for sym in symbols:
        text = text.replace(f" {sym} ", sym).replace(f" {sym}", sym).replace(f"{sym} ", sym)
    return text


def _build_index_flat(files: List[Tuple[str, Dict[str, int]]], include: List[str]) -> str:
    lines: List[str] = []
    for rel, meta in files:
        parts = [rel]
        if "size" in include and "size" in meta:
            parts.append(f"size={meta['size']}")
        if "lines" in include and "lines" in meta:
            parts.append(f"lines={meta['lines']}")
        lines.append(" \t".join(parts))
    return "\n".join(lines) + "\n"


def _build_index_tree(files: List[Tuple[str, Dict[str, int]]], include: List[str], depth: Optional[int]) -> str:
    # Build directory tree
    tree: Dict[str, Dict] = {}
    for rel, meta in files:
        parts = rel.split("/")
        cursor = tree
        for i, part in enumerate(parts):
            is_leaf = i == len(parts) - 1
            if part not in cursor:
                cursor[part] = {}
            if is_leaf:
                cursor[part]["__file__"] = meta
            else:
                cursor = cursor[part]

    def render(node: Dict, prefix: str = "", level: int = 0) -> List[str]:
        if depth is not None and level >= depth:
            return []
        lines: List[str] = []
        # directories first, then files
        keys = sorted(k for k in node.keys() if k != "__file__")
        for k in keys:
            child = node[k]
            if isinstance(child, dict) and "__file__" not in child:
                lines.append(f"{prefix}{k}/")
                lines.extend(render(child, prefix + "  ", level + 1))
            else:
                meta = child.get("__file__", {})
                parts = [f"{prefix}{k}"]
                if "size" in include and "size" in meta:
                    parts.append(f"size={meta['size']}")
                if "lines" in include and "lines" in meta:
                    parts.append(f"lines={meta['lines']}")
                lines.append(" \t".join(parts))
        # files directly under current directory (if any)
        if "__file__" in node:
            meta = node["__file__"]
            parts = [f"{prefix}"]
            if "size" in include and "size" in meta:
                parts.append(f"size={meta['size']}")
            if "lines" in include and "lines" in meta:
                parts.append(f"lines={meta['lines']}")
            if parts and parts[0].strip():
                lines.append(" \t".join(parts))
        return lines

    return "\n".join(render(tree)) + "\n"


def _build_index_json(files: List[Tuple[str, Dict[str, int]]], root_dir: str) -> str:
    import json as _json

    totals = {"files": len(files), "bytes": sum(m.get("size", 0) for _, m in files)}
    by_ext: Dict[str, int] = {}
    for rel, _ in files:
        ext = os.path.splitext(rel)[1].lower() or "(none)"
        by_ext[ext] = by_ext.get(ext, 0) + 1
    payload = {
        "schema_version": "1",
        "root": os.path.abspath(root_dir),
        "files": [{"path": rel, **meta} for rel, meta in files],
        "totals": {**totals, "by_ext": by_ext},
    }
    return _json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def pack_directory(cfg: PackConfig) -> Tuple[str, Dict[str, int]]:
    cfg = apply_defaults(cfg)
    input_dir = os.path.abspath(cfg.input_dir)
    output_file = os.path.abspath(cfg.output_file)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    buf = io.StringIO()
    processed: List[str] = []
    skipped: List[str] = []
    index_files: List[Tuple[str, Dict[str, int]]] = []

    for root, dirs, files in os.walk(input_dir):
        rel_root = os.path.relpath(root, input_dir)
        if rel_root == ".":
            rel_root = ""
        # prune excluded dirs
        pruned = []
        for d in list(dirs):
            rel_d = os.path.normpath(os.path.join(rel_root, d))
            if _should_exclude(rel_d, cfg.exclude_globs):
                pruned.append(d)
        for d in pruned:
            dirs.remove(d)

        for fn in files:
            rel_path = os.path.normpath(os.path.join(rel_root, fn))
            abs_path = os.path.join(root, fn)
            if _should_exclude(rel_path, cfg.exclude_globs) or not _should_include(rel_path, cfg.include_globs):
                skipped.append(rel_path)
                continue
            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                skipped.append(rel_path)
                continue
            # Collect index metadata
            meta: Dict[str, int] = {}
            if cfg.write_index or cfg.index_only or cfg.index_output:
                try:
                    meta["size"] = os.path.getsize(abs_path)
                except Exception:
                    pass
                try:
                    meta["lines"] = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
                except Exception:
                    pass
                try:
                    meta["ext"] = os.path.splitext(rel_path)[1] or None
                except Exception:
                    pass
                index_files.append((rel_path, meta))
            if cfg.compress:
                content = _compress_text(content, aggressive=cfg.max_compress)
                start_sep = f"--- START OF FILE: {rel_path} --- "
                end_sep = f" --- END OF FILE: {rel_path} --- "
            else:
                start_sep = f"--- START OF FILE: {rel_path} ---\n"
                end_sep = f"\n--- END OF FILE: {rel_path} ---\n\n"
            if cfg.index_only:
                # Skip writing file contents
                pass
            elif cfg.verbose:
                buf.write(start_sep)
                buf.write(content)
                buf.write(end_sep)
            else:
                buf.write(start_sep)
                buf.write(content)
                buf.write(end_sep)
            processed.append(rel_path)

    # Prepend or separate index if requested
    index_text = ""
    if cfg.write_index or cfg.index_only or cfg.index_output:
        # Sort index files
        index_files.sort(key=lambda x: x[0])
        if cfg.index_style == "json":
            index_text = _build_index_json(index_files, cfg.input_dir)
        elif cfg.index_style == "tree":
            index_text = _build_index_tree(index_files, cfg.index_include, cfg.index_depth)
        else:
            index_text = _build_index_flat(index_files, cfg.index_include)

        # Separate file if requested
        if cfg.index_output:
            os.makedirs(os.path.dirname(os.path.abspath(cfg.index_output) or "."), exist_ok=True)
            with open(cfg.index_output, "w", encoding="utf-8") as f:
                f.write(index_text)

    data = buf.getvalue()
    if cfg.index_only:
        data = ""
    elif index_text and not cfg.index_output:
        data = "--- FILE INDEX START ---\n" + index_text + "--- FILE INDEX END ---\n\n" + data
    raw_bytes = data.encode("utf-8")
    out_bytes = raw_bytes
    if cfg.gzip_out:
        gz_buf = io.BytesIO()
        with gzip.GzipFile(fileobj=gz_buf, mode="wb") as gz:
            gz.write(raw_bytes)
        out_bytes = gz_buf.getvalue()
    if cfg.base64_out:
        out_bytes = base64.b64encode(out_bytes)

    with open(output_file, "wb") as f:
        f.write(out_bytes)

    # Calculate stats
    bundle_size = len(out_bytes)
    total_files = len(processed)
    skipped_files = len(skipped)
    total_bytes = sum(meta.get("size", 0) for _, meta in index_files)
    
    stats = {
        "bundle_size": bundle_size,
        "files_processed": total_files,
        "files_skipped": skipped_files,
        "total_bytes": total_bytes,
        "compression_ratio": round(bundle_size / total_bytes, 2) if total_bytes > 0 else 0,
    }
    
    return output_file, stats


