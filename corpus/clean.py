from __future__ import annotations

import os
import shutil
from typing import List


def delete_artifact(out_dir: str, video_id: str) -> bool:
    path = os.path.join(out_dir, video_id)
    if not os.path.isdir(path):
        return False
    shutil.rmtree(path)
    return True


def list_artifacts(out_dir: str) -> List[str]:
    if not os.path.isdir(out_dir):
        return []
    return [name for name in os.listdir(out_dir) if os.path.isdir(os.path.join(out_dir, name))]


