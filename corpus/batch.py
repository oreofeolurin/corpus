from __future__ import annotations

import concurrent.futures as futures
import json
import sys
from typing import Iterable, List, Optional

from .capture import CaptureOptions, capture_video


def _capture_one(url: str, options: CaptureOptions) -> dict:
    opts = CaptureOptions(
        url=url,
        out_dir=options.out_dir,
        lang=options.lang,
        mode=options.mode,
        every_seconds=options.every_seconds,
        max_screenshots=options.max_screenshots,
        scene_threshold=options.scene_threshold,
        overwrite=options.overwrite,
        skip_video=options.skip_video,
        skip_subtitles=options.skip_subtitles,
        skip_screenshots=options.skip_screenshots,
    )
    return capture_video(opts)


def run_batch(urls: List[str], options: CaptureOptions, concurrency: int = 2, fail_fast: bool = False, jsonl: bool = False) -> List[dict]:
    results: List[dict] = []
    with futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        future_to_url = {pool.submit(_capture_one, url, options): url for url in urls}
        for fut in futures.as_completed(future_to_url):
            url = future_to_url[fut]
            try:
                summary = fut.result()
                results.append(summary)
                if jsonl:
                    sys.stdout.write(json.dumps(summary, ensure_ascii=False) + "\n")
            except Exception as exc:  # noqa: BLE001
                if fail_fast:
                    raise
                results.append({"url": url, "error": str(exc)})
                if jsonl:
                    sys.stdout.write(json.dumps({"url": url, "error": str(exc)}, ensure_ascii=False) + "\n")
    return results


