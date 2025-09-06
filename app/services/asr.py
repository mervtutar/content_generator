# app/services/asr.py
import os, json, subprocess
import whisper

def extract_audio_wav16(video_path: str, wav_path: str):
    os.makedirs(os.path.dirname(wav_path), exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-ac", "1", "-ar", "16000",    # mono, 16kHz
        "-vn", wav_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

def transcribe_to_srt(job_dir: str, video_path: str, model_name: str = "base", language: str | None = None):
    results_dir = os.path.join(job_dir, "results")
    os.makedirs(results_dir, exist_ok=True)

    # 1) Ses çıkar
    wav_path = os.path.join(results_dir, "audio_16k.wav")
    extract_audio_wav16(video_path, wav_path)

    # 2) Model
    model = whisper.load_model(model_name)   # CPU: "tiny"/"base"; GPU varsa "small"/"medium"

    # 3) Transcribe (CPU için fp16=False iyi olur)
    kwargs = dict(temperature=0.0, fp16=False)
    if language:  # Türkçe ise language="tr" verebilirsin; yoksa otomatik algılar
        kwargs["language"] = language
    res = model.transcribe(wav_path, **kwargs)
    segments = res.get("segments", [])

    # 4) SRT yaz
    srt_path = os.path.join(results_dir, "subtitles.srt")
    def fmt(t):
        h = int(t // 3600); m = int((t % 3600) // 60)
        s = int(t % 60); ms = int((t - int(t)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            f.write(f"{i}\n{fmt(seg['start'])} --> {fmt(seg['end'])}\n{seg['text'].strip()}\n\n")

    with open(os.path.join(results_dir, "transcript.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)

    return srt_path
