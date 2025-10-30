from __future__ import annotations

import os
import re
import shutil
import tarfile
import tempfile
import urllib.parse
import urllib.request
from typing import Optional, Tuple


def _get_env_token() -> Optional[str]:
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


def parse_github_url(repo_url: str, explicit_ref: Optional[str] = None) -> Tuple[str, str, Optional[str], Optional[str]]:
    """Parse GitHub URL into (owner, repo, ref, subdir).

    Supports:
    - https://github.com/owner/repo
    - https://github.com/owner/repo/sub/dir  (treat extra as subdir)
    - https://github.com/owner/repo/tree/<ref>
    - https://github.com/owner/repo/tree/<ref>/sub/dir
    """
    u = urllib.parse.urlparse(repo_url)
    if u.netloc.lower() != "github.com":
        raise ValueError("Only github.com URLs are supported")
    parts = [p for p in u.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError("Invalid GitHub URL: expected /owner/repo")
    owner, repo = parts[0], parts[1]
    ref: Optional[str] = None
    subdir: Optional[str] = None

    rest = parts[2:]
    if rest:
        if rest[0] == "tree":
            if len(rest) >= 2:
                ref = rest[1]
                subdir = "/".join(rest[2:]) if len(rest) > 2 else None
        else:
            # Treat additional segments as subdir
            subdir = "/".join(rest)

    if explicit_ref:
        ref = explicit_ref
    return owner, repo, ref, subdir


def _download_tarball(owner: str, repo: str, ref: Optional[str], token: Optional[str]) -> str:
    base = f"https://api.github.com/repos/{owner}/{repo}/tarball"
    url = f"{base}/{ref}" if ref else base
    req = urllib.request.Request(url)
    # Headers to avoid some rate limiting and content negotiation issues
    req.add_header("User-Agent", "corpus-packer/0.1")
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    tmpdir = tempfile.mkdtemp(prefix="corpus_repo_")
    tar_path = os.path.join(tmpdir, "repo.tar.gz")
    with urllib.request.urlopen(req) as resp, open(tar_path, "wb") as out:
        shutil.copyfileobj(resp, out)
    # Extract
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(tmpdir)
    # Find top-level extracted directory
    entries = [os.path.join(tmpdir, d) for d in os.listdir(tmpdir)]
    dirs = [d for d in entries if os.path.isdir(d)]
    if not dirs:
        raise RuntimeError("Failed to extract repository tarball")
    # Usually single top dir
    top = sorted(dirs)[0]
    return top


def _clone_git(url: str, ref: Optional[str]) -> str:
    if shutil.which("git") is None:
        raise RuntimeError("git not found on PATH (required when tarball fallback fails)")
    tmpdir = tempfile.mkdtemp(prefix="corpus_repo_")
    dest = os.path.join(tmpdir, "repo")
    cmd = ["git", "clone", "--depth", "1"]
    if ref:
        cmd += ["--branch", ref]
    cmd += [url, dest]
    rc = os.spawnvp(os.P_WAIT, cmd[0], cmd)
    if rc != 0:
        raise RuntimeError("git clone failed")
    return dest


def fetch_repo_checkout(repo_url: str, ref: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """Download or clone repo and return (checkout_path, detected_subdir_from_url).

    The returned path is the root of the repository (or extracted tarball top directory).
    The second value is an optional subdir parsed from the URL.
    """
    owner, repo, parsed_ref, subdir = parse_github_url(repo_url, explicit_ref=ref)
    token = _get_env_token()
    try:
        root = _download_tarball(owner, repo, parsed_ref, token)
    except Exception:
        # Fallback to git clone
        root = _clone_git(f"https://github.com/{owner}/{repo}.git", parsed_ref)
    return root, subdir


