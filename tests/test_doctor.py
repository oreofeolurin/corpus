from corpus.doctor import diagnose_environment


def test_doctor_returns_expected_keys() -> None:
    res = diagnose_environment()
    # keys exist regardless of environment
    assert "yt-dlp" in res
    assert "ffmpeg" in res
    assert "ffprobe" in res
    assert "python_deps" in res


