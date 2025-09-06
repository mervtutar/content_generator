# app/services/asr.py
import os, json, subprocess, shutil
from typing import Optional
from dotenv import load_dotenv
import whisper

load_dotenv()  # .env oku

def _bin(name: str, env_name: str) -> str:
    # .env'den oku; yoksa PATH'te ara
    return os.getenv(env_name) or shutil.which(name) or ""

FFMPEG = _bin("ffmpeg", "FFMPEG_PATH")
if not FFMPEG:
    raise RuntimeError("ffmpeg bulunamadı. FFMPEG_PATH ortam değişkenini ayarla veya ffmpeg'i PATH'e ekle.")
ffmpeg_dir = os.path.dirname(FFMPEG)
os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

def extract_audio_wav16(video_path: str, wav_path: str):
    os.makedirs(os.path.dirname(wav_path), exist_ok=True)
    cmd = [
        FFMPEG, "-y", "-i", video_path,
        "-ac", "1", "-ar", "16000",   # mono, 16 kHz
        "-vn", wav_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

def transcribe_to_srt(job_dir: str, video_path: str, model_name: str = "base", language: Optional[str] = None):
    results_dir = os.path.join(job_dir, "results")
    os.makedirs(results_dir, exist_ok=True)

    # 1) sesi çıkar
    wav_path = os.path.join(results_dir, "audio_16k.wav")
    extract_audio_wav16(video_path, wav_path)

    # 2) whisper modelini yükle
    model = whisper.load_model(model_name)
    kwargs = dict(temperature=0.0, fp16=False)
    if language:
        kwargs["language"] = language

    # 3) deşifre
    res = model.transcribe(wav_path, **kwargs)
    segments = res.get("segments", [])

    # 4) SRT yaz
    def fmt(t):
        h = int(t // 3600); m = int((t % 3600) // 60)
        s = int(t % 60); ms = int((t - int(t)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    srt_path = os.path.join(results_dir, "subtitles.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            f.write(f"{i}\n{fmt(seg['start'])} --> {fmt(seg['end'])}\n{seg['text'].strip()}\n\n")

    with open(os.path.join(results_dir, "transcript.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)

    return srt_path
