# app/services/video.py
import os, json, subprocess, shutil
from typing import List, Dict, Union
from scenedetect import VideoManager, SceneManager
from scenedetect.detectors import ContentDetector
from dotenv import load_dotenv
load_dotenv()  # .env dosyasını belleğe al

def _bin(name: str, env_name: str) -> str:
    return os.getenv(env_name) or shutil.which(name) or ""

FFMPEG  = _bin("ffmpeg",  "FFMPEG_PATH")
FFPROBE = _bin("ffprobe", "FFPROBE_PATH")
print("FFMPEG=", FFMPEG)
print("FFPROBE=", FFPROBE)

if not FFMPEG:
    raise RuntimeError("ffmpeg bulunamadı. FFMPEG_PATH ortam değişkenini ayarla veya ffmpeg'i PATH'e ekle.")
if not FFPROBE:
    raise RuntimeError("ffprobe bulunamadı. FFPROBE_PATH ortam değişkenini ayarla veya ffprobe'u PATH'e ekle.")

def _parse_tc_to_seconds(tc: Union[str, float, int, object]) -> float:
    if hasattr(tc, "get_seconds"):
        return float(tc.get_seconds())
    if isinstance(tc, str):
        try:
            h, m, s = tc.split(":")
            return int(h)*3600 + int(m)*60 + float(s)
        except Exception:
            return 0.0
    try:
        return float(tc)
    except Exception:
        return 0.0

def ffprobe_duration(video_path: str) -> float:
    out = subprocess.check_output(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "json", video_path]
    ).decode("utf-8", "ignore")
    return float(json.loads(out)["format"]["duration"])

def fixed_segments(duration: float, seg_len: float = 10.0) -> List[Dict]:
    t, out = 0.0, []
    while t < duration:
        end = min(duration, t + seg_len)
        out.append({"start": t, "end": end})
        t = end
    return out

def detect_scenes(video_path: str, threshold: float = 27.0, max_scenes: int = 10):
    vm = VideoManager([video_path])
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=threshold))
    vm.set_downscale_factor(2)
    vm.start()
    sm.detect_scenes(frame_source=vm)
    scene_list = sm.get_scene_list()
    vm.release()

    scenes = [{"start": _parse_tc_to_seconds(s), "end": _parse_tc_to_seconds(e)} for s, e in scene_list]
    if not scenes:
        duration = ffprobe_duration(video_path)
        scenes = fixed_segments(duration, seg_len=10.0)
    elif len(scenes) > max_scenes:
        scenes = scenes[:max_scenes]
    return scenes

def extract_keyframe(video_path: str, time_s: float, out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cmd = [FFMPEG, "-y", "-ss", str(time_s), "-i", video_path, "-vf", "scale=720:-1", "-frames:v", "1", out_path]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

def process_video(job_dir: str, video_path: str):
    results_dir = os.path.join(job_dir, "results")
    frames_dir = os.path.join(results_dir, "frames")
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(frames_dir, exist_ok=True)

    scenes = detect_scenes(video_path, threshold=27.0, max_scenes=12)
    for i, s in enumerate(scenes, start=1):
        mid = (s["start"] + s["end"])/2.0 if s["end"] is not None else s["start"] + 5.0
        out_jpg = os.path.join(frames_dir, f"scene_{i:02d}.jpg")
        extract_keyframe(video_path, mid, out_jpg)
        s["keyframe"] = out_jpg

    with open(os.path.join(results_dir, "scenes.json"), "w", encoding="utf-8") as f:
        json.dump(scenes, f, ensure_ascii=False, indent=2)
    return scenes
