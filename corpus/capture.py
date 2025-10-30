from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


def _run(cmd: List[str]) -> Tuple[int, str, str]:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate()
    return proc.returncode, out, err


def _to_mmss(ts: str) -> str:
    ts_main = ts.split(".")[0]
    parts = [int(p) for p in ts_main.split(":")]
    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours, minutes, seconds = 0, parts[0], parts[1]
    else:
        hours, minutes, seconds = 0, 0, parts[0]
    total = hours * 3600 + minutes * 60 + seconds
    return f"{total // 60:02d}:{total % 60:02d}"


def _vtt_to_text(vtt_path: str, out_txt_path: str) -> int:
    import re as _re

    if not os.path.exists(vtt_path):
        return 0
    with open(vtt_path, "r", encoding="utf-8") as f:
        data = f.read()
    lines = data.splitlines()
    out_lines: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].lstrip("\ufeff").strip()
        if not line or line.startswith("WEBVTT") or line.startswith("NOTE") or line.startswith("STYLE") or line.startswith("REGION"):
            i += 1
            continue
        if "-->" not in line and i + 1 < len(lines) and "-->" in lines[i + 1]:
            i += 1
            line = lines[i]
        if "-->" in line:
            ts_line = line
            try:
                start = ts_line.split("-->")[0].strip()
                start_mmss = _to_mmss(start)
            except Exception:
                start_mmss = ""
            i += 1
            texts: List[str] = []
            while i < len(lines) and lines[i].strip() != "":
                t = lines[i]
                t = _re.sub(r"<[^>]+>", "", t)
                t = _re.sub(r"^\w+::", "", t)
                texts.append(t.strip())
                i += 1
            if texts:
                merged = " ".join(texts)
                merged = _re.sub(r"\s+", " ", merged).strip()
                if merged:
                    out_lines.append(f"{start_mmss} {merged}")
        else:
            i += 1
    with open(out_txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines))
    return len(out_lines)


def _extract_info(url: str) -> dict:
    code, out, err = _run(["yt-dlp", "-J", url])
    if code != 0:
        raise RuntimeError(f"yt-dlp -J failed: {err.strip()}")
    try:
        return json.loads(out)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to parse yt-dlp JSON: {exc}")


def _download_subtitles(url: str, out_dir: str, video_id: str, lang: str, info: Optional[dict]) -> Optional[str]:
    """Attempt to download subtitles; prefer auto-subs, then authored subs.

    Uses yt-dlp with --sub-langs and --convert-subs vtt, then returns any
    <video_id>.*.vtt found in out_dir (matching language variants like en-GB).
    """
    # Accept language variants like en-GB via glob-like syntax and common aliases
    common = [lang, f"{lang}.*"]
    if lang == "en":
        common.extend(["en-US", "en-GB"])
    sub_langs = ",".join(common)
    out_tmpl = os.path.join(out_dir, f"{video_id}.%(ext)s")

    def find_any_vtt() -> Optional[str]:
        for name in os.listdir(out_dir):
            if name.startswith(video_id) and name.endswith(".vtt"):
                return os.path.join(out_dir, name)
        return None

    # Try auto-subs
    args_auto = [
        "yt-dlp",
        "--skip-download",
        "--write-auto-subs",
        "--sub-langs",
        sub_langs,
        "--convert-subs",
        "vtt",
        "-o",
        out_tmpl,
        url,
    ]
    _run(args_auto)
    vtt = find_any_vtt()
    if vtt:
        return vtt

    # Try authored subs
    args_authored = [
        "yt-dlp",
        "--skip-download",
        "--write-subs",
        "--sub-langs",
        sub_langs,
        "--convert-subs",
        "vtt",
        "-o",
        out_tmpl,
        url,
    ]
    _run(args_authored)
    vtt2 = find_any_vtt()
    if vtt2:
        return vtt2

    # Manual fallback using automatic_captions from info JSON
    if info and isinstance(info, dict):
        aut_caps = info.get("automatic_captions") or {}
        if isinstance(aut_caps, dict) and aut_caps:
            # Priority: exact lang key -> tlang match -> 'en' -> any
            priority_langs = []
            if lang in aut_caps:
                priority_langs.append(lang)
            # tlang match
            for k, entries in aut_caps.items():
                if any(isinstance(e, dict) and f"tlang={lang}" in (e.get("url") or "") for e in entries or []):
                    if k not in priority_langs:
                        priority_langs.append(k)
            if "en" in aut_caps and "en" not in priority_langs:
                priority_langs.append("en")
            # any remaining
            for k in aut_caps.keys():
                if k not in priority_langs:
                    priority_langs.append(k)

            for code in priority_langs:
                entries = aut_caps.get(code) or []
                for e in entries:
                    if not isinstance(e, dict):
                        continue
                    if e.get("ext") == "vtt" and e.get("url"):
                        try:
                            dest = os.path.join(out_dir, f"{video_id}.{code}.vtt")
                            urllib.request.urlretrieve(e["url"], dest)
                            if os.path.exists(dest):
                                return dest
                        except Exception:
                            continue
    return None


def _fallback_transcript(video_id: str, out_json: str, out_txt: str) -> bool:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi as YTA
    except Exception:
        return False
    transcript = None
    try:
        transcript = YTA.get_transcript(video_id, languages=["en", "en-US", "en-GB"])
    except Exception:
        try:
            transcripts = YTA.list_transcripts(video_id)
            for lang in ["en", "en-US", "en-GB"]:
                try:
                    t = transcripts.find_transcript([lang])
                    transcript = t.fetch()
                    break
                except Exception:
                    pass
            if transcript is None:
                for t in transcripts:
                    try:
                        transcript = t.translate("en").fetch()
                        break
                    except Exception:
                        pass
        except Exception:
            transcript = None
    if not transcript:
        return False
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(transcript, f, ensure_ascii=False, indent=2)
    with open(out_txt, "w", encoding="utf-8") as f:
        for item in transcript:
            mm = int(item["start"] // 60)
            ss = int(item["start"] % 60)
            f.write(f"{mm:02d}:{ss:02d} {item['text']}\n")
    return True


def _download_video(url: str, out_dir: str, video_id: str) -> Optional[str]:
    out_path = os.path.join(out_dir, f"{video_id}.mp4")
    fmt = "bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/mp4"
    code, out, err = _run(["yt-dlp", "-f", fmt, "-o", out_path, url])
    if code == 0 and os.path.exists(out_path):
        return out_path
    return None


def _get_duration_seconds(info: Optional[dict], video_path: Optional[str]) -> Optional[float]:
    if info is not None:
        dur = info.get("duration")
        if isinstance(dur, (int, float)) and dur > 0:
            return float(dur)
    if video_path and _which("ffprobe"):
        code, out, err = _run([
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nk=1:nw=1",
            video_path,
        ])
        if code == 0:
            try:
                val = float(out.strip())
                return val if val > 0 else None
            except Exception:
                pass
    return None


def _extract_screenshots(
    video_path: str,
    shots_dir: str,
    mode: str,
    every_seconds: int,
    max_screenshots: Optional[int],
    duration_seconds: Optional[float],
    scene_threshold: float = 0.3,
) -> int:
    _ensure_dir(shots_dir)
    if _which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH. Please install ffmpeg.")

    if mode == "interval":
        vf = f"fps=1/{max(1, every_seconds)}"
        out_pattern = os.path.join(shots_dir, "shot_%04d.jpg")
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            video_path,
            "-vf",
            vf,
            "-qscale:v",
            "2",
            out_pattern,
        ]
        code, out, err = _run(cmd)
        if code != 0:
            raise RuntimeError(f"ffmpeg failed: {err.strip()}")

    elif mode == "uniform":
        if not duration_seconds or duration_seconds <= 0:
            return _extract_screenshots(
                video_path, shots_dir, "interval", every_seconds, max_screenshots, duration_seconds, scene_threshold
            )
        shots = max_screenshots or 20
        shots = max(1, shots)
        start_offset = 1.0
        end_offset = 1.0
        total = max(duration_seconds - start_offset - end_offset, 1.0)
        for idx in range(shots):
            t = start_offset + (total * idx / max(1, shots - 1)) if shots > 1 else duration_seconds / 2
            out_path = os.path.join(shots_dir, f"shot_{idx+1:04d}.jpg")
            cmd = [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{t:.2f}",
                "-i",
                video_path,
                "-frames:v",
                "1",
                "-qscale:v",
                "2",
                out_path,
            ]
            code, out, err = _run(cmd)
            if code != 0:
                raise RuntimeError(f"ffmpeg at t={t:.2f}s failed: {err.strip()}")

    elif mode == "scene":
        out_pattern = os.path.join(shots_dir, "shot_%04d.jpg")
        sel = f"select='gt(scene,{scene_threshold})'"
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            video_path,
            "-vf",
            sel,
            "-vsync",
            "vfr",
            "-qscale:v",
            "2",
            out_pattern,
        ]
        if max_screenshots and max_screenshots > 0:
            cmd += ["-vframes", str(max_screenshots)]
        code, out, err = _run(cmd)
        if code != 0:
            raise RuntimeError(f"ffmpeg scene-detect failed: {err.strip()}")

    else:
        raise ValueError(f"Unknown mode: {mode}")

    created = [p for p in os.listdir(shots_dir) if p.lower().endswith(".jpg")]
    return len(created)


@dataclass
class CaptureOptions:
    url: str
    out_dir: str = "artifacts/yt"
    lang: str = "en"
    mode: str = "interval"  # interval|uniform|scene
    every_seconds: int = 60
    max_screenshots: int = 60
    scene_threshold: float = 0.3
    overwrite: bool = False
    skip_video: bool = False
    skip_subtitles: bool = False
    skip_screenshots: bool = False
    write_index: bool = True


def capture_video(options: CaptureOptions) -> Dict[str, object]:
    _ensure_dir(options.out_dir)
    info = _extract_info(options.url)
    video_id = info.get("id") or "video"
    video_title = info.get("title", "")
    video_dir = os.path.join(options.out_dir, video_id)
    _ensure_dir(video_dir)

    info_path = os.path.join(video_dir, f"{video_id}.info.json")
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    txt_path = os.path.join(video_dir, f"{video_id}.txt")
    vtt_path: Optional[str] = None
    json_path = os.path.join(video_dir, f"{video_id}.subs.json")
    lines_written = 0
    if not options.skip_subtitles:
        vtt_path = _download_subtitles(options.url, video_dir, video_id, options.lang, info)
        if vtt_path:
            lines_written = _vtt_to_text(vtt_path, txt_path)
        if lines_written == 0:
            if _fallback_transcript(video_id, json_path, txt_path):
                with open(txt_path, "r", encoding="utf-8") as f:
                    lines_written = sum(1 for _ in f)

    video_path: Optional[str] = None
    shots_dir = os.path.join(video_dir, "shots")
    num_shots = 0
    if not options.skip_video:
        video_path = _download_video(options.url, video_dir, video_id)
        if video_path and not options.skip_screenshots:
            try:
                duration_seconds = _get_duration_seconds(info, video_path)
                num_shots = _extract_screenshots(
                    video_path=video_path,
                    shots_dir=shots_dir,
                    mode=options.mode,
                    every_seconds=options.every_seconds,
                    max_screenshots=options.max_screenshots,
                    duration_seconds=duration_seconds,
                    scene_threshold=options.scene_threshold,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"Warning: failed to extract screenshots: {exc}", file=sys.stderr)

    summary: Dict[str, object] = {
        "id": video_id,
        "title": video_title,
        "out_dir": video_dir,
        "transcript_txt": txt_path if os.path.exists(txt_path) else None,
        "subtitles_vtt": vtt_path if vtt_path and os.path.exists(vtt_path) else None,
        "video_path": video_path if video_path and os.path.exists(video_path) else None,
        "screenshots_dir": shots_dir if os.path.isdir(shots_dir) else None,
        "num_screenshots": num_shots,
        "lines_in_transcript": lines_written,
    }
    # Emit index.json for the capture directory (Corpus v1)
    if options.write_index:
        try:
            from .indexer import build_index, write_index_json

            idx = build_index(video_dir)
            write_index_json(idx, os.path.join(video_dir, "index.json"))
            summary["index_json"] = os.path.join(video_dir, "index.json")
        except Exception:
            pass
    return summary


