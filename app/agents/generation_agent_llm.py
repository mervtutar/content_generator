# app/agents/generation_agent_llm.py
from __future__ import annotations

import os
import json
import re
from typing import Dict, List, Any, Optional

from dotenv import load_dotenv


try:
    from app.llm.gemini_llm import get_model as _get_gemini_model  
except Exception:
    import google.generativeai as genai

    def _get_gemini_model(model_name: str):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY missing in environment.")
        genai.configure(api_key=api_key)
        return genai.GenerativeModel(model_name)


# -------------------- Promptlar --------------------
SYSTEM_PROMPT = (
    "Sen bir sosyal medya içerik editörü ve ASO uzmanısın. "
    "Yalnızca istenen JSON formatında yanıtlarsın — hiçbir açıklama, giriş/preface, "
    "uyarı veya serbest metin döndürmezsin."
)

USER_PROMPT_TMPL = """
Aşağıdaki bilgilerle Instagram postu için 3 farklı varyant üret.

- Dil: {lang}
- Oyun adı: {game_name}
- Oyun açıklaması (özet): {description}
- Görsel/Video tag'leri: {tags}
- Trend terimleri: {trends}
- ASO anahtar kelimeleri: {aso}

Kurallar:
1) Yalnızca JSON döndür (code block yok). Biçim:
{{
  "variants": [
    {{"id":"v1","caption":"...", "hashtags":["#..."]}},
    {{"id":"v2","caption":"...", "hashtags":["#..."]}},
    {{"id":"v3","caption":"...", "hashtags":["#..."]}}
  ]
}}
2) caption: 1–2 cümle (90–220 karakter), anlaşılır ve aksiyona çağıran bir üslup; emoji serbest ama aşırıya kaçma.
3) Açıklama/preface/giriş cümlesi YAZMA (örn: "Harika bir görev!", "İşte 3 öneri:", "Editör olarak..." yasak).
4) Hashtag: 8–12 adet, tek # ile, boşlukla ayrık; trend terimlerinden en az BİRİ mutlaka kullanılsın.
5) Yasak: madde işareti, numaralandırma, '---' ayraçları, "Öneri:", "editör", "tekrar yaz", "revize" gibi meta ifadeler.

{critique_block}

Şimdi sadece geçerli JSON ver.
"""

# -------------------- Yardımcılar --------------------
FORBIDDEN_PREFIXES = (
    "harika bir görev", "işte", "aşağıda", "öneri",
    "editör", "editor", "tekrar yaz", "revize", "---"
)

def _sanitize_caption(text: str) -> str:
    """Modelin preamble/giriş cümlelerini veya ayraçlarını temizle."""
    t = (text or "").strip()
    low = t.lower()
    for fp in FORBIDDEN_PREFIXES:
        if low.startswith(fp):
            # ilk satırı at; geri kalanı toparla
            lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
            t = " ".join(lines[1:]) if len(lines) > 1 else ""
            break
    # baş/son ayraçları temizle
    t = re.sub(r"^-{2,}|-{2,}$", "", t).strip()
    return t

def _force_json(text: str) -> Dict[str, Any]:
    """Gemini bazen code fence veya metin ekleyebilir; JSON gövdesini çıkar."""
    cleaned = text.strip()

    # ```json ... ``` kaldır
    cleaned = re.sub(r"^```json\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.DOTALL).strip()
    # Çoğu durumda { ile } arasını almak yeterli olur
    if cleaned and cleaned[0] != "{":
        m = re.search(r"\{.*\}\s*$", cleaned, flags=re.DOTALL)
        if m:
            cleaned = m.group(0)
    return json.loads(cleaned)

def _parse_variants(raw_text: str) -> Dict[str, Any]:
    data = _force_json(raw_text)
    out = {"variants": []}
    for it in data.get("variants", []):
        cid = it.get("id")
        cap = _sanitize_caption(it.get("caption", ""))
        tags = [h.strip() for h in (it.get("hashtags") or []) if h.strip().startswith("#")]
        if cid and cap and tags:
            out["variants"].append({"id": cid, "caption": cap, "hashtags": tags})
    # En az bir varyant yoksa kaba bir emniyet ağı:
    if not out["variants"]:
        raise ValueError("No valid variants parsed from LLM output.")
    return out


# -------------------- Agent --------------------
class GenerationAgentLLM:
    """Gemini tabanlı caption/hashtag üretici."""

    def __init__(self, model_name: Optional[str] = None):
        load_dotenv()
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.model = _get_gemini_model(self.model_name)

    def _call_llm(self, prompt: str) -> str:
        # app.llm.gemini_llm.get_model() genelde .generate_content kullanır
        if hasattr(self.model, "generate_content"):
            res = self.model.generate_content(prompt)
            # genai: res.text / LangChain wrapper: res.candidates[0].content.parts[0].text olabilir
            text = getattr(res, "text", None)
            if text is None:
                # yedek okuma
                try:
                    text = res.candidates[0].content.parts[0].text  # type: ignore
                except Exception:
                    raise RuntimeError("Gemini response has no text field.")
            return text
        # farklı bir wrapper ise:
        if callable(getattr(self.model, "invoke", None)):
            return self.model.invoke(prompt)  # type: ignore
        raise RuntimeError("Unsupported Gemini model client.")

    def run(
        self,
        job_dir: str,
        aso_keywords: List[str],
        description: str,
        tags: List[str],
        trends: List[str],
        critique: Optional[str] = None,
        lang: str = "tr",
        game_name: str = "Game"
    ) -> Dict[str, Any]:
        """
        Sonuç: {"variants":[{"id":"v1","caption":..., "hashtags":[...]}...]}
        ve results/captions.json dosyası yazılır.
        """
        # ---- prompt inşası
        critique_block = ""
        if critique:
            critique_block = f"Revizyon talimatı: {critique}\n"

        user_prompt = USER_PROMPT_TMPL.format(
            lang=lang,
            game_name=game_name,
            description=description[:700],
            tags=", ".join(tags[:20]),
            trends=", ".join(trends[:20]),
            aso=", ".join(aso_keywords[:30]),
            critique_block=critique_block
        )
        full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}".strip()

        # ---- LLM çağrısı
        raw = self._call_llm(full_prompt)

        # ---- parse & sanitize
        data = _parse_variants(raw)

        # ---- diske yaz
        results_dir = os.path.join(job_dir, "results")
        os.makedirs(results_dir, exist_ok=True)
        out_path = os.path.join(results_dir, "captions.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return data
