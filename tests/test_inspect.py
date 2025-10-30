import json
from pathlib import Path

from corpus.inspect import inspect_artifact


def test_inspect_basic(tmp_path: Path) -> None:
    vid = "abc123"
    d = tmp_path / vid
    d.mkdir()
    (d / f"{vid}.info.json").write_text(json.dumps({"title": "T", "duration": 10}), encoding="utf-8")
    (d / f"{vid}.txt").write_text("00:00 hello", encoding="utf-8")
    (d / f"{vid}.en.vtt").write_text("WEBVTT", encoding="utf-8")
    (d / "shots").mkdir()
    (d / "shots" / "shot_0001.jpg").write_bytes(b"x")

    res = inspect_artifact(str(d), details=True)
    assert res["exists"] is True
    assert res["id"] == vid
    assert res["files"]["info_json"]
    assert res["files"]["transcript_txt"]
    assert len(res["files"]["subtitles_vtt"]) == 1
    assert res["shots"] == 1
    assert res["title"] == "T"


