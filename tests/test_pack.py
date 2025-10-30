import base64
import gzip
import os
from pathlib import Path

from corpus.pack import PackConfig, pack_directory, _compress_text


def test_pack_directory_includes_and_excludes(tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / "a").mkdir(parents=True)
    (src / "a" / "keep.txt").write_text("hello world", encoding="utf-8")
    (src / "a" / "drop.log").write_text("ignore me", encoding="utf-8")
    (src / "node_modules").mkdir()
    (src / "node_modules" / "mod.js").write_text("npm", encoding="utf-8")

    out = tmp_path / "out.txt"
    cfg = PackConfig(
        input_dir=str(src),
        output_file=str(out),
        include_globs=["**/*.txt"],
        exclude_globs=["**/node_modules/**"],
        verbose=True,
    )
    path, stats = pack_directory(cfg)
    assert path == str(out)
    content = out.read_text(encoding="utf-8")
    assert "keep.txt" in content
    assert "drop.log" not in content
    assert "mod.js" not in content


def test_pack_directory_gzip_and_base64(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.txt").write_text("data", encoding="utf-8")
    out = tmp_path / "out.gz.b64"

    cfg = PackConfig(
        input_dir=str(src),
        output_file=str(out),
        include_globs=["**/*.txt"],
        gzip_out=True,
        base64_out=True,
    )
    pack_directory(cfg)
    raw = out.read_bytes()
    decoded = base64.b64decode(raw)
    # should be valid gzip
    text = gzip.decompress(decoded).decode("utf-8")
    assert "f.txt" in text


def test_compress_text_aggressive_removes_comments() -> None:
    src = """
    // comment line
    code /* block */ more
    a = 1 + 2 // tail
    """
    out = _compress_text(src, aggressive=True)
    assert "comment" not in out
    assert "block" not in out
    assert "a=1+2" in out or "a = 1 + 2" in out


