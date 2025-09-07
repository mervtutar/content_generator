# AI Instagram Content Generator — Multi-Agent System

This project is a multi-agent system that generates **Instagram-ready content** from gameplay videos and screenshots.  
It ingests a Google Drive folder, analyzes content and trends, generates captions and hashtags, applies quality control, and serves results through a FastAPI-based UI.

---

## 🚀 Features

- **FastAPI UI** (`/ui`) — paste a Google Drive folder link, the system runs end-to-end automatically.
- **Content Understanding Agent**
  - `ffmpeg` for video scene & keyframe extraction
  - **Whisper** (optional) for transcripts / SRT
  - **BLIP** (Salesforce/blip-image-captioning-base) for frame captions & lightweight tag extraction
- **Trend Analysis Agent**
  - Seeds from ASO keywords + description
  - **Google Trends / pytrends** 
  - **TrendFit score**: Sentence-Transformers (`all-MiniLM-L6-v2`) for caption ↔ trend alignment
- **Generation Agent (LLM)**
  - **Gemini** (default: `gemini-2.5-flash`) generates multiple caption/hashtag variants
- **Quality Control Agent**
  - Text: length bands, hashtag count, repetition/spam, banned terms
  - Media: resolution, aspect ratio, duration, bitrate (`ffprobe`)
  - Trend alignment via TrendFit score
- **Finalize Agent**
  - Selects the best variant
  - Produces hashtag list and summary
  - Packages results into `bundle.zip`

---

## 📂 Project Structure
```bash

app/
├── agents/
│   ├── content_understanding_agent.py   # video + ASR + BLIP
│   ├── trend_agent.py                   # Google Trends + TrendFit
│   ├── generation_agent_llm.py          # Gemini caption/hashtag generation
│   ├── qc_agent.py                      # quality scoring
│   └── finalize_agent.py                # packaging results
│
├── graph/
│   └── flow.py                          # state graph / orchestration
│
├── llm/
│   └── gemini_llm.py                    # Gemini wrapper
│
├── services/
│   ├── video.py                         # ffmpeg/ffprobe processing
│   ├── asr.py                           # whisper wrapper (optional)
│   └── drive.py                         # download/index helpers
│
├── templates/
│   ├── form.html                        # input form
│   └── results.html                     # results UI
│
├── main.py                              # FastAPI routes & UI
├── orchestrator.py                      # pipeline runner
├── storage/                             # job-specific working dirs (gitignored)
├── venv                                 # gitignored
├── .env                                 # gitignored
└── requirements.txt                      # dependencies
```


## ⚙️ Installation

```bash
git clone <repo-url>
cd repo
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
```
Note: ffmpeg/ffprobe must be installed on the system.

```bash
🔑 Environment Variables (.env)
WHISPER_MODEL=base
WHISPER_LANG=tr
FFMPEG_PATH = ""
FFPROBE_PATH = ""
GEMINI_API_KEY= your api key
GEMINI_MODEL=gemini-2.5-flash
STORAGE_PATH=storage
```

▶️ Run
```bash
uvicorn app.main:app --reload --port 8000
```
Open in browser:
👉 http://localhost:8000/ui

**Google Drive folder must contain:**

- gameplay.mp4

- *.jpg or *.png screenshots

- aso_keywords.txt

- description.txt


**📊 Pipeline Flow**

- Content Understanding — extract video scenes/frames + captions/tags + transcript
  
- Trend — fetch trending queries via Google Trends

- Generation — LLM (Gemini) creates multiple caption/hashtag variants

- Quality Control — scoring, possible revision loop

- Finalize — select best variant, package into bundle.zip

**✅ Sample Outputs**

- results/captions.json → generated variants

- results/scores.json → QC scores

- results/trends.json → trending terms

- results/summary.json → selected variant

- results/bundle.zip → all packaged results
