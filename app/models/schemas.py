from pydantic import BaseModel
from typing import Dict, Any

class IngestFolderRequest(BaseModel):
    folder_url: str = "https://drive.google.com/drive/folders/1oC9JL4sKlNYtnhYM6JcMEc5Fm_c_T7WX?usp=drive_link"
    game_name: str = "Patrol Officer"
    lang: str = "tr"

class IngestResponse(BaseModel):
    job_id: str
    assets: Dict[str, Any]

class RunRequest(BaseModel):
    job_id: str
