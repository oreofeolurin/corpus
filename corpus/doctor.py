from __future__ import annotations

import shutil
import subprocess
from typing import Dict, Tuple


def _check_cmd(cmd: str) -> Tuple[bool, str]:
    path = shutil.which(cmd)
    if not path:
        return False, f"{cmd} not found on PATH"
    return True, path


def _run_version(cmd: str) -> Tuple[bool, str]:
    try:
        out = subprocess.check_output([cmd, "--version"], text=True, stderr=subprocess.STDOUT)
        return True, out.strip()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def diagnose_environment() -> Dict[str, Dict[str, str]]:
    results: Dict[str, Dict[str, str]] = {}

    for tool in ("yt-dlp", "ffmpeg", "ffprobe"):
        ok, info = _check_cmd(tool)
        ver_ok, ver = _run_version(tool) if ok else (False, "")
        results[tool] = {
            "present": str(ok),
            "path": info if ok else "",
            "version": ver if ver_ok else "",
        }

    # Python deps
    pydeps = {
        "youtube-transcript-api": False,
    }
    try:
        import youtube_transcript_api  # noqa: F401

        pydeps["youtube-transcript-api"] = True
    except Exception:  # noqa: BLE001
        pydeps["youtube-transcript-api"] = False

    results["python_deps"] = {k: str(v) for k, v in pydeps.items()}
    return results


