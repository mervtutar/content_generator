from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import os, uuid, json

from app.models.schemas import IngestFolderRequest, IngestResponse, RunRequest
from app.services.drive import download_folder, index_assets

app = FastAPI(title="Case 1 - IG Content Generator")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

APP_DIR = os.path.dirname(__file__)
STORAGE = os.path.join(APP_DIR, "..", "storage")
os.makedirs(STORAGE, exist_ok=True)

@app.post("/ingest", response_model=IngestResponse)
def ingest(req: IngestFolderRequest):
    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join(STORAGE, job_id)
    assets_dir = os.path.join(job_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    # 1) Drive klasörünü indir
    download_folder(req.folder_url, assets_dir)

    # 2) Dosyaları indeksle
    idx = index_assets(assets_dir)

    # 3) ASO ve açıklamayı (MVP için .txt) topla
    aso, desc = [], ""
    for p in idx["texts"]:
        name = os.path.basename(p).lower()
        if "aso" in name and name.endswith(".txt"):
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                aso = [x.strip() for x in f if x.strip()]
        if "desc" in name or "description" in name:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                desc = f.read().strip()

    meta = {
        "game_name": req.game_name,
        "lang": req.lang,
        "aso_keywords": aso,
        "description": desc,
        "files": idx,
    }
    os.makedirs(job_dir, exist_ok=True)
    with open(os.path.join(job_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return IngestResponse(job_id=job_id, assets=meta["files"])

from fastapi import Body, HTTPException
from app.models.schemas import RunRequest
from app.orchestrator import run_pipeline

@app.post("/run")
def run(req: RunRequest = Body(...)):
    job_dir = os.path.join(STORAGE, req.job_id)
    if not os.path.isdir(job_dir):
        raise HTTPException(status_code=404, detail="job not found")
    run_pipeline(job_dir)
    return {"job_id": req.job_id, "status": "done"}

