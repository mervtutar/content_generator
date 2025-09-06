# app/orchestrator.py
import os, json
from app.services.video import process_video
from app.services.asr import transcribe_to_srt

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
WHISPER_LANG  = os.getenv("WHISPER_LANG", "")  # "tr" yazarsan dil kilitlenir

def run_pipeline(job_dir: str):
    results_dir = os.path.join(job_dir, "results")
    os.makedirs(results_dir, exist_ok=True)

    meta = json.load(open(os.path.join(job_dir, "meta.json"), "r", encoding="utf-8"))
    video_path = meta.get("files", {}).get("videos", [None])[0]
    assert video_path, "No video found."

    scenes = process_video(job_dir, video_path)
    srt = transcribe_to_srt(job_dir, video_path, model_name=WHISPER_MODEL,
                            language=(WHISPER_LANG or None))

    json.dump({"steps": {"scenes": len(scenes), "srt": bool(srt)}},
              open(os.path.join(results_dir, "scores.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
