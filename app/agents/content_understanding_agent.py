# app/agents/content_understanding_agent.py
import os, json
from typing import Dict, Any, List
from PIL import Image
from transformers import BlipForConditionalGeneration, BlipProcessor

from app.services.video import process_video
from app.services.asr import transcribe_to_srt

class ContentUnderstandingAgent:
    """
    Tek ajan içinde:
      - Video: sahne & keyframe
      - Audio: Whisper -> SRT
      - Image: BLIP caption & tags
    """

    def __init__(self, blip_model: str = "Salesforce/blip-image-captioning-base"):
        self.processor = BlipProcessor.from_pretrained(blip_model)
        self.model = BlipForConditionalGeneration.from_pretrained(blip_model)

    @staticmethod
    def _tags_from_caption(caption: str) -> List[str]:
        words = [w.strip(".,!?;:()[]\"'").lower() for w in caption.split()]
        stop = {"the","and","with","this","that","for","from","into","your","have","has","are","you",
                "bir","ile","ve","için","bu"}
        return list(dict.fromkeys([w for w in words if len(w) >= 3 and w.isalpha() and w not in stop]))[:10]

    def _vision(self, job_dir: str) -> Dict[str, Any]:
        frames_dir = os.path.join(job_dir, "results", "frames")
        frames = []
        if os.path.isdir(frames_dir):
            frames = [os.path.join(frames_dir, f) for f in sorted(os.listdir(frames_dir))
                      if f.lower().endswith((".jpg",".png"))][:12]
        captions = []
        for fp in frames:
            try:
                img = Image.open(fp).convert("RGB")
                inputs = self.processor(img, return_tensors="pt")
                out = self.model.generate(**inputs, max_new_tokens=30)
                text = self.processor.decode(out[0], skip_special_tokens=True).strip()
                captions.append({"frame": fp, "caption": text, "tags": self._tags_from_caption(text)})
            except Exception:
                continue

        agg_tags = []
        for c in captions:
            for t in c["tags"]:
                if t not in agg_tags:
                    agg_tags.append(t)
        return {"frames": frames, "captions": captions, "tags": agg_tags[:15]}

    def run(self, job_dir: str, video_path: str, whisper_model="base", lang="tr") -> Dict[str, Any]:
        results_dir = os.path.join(job_dir, "results")
        os.makedirs(results_dir, exist_ok=True)

        # 1) Video sahneleri & keyframe
        scenes = process_video(job_dir, video_path)

        # 2) Audio -> transcript + SRT
        srt_path = transcribe_to_srt(job_dir, video_path, model_name=whisper_model, language=lang)

        # 3) Image understanding (BLIP)
        vision_data = self._vision(job_dir)

        data = {"scenes": scenes, "srt_path": srt_path, "vision": vision_data}
        with open(os.path.join(results_dir, "content_understanding.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data
