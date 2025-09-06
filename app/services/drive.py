import os
from typing import Dict, List
import gdown

VIDEO_EXT = {".mp4", ".mov", ".mkv"}
IMAGE_EXT = {".jpg", ".jpeg", ".png"}

def download_folder(folder_url: str, dest_dir: str) -> None:
    os.makedirs(dest_dir, exist_ok=True)
    gdown.download_folder(
        url=folder_url,
        output=dest_dir,
        quiet=False,
        use_cookies=False,
        remaining_ok=True,
    )

def index_assets(dest_dir: str) -> Dict[str, List[str]]:
    videos, images, texts = [], [], []
    for root, _, files in os.walk(dest_dir):
        for fn in files:
            p = os.path.join(root, fn)
            low = fn.lower()
            if any(low.endswith(ext) for ext in VIDEO_EXT):
                videos.append(p)
            elif any(low.endswith(ext) for ext in IMAGE_EXT):
                images.append(p)
            elif low.endswith(".txt") or low.endswith(".json"):
                texts.append(p)
    return {"videos": videos, "images": images, "texts": texts}
