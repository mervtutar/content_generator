import os, json
from app.graph.flow import build_graph, FlowState

def run_pipeline(job_dir: str):
    meta = json.load(open(os.path.join(job_dir, "meta.json"), "r", encoding="utf-8"))
    videos = meta.get("files", {}).get("videos", [])
    if not videos:
        raise RuntimeError("No video found in assets.")
    video_path = videos[0]

    state = FlowState(job_id=os.path.basename(job_dir), job_dir=job_dir, video_path=video_path)
    graph = build_graph()
    final_state = graph.invoke(state)  
    print("FINAL_STATE_TYPE:", type(final_state))

    if isinstance(final_state, dict):
        dumpable = final_state
    elif hasattr(final_state, "model_dump"):      # pydantic v2
        dumpable = final_state.model_dump()
    elif hasattr(final_state, "dict"):            # pydantic v1
        dumpable = final_state.dict()
    else:
        try:
            dumpable = vars(final_state)          # generic objeyi sözlüğe çevir
        except Exception:
            dumpable = {"value": str(final_state)}

    results_dir = os.path.join(job_dir, "results")
    os.makedirs(results_dir, exist_ok=True)
    with open(os.path.join(results_dir, "state.json"), "w", encoding="utf-8") as f:
        json.dump(dumpable, f, ensure_ascii=False, indent=2)