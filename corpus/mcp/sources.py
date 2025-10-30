from __future__ import annotations

import io
import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class FileHit:
    path: str
    line: int
    snippet: str
    score: int = 0


class Source:
    def list_files(self) -> List[str]:
        raise NotImplementedError

    def get_file(self, path: str, start: Optional[int] = None, end: Optional[int] = None) -> str:
        raise NotImplementedError

    def search(self, query: str, max_results: int = 50, case_sensitive: bool = False) -> List[FileHit]:
        raise NotImplementedError


class DirSource(Source):
    def __init__(self, root_dir: str, index_json: Optional[str] = None) -> None:
        self.root_dir = os.path.abspath(root_dir)
        self._files: List[str] = []
        # Try to load index.json if not provided
        idx_path = index_json or os.path.join(self.root_dir, "index.json")
        if os.path.exists(idx_path):
            try:
                with open(idx_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._files = [entry["path"] for entry in data.get("files", []) if isinstance(entry, dict) and entry.get("path")]
            except Exception:
                self._files = []
        if not self._files:
            # Fallback: walk filesystem
            for current, _, files in os.walk(self.root_dir):
                rel = os.path.relpath(current, self.root_dir)
                base = "" if rel == "." else rel
                for fn in files:
                    rel_path = os.path.normpath(os.path.join(base, fn)) if base else fn
                    self._files.append(rel_path)
        self._files.sort()

    def list_files(self) -> List[str]:
        return list(self._files)

    def get_file(self, path: str, start: Optional[int] = None, end: Optional[int] = None) -> str:
        abs_path = os.path.join(self.root_dir, path)
        with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
            if start is None and end is None:
                return f.read()
            out_lines: List[str] = []
            for i, line in enumerate(f, start=1):
                if start is not None and i < start:
                    continue
                if end is not None and i > end:
                    break
                out_lines.append(line)
            return "".join(out_lines)

    def search(self, query: str, max_results: int = 50, case_sensitive: bool = False) -> List[FileHit]:
        flags = 0 if case_sensitive else re.IGNORECASE
        # Tokenize query into words/phrases for better matching
        tokens = re.findall(r'\b\w+\b', query)
        if not tokens:
            # Fallback: use the entire query
            tokens = [query]
        # Build patterns for each token
        patterns = [re.compile(re.escape(token), flags) for token in tokens]
        results: List[FileHit] = []
        
        # Universal scoring based on file characteristics, not hard-coded paths
        def calculate_score(path: str, line_matches: int) -> int:
            score = 0
            path_lower = path.lower()
            filename = os.path.basename(path_lower)
            
            # 1. Token match density (most important)
            score += line_matches * 10
            
            # 2. Filename relevance - does filename contain query tokens?
            filename_matches = sum(1 for token in tokens if token.lower() in filename)
            score += filename_matches * 20
            
            # 3. File type priority
            if filename.endswith('.md'):
                score += 15  # Markdown/docs are usually informative
            elif filename.endswith(('.py', '.js', '.ts', '.go', '.rs', '.java', '.c', '.cpp')):
                score += 10  # Source code
            elif filename.endswith(('.json', '.yaml', '.yml', '.toml')):
                score += 5   # Config files
            
            # 4. Penalize noise files
            noise_patterns = ['changelog', 'package-lock', 'yarn.lock', 'go.sum', '.min.', 'dist/', 'build/', 'node_modules/']
            for noise in noise_patterns:
                if noise in path_lower:
                    score -= 30
                    break
            
            return max(score, 0)  # Never negative
        
        for rel in self._files:
            abs_path = os.path.join(self.root_dir, rel)
            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, start=1):
                        # Count matching tokens in this line
                        matches = sum(1 for pattern in patterns if pattern.search(line))
                        if matches > 0:
                            snippet = line.strip()
                            score = calculate_score(rel, matches)
                            results.append(FileHit(path=rel, line=i, snippet=snippet, score=score))
            except Exception:
                continue
        
        # Sort by score (highest first) and return top results
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:max_results]


class BundleSource(Source):
    """Parses a corpus-out packed text file produced by corpus pack."""

    START_RE = re.compile(r"^--- START OF FILE: (.+) ---\s*$")
    END_RE = re.compile(r"^--- END OF FILE: (.+) ---\s*$")
    START_RE_B = re.compile(br"^--- START OF FILE: (.+) ---\s*$")
    END_RE_B = re.compile(br"^--- END OF FILE: (.+) ---\s*$")

    def __init__(self, bundle_path: str) -> None:
        self.bundle_path = os.path.abspath(bundle_path)
        self._index: Dict[str, Tuple[int, int]] = {}
        self._files_only: List[str] = []
        # Build byte-offset index for random access
        self._build_index()

    def _build_index(self) -> None:
        # First, scan byte-wise to build offsets for each file between markers
        with open(self.bundle_path, "rb") as fb:
            offset = 0
            current_path: Optional[str] = None
            start_pos: Optional[int] = None
            # Optional: skip a leading index section delimited by FILE INDEX markers
            # but we don't need to special-case; we just look for START/END markers.
            for raw_line in fb:
                line_len = len(raw_line)
                m_start = self.START_RE_B.match(raw_line)
                if m_start:
                    try:
                        current_path = m_start.group(1).decode("utf-8", errors="ignore")
                    except Exception:
                        current_path = None
                    start_pos = offset + line_len  # content starts after this line
                    offset += line_len
                    continue
                m_end = self.END_RE_B.match(raw_line)
                if m_end and current_path is not None and start_pos is not None:
                    end_pos = offset  # content ends before this end line
                    self._index[current_path] = (start_pos, end_pos)
                    current_path = None
                    start_pos = None
                    offset += line_len
                    continue
                offset += line_len

        # If no file markers found, try to parse a FILE INDEX section for filenames only
        if not self._index:
            try:
                with open(self.bundle_path, "r", encoding="utf-8", errors="ignore") as f:
                    in_idx = False
                    for line in f:
                        if line.startswith("--- FILE INDEX START ---"):
                            in_idx = True
                            continue
                        if line.startswith("--- FILE INDEX END ---"):
                            break
                        if in_idx:
                            name = line.strip()
                            if name:
                                self._files_only.append(name)
            except Exception:
                pass

    def list_files(self) -> List[str]:
        if self._index:
            return sorted(self._index.keys())
        if self._files_only:
            return sorted(set(self._files_only))
        return []

    def get_file(self, path: str, start: Optional[int] = None, end: Optional[int] = None) -> str:
        if path not in self._index:
            raise FileNotFoundError(path)
        start_pos, end_pos = self._index[path]
        with open(self.bundle_path, "rb") as f:
            f.seek(start_pos)
            data = f.read(end_pos - start_pos)
        content = data.decode("utf-8", errors="ignore")
        if start is None and end is None:
            return content
        out_lines: List[str] = []
        for i, line in enumerate(io.StringIO(content), start=1):
            if start is not None and i < start:
                continue
            if end is not None and i > end:
                break
            out_lines.append(line)
        return "".join(out_lines)

    def search(self, query: str, max_results: int = 50, case_sensitive: bool = False) -> List[FileHit]:
        flags = 0 if case_sensitive else re.IGNORECASE
        # Tokenize query into words/phrases for better matching
        tokens = re.findall(r'\b\w+\b', query)
        if not tokens:
            # Fallback: use the entire query
            tokens = [query]
        # Build patterns for each token
        patterns = [re.compile(re.escape(token), flags) for token in tokens]
        results: List[FileHit] = []
        
        # Universal scoring based on file characteristics, not hard-coded paths
        def calculate_score(path: str, line_matches: int) -> int:
            score = 0
            path_lower = path.lower()
            filename = os.path.basename(path_lower)
            
            # 1. Token match density (most important)
            score += line_matches * 10
            
            # 2. Filename relevance - does filename contain query tokens?
            filename_matches = sum(1 for token in tokens if token.lower() in filename)
            score += filename_matches * 20
            
            # 3. File type priority
            if filename.endswith('.md'):
                score += 15  # Markdown/docs are usually informative
            elif filename.endswith(('.py', '.js', '.ts', '.go', '.rs', '.java', '.c', '.cpp')):
                score += 10  # Source code
            elif filename.endswith(('.json', '.yaml', '.yml', '.toml')):
                score += 5   # Config files
            
            # 4. Penalize noise files
            noise_patterns = ['changelog', 'package-lock', 'yarn.lock', 'go.sum', '.min.', 'dist/', 'build/', 'node_modules/']
            for noise in noise_patterns:
                if noise in path_lower:
                    score -= 30
                    break
            
            return max(score, 0)  # Never negative
        
        for rel in self.list_files():
            try:
                content = self.get_file(rel)
                for i, line in enumerate(io.StringIO(content), start=1):
                    # Count matching tokens in this line
                    matches = sum(1 for pattern in patterns if pattern.search(line))
                    if matches > 0:
                        snippet = line.strip()
                        score = calculate_score(rel, matches)
                        results.append(FileHit(path=rel, line=i, snippet=snippet, score=score))
            except Exception:
                continue
        
        # Sort by score (highest first) and return top results
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:max_results]


def load_source(path: str, source_type: str = "auto") -> Source:
    if source_type == "dir" or (source_type == "auto" and os.path.isdir(path)):
        return DirSource(path)
    if source_type == "bundle" or (source_type == "auto" and os.path.isfile(path)):
        # Always try bundle parsing; it can fallback to reading FILE INDEX.
        return BundleSource(path)
    raise ValueError("Invalid source path or type")


