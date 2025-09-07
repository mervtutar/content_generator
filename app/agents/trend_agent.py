# app/agents/trend_agent.py
import os, json, time
from typing import Dict, List, Iterable
from collections import Counter

from pytrends.request import TrendReq
from sentence_transformers import SentenceTransformer
import numpy as np
from scipy.spatial.distance import cdist

EMBED_MODEL = os.getenv("TREND_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


# ---- Embedding helper --------------------------------------------------------
_model_cache = {"emb": None}
def _embed(texts: List[str]) -> np.ndarray:
    if _model_cache["emb"] is None:
        _model_cache["emb"] = SentenceTransformer(EMBED_MODEL)
    vecs = _model_cache["emb"].encode(
        texts, normalize_embeddings=True, show_progress_bar=False
    )
    return np.array(vecs, dtype="float32")


# ---- Trend Agent --------------------------------------------------------------
class TrendAgent:
    """
    Oyuna-özgü Trend Analizi

    - Dışarıdan verilen seeds (ASO, başlık, açıklamadan türetilmiş) ile
      Google Trends 'related_queries' üzerinden aday terimleri toplar.
    - Ağ/quota hatasında sabit kelime DÖNMEZ; eldeki seed'leri güvenli fallback
      olarak kullanır.
    - QC ajanı için `_trendfit_score` (cosine similarity) sağlar.
    """

    def __init__(self, geo: str = "TR", lang: str = "tr-TR", tz: int = 180):
        self.geo = geo
        self.lang = lang
        self.tz = tz

    # Eski akışla uyumluluk: flow.py -> TrendAgent().run(job_dir, seeds)
    def run(self, job_dir: str, seeds: List[str]) -> Dict:
        terms = self._google_trends(seeds)
        trend = {"terms": terms, "ts": int(time.time())}

        results_dir = os.path.join(job_dir, "results")
        os.makedirs(results_dir, exist_ok=True)
        with open(os.path.join(results_dir, "trends.json"), "w", encoding="utf-8") as f:
            json.dump(trend, f, ensure_ascii=False, indent=2)
        return trend

    # ---- Internal -------------------------------------------------------------
    def _google_trends(self, seeds: List[str], timeframe: str = "now 7-d") -> List[str]:
        seeds = self._normalize_seeds(seeds)[:8]  # gereksiz gürültüyü azalt
        if not seeds:
            return []

        try:
            pytrends = TrendReq(hl=self.lang, tz=self.tz)
            bag: Counter = Counter()

            for kw in seeds[:5]:
                if not kw:
                    continue
                pytrends.build_payload([kw], timeframe=timeframe, geo=self.geo)
                rel = pytrends.related_queries() or {}
                # {'kw': {'top': DataFrame(query, value), 'rising': DataFrame(...) }}
                for obj in rel.values():
                    if obj and obj.get("top") is not None:
                        df = obj["top"]
                        for _, row in df.iterrows():
                            term = str(row.get("query", "")).strip().lower()
                            val = int(row.get("value", 50) or 50)
                            if term and term not in seeds:
                                bag[term] += val

            # Hiç sonuç gelmediyse sabite DÖNME – seed'leri kullan
            if not bag:
                return seeds

            ranked = [t for t, _ in bag.most_common(40)]
            return ranked

        except Exception:
            # ağ/quota hatası vs.: sabite düşme yok; mevcut seed'leri kullan
            return seeds

    @staticmethod
    def _normalize_seeds(seeds: Iterable[str]) -> List[str]:
        out: List[str] = []
        for s in seeds or []:
            if not s:
                continue
            s = str(s).strip().lower()
            # çok uzun açıklamalar geldiyse sadece ilk 6-8 kelimeyi al
            toks = s.split()
            if len(toks) > 8:
                s = " ".join(toks[:8])
            if s and s not in out:
                out.append(s)
        return out

    # ---- QC için: Trend uyum skoru -------------------------------------------
    @staticmethod
    def _trendfit_score(caption: str, trend_terms: List[str]) -> float:
        """
        Caption ile trend terimleri arasındaki benzerliği ölçer (cosine sim.).
        En iyi 5 terimin ortalamasını % cinsinden döndürür.
        """
        trend_terms = [t for t in (trend_terms or []) if t]
        if not caption or not trend_terms:
            return 50.0  # nötr skor

        vecs = _embed([caption] + trend_terms)
        cap_vec = vecs[0:1]
        terms_vec = vecs[1:]
        sims = 1.0 - cdist(cap_vec, terms_vec, metric="cosine")[0]
        topk = sorted(sims, reverse=True)[:5]
        return float(np.mean(topk) * 100.0)
