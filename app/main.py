# app/main.py
import os, json, uuid
from fastapi import FastAPI, Body, HTTPException, Request, Form
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from app.models.schemas import IngestFolderRequest, IngestResponse, RunRequest
from app.services.drive import download_folder, index_assets
from app.orchestrator import run_pipeline

load_dotenv()
APP_DIR = os.path.dirname(__file__)
STORAGE = os.getenv("STORAGE_PATH", os.path.abspath(os.path.join(APP_DIR, "..", "storage")))
os.makedirs(STORAGE, exist_ok=True)

UI_TITLE = os.getenv("UI_TITLE", "Ai Instagram Content Generator")

app = FastAPI(title="Ai Instagram Content Generator - Multi-Agent (UI)")

# --- UI ---
TEMPLATES_DIR = os.path.join(APP_DIR, "templates")
os.makedirs(TEMPLATES_DIR, exist_ok=True)
templates = Jinja2Templates(directory=TEMPLATES_DIR)

def _guess_game_name(aso: list[str], description: str, fallback: str) -> str:
    first = (description.splitlines() or [""])[0].strip()
    if 3 <= len(first) <= 60:
        return first
    if aso:
        k = aso[0].strip()
        if 3 <= len(k) <= 60:
            return k
    return fallback

@app.get("/ui", response_class=HTMLResponse)
def ui_form(request: Request):
    return templates.TemplateResponse("form.html", {"request": request, "ui_title": UI_TITLE})

@app.post("/ui/run")
def ui_run(request: Request, folder_url: str = Form(...)):
    job_id = uuid.uuid4().hex[:8]
    job_dir = os.path.join(STORAGE, job_id)
    assets_dir = os.path.join(job_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    download_folder(folder_url, assets_dir)
    files = index_assets(assets_dir)

    aso, description = [], ""
    for p in files.get("texts", []):
        name = os.path.basename(p).lower()
        if "aso" in name:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                aso = [x.strip() for x in f if x.strip()]
        if name.startswith(("desc", "description")):
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                description = f.read().strip()

    game_name = _guess_game_name(aso, description, fallback=f"Job {job_id}")
    lang = os.getenv("WHISPER_LANG", "tr")

    meta = {
        "job_id": job_id,
        "game_name": game_name,
        "lang": lang,
        "files": files,
        "aso_keywords": aso,
        "description": description,
    }
    with open(os.path.join(job_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    run_pipeline(job_dir)
    return RedirectResponse(url=f"/ui/{job_id}", status_code=303)

@app.get("/ui/{job_id}", response_class=HTMLResponse)
def ui_results(request: Request, job_id: str):
    job_dir = os.path.join(STORAGE, job_id)
    results_dir = os.path.join(job_dir, "results")
    if not os.path.isdir(results_dir):
        raise HTTPException(status_code=404, detail="Results not found")

    def jload(name, default=None):
        p = os.path.join(results_dir, name)
        return json.load(open(p, "r", encoding="utf-8")) if os.path.isfile(p) else default

    summary   = jload("summary.json", {})
    captions  = jload("captions.json", {})
    scores    = jload("scores.json", {})
    trends    = jload("trends.json", {"terms": []})
    scenes    = jload("scenes.json", [])
    state     = jload("state.json", {"errors":[]})
    cu        = jload("content_understanding.json", {})
    vision_json = jload("vision.json", {})

    vision_caps = []
    if isinstance(vision_json, dict) and "captions" in vision_json:
        vision_caps = vision_json["captions"]
    elif isinstance(cu, dict):
        if "vision" in cu and isinstance(cu["vision"], dict) and "captions" in cu["vision"]:
            vision_caps = cu["vision"]["captions"]
        elif "captions" in cu:
            vision_caps = cu["captions"]

    import glob
    frames = sorted(glob.glob(os.path.join(results_dir, "frames", "*.jpg")))[:8]
    bundle_ok = os.path.isfile(os.path.join(results_dir, "bundle.zip"))

    meta_path = os.path.join(job_dir, "meta.json")
    game_name = ""
    if os.path.isfile(meta_path):
        try:
            game_name = json.load(open(meta_path, "r", encoding="utf-8")).get("game_name", "")
        except Exception:
            pass

    return templates.TemplateResponse("results.html", {
        "request": request,
        "ui_title": UI_TITLE,
        "job_id": job_id,
        "game_name": game_name,
        "summary": summary,
        "captions": captions,
        "scores": scores,
        "trends": trends.get("terms", []),
        "vision_caps": vision_caps,
        "scenes": scenes,
        "frames": [f"/jobs/{job_id}/files/results/frames/{os.path.basename(x)}" for x in frames],
        "bundle_ok": bundle_ok,
        "errs": state.get("errors", []),
    })

@app.get("/jobs/{job_id}/files/{path:path}")
def serve_result(job_id: str, path: str):
    fp = os.path.join(STORAGE, job_id, path)
    if not os.path.isfile(fp):
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(fp)

# --- API (korunur) ---
@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs", "ui": "/ui"}

@app.post("/ingest", response_model=IngestResponse)
def ingest(req: IngestFolderRequest = Body(...)):
    job_id = uuid.uuid4().hex[:8]
    job_dir = os.path.join(STORAGE, job_id)
    assets_dir = os.path.join(job_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    download_folder(req.folder_url, assets_dir)
    files = index_assets(assets_dir)

    aso, description = [], ""
    for p in files.get("texts", []):
        name = os.path.basename(p).lower()
        if "aso" in name:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                aso = [x.strip() for x in f if x.strip()]
        if name.startswith(("desc", "description")):
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                description = f.read().strip()

    meta = {
        "job_id": job_id,
        "game_name": req.game_name,
        "lang": req.lang,
        "files": files,
        "aso_keywords": aso,
        "description": description,
    }
    with open(os.path.join(job_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return {"job_id": job_id, "assets": files}

@app.post("/run")
def run(req: RunRequest = Body(...)):
    job_dir = os.path.join(STORAGE, req.job_id)
    if not os.path.isdir(job_dir):
        raise HTTPException(status_code=404, detail="job not found")
    run_pipeline(job_dir)
    return {"job_id": req.job_id, "status": "done"}

@app.get("/jobs/{job_id}/bundle")
def bundle(job_id: str):
    job_dir = os.path.join(STORAGE, job_id)
    bundle_path = os.path.join(job_dir, "results", "bundle.zip")
    if not os.path.isfile(bundle_path):
        raise HTTPException(status_code=404, detail="bundle not found")
    return FileResponse(bundle_path, filename=f"{job_id}_bundle.zip")
