from pathlib import Path

from corpus.capture import _vtt_to_text


def test_vtt_to_text_parses_basic(tmp_path: Path) -> None:
    vtt = tmp_path / "a.vtt"
    out = tmp_path / "a.txt"
    vtt.write_text(
        """WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n\n00:00:02.000 --> 00:00:03.000\nWorld\n""",
        encoding="utf-8",
    )
    lines = _vtt_to_text(str(vtt), str(out))
    assert lines == 2
    text = out.read_text(encoding="utf-8").strip().splitlines()
    assert text[0].endswith("Hello")
    assert text[1].endswith("World")


