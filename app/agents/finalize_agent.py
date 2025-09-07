# app/agents/finalize_agent.py
import os, json, zipfile

class FinalizeAgent:
    def run(self, job_dir: str, variants, scores):
        results = os.path.join(job_dir, "results")
        os.makedirs(results, exist_ok=True)

        best_id = max(scores.items(), key=lambda x: x[1]["total"])[0]
        best = next(v for v in variants["variants"] if v["id"] == best_id)

        with open(os.path.join(results, "captions.json"), "w", encoding="utf-8") as f:
            json.dump(variants, f, ensure_ascii=False, indent=2)
        with open(os.path.join(results, "hashtags.txt"), "w", encoding="utf-8") as f:
            f.write(" ".join(best.get("hashtags", [])))
        with open(os.path.join(results, "summary.json"), "w", encoding="utf-8") as f:
            json.dump({"selected": best_id, "caption": best["caption"],
                       "hashtags": best["hashtags"], "score": scores[best_id]["total"]},
                      f, ensure_ascii=False, indent=2)

        bundle = os.path.join(results, "bundle.zip")
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
            for fn in ["captions.json","hashtags.txt","subtitles.srt","scenes.json","summary.json"]:
                fp = os.path.join(results, fn)
                if os.path.isfile(fp):
                    z.write(fp, arcname=fn)
            frames = os.path.join(results, "frames")
            if os.path.isdir(frames):
                for name in sorted(os.listdir(frames))[:6]:
                    z.write(os.path.join(frames, name), arcname=f"frames/{name}")
        return bundle
