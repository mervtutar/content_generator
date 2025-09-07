import os, re, json, subprocess, shutil
from typing import Dict
from app.agents.trend_agent import TrendAgent

def _format_score(caption: str) -> float:
    L = len(caption)
    if L <= 180: return 1.0
    if L <= 300: return 0.8
    if L <= 600: return 0.6
    return 0.4

def _hashtag_score(tags) -> float:
    n = len(tags or [])
    if 8 <= n <= 12: return 1.0
    if 5 <= n < 8:   return 0.7
    if 12 < n <= 15: return 0.8
    return 0.5

def _repeat_penalty(caption: str) -> float:
    words = re.findall(r"[A-Za-zĞÜŞİÖÇğüşıöç0-9]+", caption, flags=re.UNICODE)
    from collections import Counter
    mx = max(Counter([w.lower() for w in words]).values() or [1])
    return 1.0 if mx < 4 else 0.7

def _bin(name, env): return os.getenv(env) or shutil.which(name) or ""
FFPROBE = _bin("ffprobe", "FFPROBE_PATH")

def _media_metrics(video_path: str) -> Dict:
    if not FFPROBE or not os.path.isfile(video_path):
        return {"width": 0, "height": 0, "duration": 0.0, "bitrate": 0}
    out = subprocess.check_output([FFPROBE, "-v", "error",
                                   "-select_streams", "v:0",
                                   "-show_entries", "stream=width,height,bit_rate",
                                   "-show_entries", "format=duration",
                                   "-of", "json", video_path]).decode("utf-8","ignore")
    import json as _j
    js = _j.loads(out)
    w = js.get("streams",[{}])[0].get("width",0)
    h = js.get("streams",[{}])[0].get("height",0)
    br= js.get("streams",[{}])[0].get("bit_rate",0)
    dur=float(js.get("format",{}).get("duration",0.0))
    return {"width":w,"height":h,"duration":dur,"bitrate":int(br or 0)}

def _media_score(metrics: Dict) -> float:
    w,h,dur,br = metrics["width"], metrics["height"], metrics["duration"], metrics["bitrate"]
    # IG Reels öneri: 1080x1920 (9:16), 5-60 sn, makul bitrate
    ok_res = (w>=720 and h>=1280)
    ratio = (h>0 and abs((w/h) - (9/16)) <= 0.05)
    ok_dur = (5 <= dur <= 90) or dur==0  # tolerans
    ok_br  = (br==0 or br >= 500_000)
    score = (0.35*(1.0 if ok_res else 0.6) +
             0.35*(1.0 if ratio else 0.5) +
             0.2*(1.0 if ok_dur else 0.6) +
             0.1*(1.0 if ok_br else 0.7))
    return round(score,3)

BANNED = {"FREE", "BEDAVA", "NO ADS"}  # örnek; genişletilebilir

class QCAgent:
    def run(self, job_dir: str, variants, trend_terms, video_path: str):
        # medya metrikleri
        m = _media_metrics(video_path)
        mscore = _media_score(m)

        out = {}
        for v in variants["variants"]:
            cap = v["caption"]
            # text skorları
            f = _format_score(cap)
            h = _hashtag_score(v.get("hashtags"))
            r = _repeat_penalty(cap)
            # trend uyumu
            trendfit = TrendAgent._trendfit_score(cap, trend_terms)

            # banned basit ceza
            banned_pen = 0.9 if any(b.lower() in cap.lower() for b in BANNED) else 1.0

            total = 100 * (0.25*f + 0.25*h + 0.15*r + 0.2*mscore + 0.15*(trendfit/100.0)) * banned_pen
            out[v["id"]] = {
                "format": round(f,3), "hashtags": round(h,3), "repeat": round(r,3),
                "media": m, "media_score": mscore,
                "trendfit": round(trendfit,1),
                "total": round(total,1)
            }

        results_dir = os.path.join(job_dir, "results"); os.makedirs(results_dir, exist_ok=True)
        with open(os.path.join(results_dir, "scores.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        return out
