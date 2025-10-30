from __future__ import annotations

import json
import os
from typing import Dict, Optional


def inspect_artifact(path: str, details: bool = False) -> Dict[str, object]:
    result: Dict[str, object] = {
        "path": path,
        "exists": os.path.isdir(path),
        "id": None,
        "title": None,
        "files": {},
        "shots": 0,
    }
    if not os.path.isdir(path):
        return result

    # Infer video id from folder name
    video_id = os.path.basename(os.path.normpath(path))
    result["id"] = video_id

    info_path = os.path.join(path, f"{video_id}.info.json")
    txt_path = os.path.join(path, f"{video_id}.txt")
    vtt_candidates = [p for p in os.listdir(path) if p.endswith(".vtt")]
    mp4_path = os.path.join(path, f"{video_id}.mp4")
    shots_dir = os.path.join(path, "shots")
    shots = [p for p in os.listdir(shots_dir)] if os.path.isdir(shots_dir) else []

    result["files"] = {
        "info_json": info_path if os.path.exists(info_path) else None,
        "transcript_txt": txt_path if os.path.exists(txt_path) else None,
        "subtitles_vtt": [os.path.join(path, p) for p in vtt_candidates],
        "video_path": mp4_path if os.path.exists(mp4_path) else None,
        "shots_dir": shots_dir if os.path.isdir(shots_dir) else None,
    }
    result["shots"] = len([p for p in shots if p.lower().endswith(".jpg")])

    if details and os.path.exists(info_path):
        try:
            with open(info_path, "r", encoding="utf-8") as f:
                info = json.load(f)
            result["title"] = info.get("title")
            result["duration"] = info.get("duration")
            result["uploader"] = info.get("uploader")
        except Exception:
            pass

    return result


