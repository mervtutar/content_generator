# app/graph/flow.py
from __future__ import annotations
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os, json, traceback

# --------------------- STATE ---------------------
class FlowState(BaseModel):
    job_id: str
    job_dir: str
    video_path: str

    # Content Understanding çıktıları
    scenes: List[Dict[str, Any]] = Field(default_factory=list)
    srt_path: Optional[str] = None
    vision: Dict[str, Any] = Field(default_factory=dict)

    # Trend + üretim + kalite
    trends: Dict[str, Any] = Field(default_factory=dict)
    variants: Optional[Dict[str, Any]] = None
    scores: Optional[Dict[str, Any]] = None

    # yönetim
    errors: List[str] = Field(default_factory=list)

    # --- revizyon kontrolü ---
    need_revision: bool = False
    revision_count: int = 0          # kaç kez revize edildi
    max_revisions: int = 1           # EN FAZLA 1 kez revize et

# --------------------- HELPERS -------------------
def _append_error(state: FlowState, err: Exception, label: str) -> FlowState:
    tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
    state.errors.append(f"[{label}] {tb}")
    return state

# --------------------- NODES ---------------------
def node_content_understanding(state: FlowState) -> FlowState:
    """Video sahneleri + ASR + BLIP (tek ajan)"""
    try:
        from app.agents.content_understanding_agent import ContentUnderstandingAgent
        from dotenv import load_dotenv; load_dotenv()
        data = ContentUnderstandingAgent().run(
            state.job_dir,
            state.video_path,
            whisper_model=os.getenv("WHISPER_MODEL", "base"),
            lang=os.getenv("WHISPER_LANG", "tr"),
        )
        state.scenes = data["scenes"]
        state.srt_path = data["srt_path"]
        state.vision = data["vision"]
        return state
    except Exception as e:
        return _append_error(state, e, "content_understanding")

def node_trend(state: FlowState) -> FlowState:
    try:
        meta = json.load(open(os.path.join(state.job_dir, "meta.json"), "r", encoding="utf-8"))
        from app.agents.trend_agent import TrendAgent

        seeds = []
        if "aso_keywords" in meta:
            seeds.extend(meta["aso_keywords"])
        if "game_name" in meta:
            seeds.append(meta["game_name"])
        if "description" in meta and meta["description"]:
            seeds.append(meta["description"])
        if state.vision.get("tags"):
            seeds.extend(state.vision["tags"])

        # Trend agent çağrısı
        state.trends = TrendAgent().run(state.job_dir, seeds)

        return state
    except Exception as e:
        return _append_error(state, e, "trend")


def node_generate(state: FlowState) -> FlowState:
    """Gemini ile caption/hashtag üretimi. Revizyon modunda sayacı artırır."""
    try:
        meta = json.load(open(os.path.join(state.job_dir, "meta.json"), "r", encoding="utf-8"))
        aso   = meta.get("aso_keywords", [])
        desc  = meta.get("description", "")
        tags  = state.vision.get("tags", [])
        trends = state.trends.get("terms", [])

        critique = None
        if state.need_revision and state.revision_count < state.max_revisions:
            critique = "QC/TrendFit düşük: trend terimlerini ve medya kurallarını dikkate alarak tekrar yaz."
            state.revision_count += 1  # <<< yalnızca burada artar

        from app.agents.generation_agent_llm import GenerationAgentLLM
        state.variants = GenerationAgentLLM().run(state.job_dir, aso, desc, tags, trends, critique=critique)
        state.need_revision = False
        return state
    except Exception as e:
        return _append_error(state, e, "generate_llm")

def node_qc(state: FlowState) -> FlowState:
    """QC: metin + medya + TrendFit. Revizyon hakkı varsa işaretler."""
    try:
        from app.agents.qc_agent import QCAgent
        trend_terms = state.trends.get("terms", [])
        state.scores = QCAgent().run(state.job_dir, state.variants, trend_terms, state.video_path)

        # karar
        THRESH = 75.0      # toplam skor eşiği
        TREND_MIN = 60.0   # trendfit min
        best_id = max(state.scores.items(), key=lambda x: x[1]["total"])[0]
        best = state.scores[best_id]

        can_revise = state.revision_count < state.max_revisions
        state.need_revision = ((best["total"] < THRESH) or (best.get("trendfit", 0) < TREND_MIN)) and can_revise
        return state
    except Exception as e:
        return _append_error(state, e, "qc")

def node_finalize(state: FlowState) -> FlowState:
    try:
        from app.agents.finalize_agent import FinalizeAgent
        FinalizeAgent().run(state.job_dir, state.variants, state.scores)
        return state
    except Exception as e:
        return _append_error(state, e, "finalize")

# --------------------- ROUTING -------------------
def after_qc(state: FlowState) -> str:
    return "revise" if state.need_revision else "done"

# --------------------- GRAPH ---------------------
def build_graph():
    g = StateGraph(FlowState)

    g.add_node("content_understanding", node_content_understanding)
    g.add_node("trend",    node_trend)
    g.add_node("generate", node_generate)
    g.add_node("qc",       node_qc)
    g.add_node("finalize", node_finalize)

    g.set_entry_point("content_understanding")
    g.add_edge("content_understanding", "trend")
    g.add_edge("trend", "generate")
    g.add_edge("generate", "qc")
    g.add_conditional_edges("qc", after_qc, {"revise": "generate", "done": "finalize"})
    g.add_edge("finalize", END)

    return g.compile()
