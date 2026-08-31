# DantShaant — Run Guide

How to set up and run the **frontend**, **backend services**, **MongoDB**, and **RAG** stack on your machine.

---

## What runs where

| Component | Port | Purpose |
| --- | --- | --- |
| **Next.js frontend** | `3000` | Scan UI (`/`) and chat UI (`/chat`) |
| **Orchestrator** | `8000` | API gateway, WebSocket live scan, chat API, RAG endpoints |
| **Teeth Analyzer** | `8001` | OpenCV preprocess + Gemini vision |
| **Diagnosis** | `8002` | Rule-based clinical classification |
| **MongoDB** | `27017` | Users, conversations, messages, analysis history |
| **FAISS RAG index** | — | Local files under `data/rag/` (loaded by orchestrator) |

```
Browser (localhost:3000)
    │
    ▼
Orchestrator :8000 ──► Teeth Analyzer :8001
    │                    Diagnosis :8002
    ├── MongoDB :27017
    └── FAISS index (data/rag/)
```

---

## Prerequisites

Install these before starting:

| Tool | Version | Notes |
| --- | --- | --- |
| **Python** | 3.11+ | 3.12 recommended |
| **Node.js** | 18+ | For the Next.js app |
| **MongoDB Community** | Latest | [Download](https://www.mongodb.com/try/download/community) |
| **Gemini API key** | — | [Google AI Studio](https://aistudio.google.com/apikey) — required for real image analysis |
| **OpenRouter API key** | — | [OpenRouter](https://openrouter.ai/keys) — required for chat |

Optional but recommended on Windows:

- **uv** — faster venv/package installs (`pip install uv` or [uv docs](https://docs.astral.sh/uv/))
- **Git** — clone the repo

All commands below assume you are in the **repo root** (folder containing `orchestrator/`, `apps/`, `scripts/`).

---

## First-time setup

### 1. Clone and enter the project

```powershell
git clone <your-repo-url>
cd DantShaant
```

### 2. Create Python virtual environment

**Option A — uv (recommended):**

```powershell
uv venv
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt -c constraints.txt
```

**Option B — standard Python:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt -c constraints.txt
```

> **Important:** Always install with `-c constraints.txt`. OpenCV requires NumPy 1.x; NumPy 2.x will break the teeth analyzer.

**Alternative install script:**

```powershell
.\scripts\install-deps.ps1
```

### 3. Configure environment variables

```powershell
copy .env.example .env
```

Edit `.env` and set at minimum:

```env
TEETH_ANALYZER_GEMINI_API_KEY=<your-gemini-key>
OPENROUTER_API_KEY=<your-openrouter-key>
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=dantshaant
```

Other useful defaults (already in `.env.example`):

| Variable | Purpose |
| --- | --- |
| `TEETH_ANALYZER_BACKEND=gemini` | Use Gemini for vision (`stub` for offline mock) |
| `TEETH_ANALYZER_FALLBACK_TO_STUB=false` | Keep `false` in dev so Gemini errors are visible |
| `TEETH_ANALYZER_GEMINI_MODEL=gemini-flash-lite-latest` | Vision model |
| `OPENROUTER_MODEL=openrouter/free` | Chat model |
| `NEXT_PUBLIC_ORCHESTRATOR_URL=http://127.0.0.1:8000` | Frontend → backend HTTP |
| `NEXT_PUBLIC_ORCHESTRATOR_WS=ws://127.0.0.1:8000` | Frontend → live WebSocket |

### 4. Start MongoDB

**Windows service:**

```powershell
net start MongoDB
```

**Or run manually:**

```powershell
mongod --dbpath C:\data\db
```

Verify:

```powershell
mongosh --eval "db.runCommand({ ping: 1 })"
```

### 5. Install frontend dependencies

```powershell
cd apps\web
npm install
cd ..\..
```

### 6. Ingest dental knowledge (RAG, first time)

Place documents in `data\dental_knowledge\` (`.md`, `.txt`, `.pdf`), then:

```powershell
.\.venv\Scripts\Activate.ps1
.\scripts\ingest-dental-knowledge.ps1
```

This builds the local FAISS index at `data\rag\faiss_index.faiss`. Skip only if the index already exists and you have not changed knowledge files.

---

## Running the project (every day)

You need **four things** running: MongoDB, three backend services, and the frontend.

### Step 1 — MongoDB

Ensure MongoDB is running (see above).

### Step 2 — Backend (all three services)

From repo root:

```powershell
.\scripts\start-services.ps1
```

This opens **three PowerShell windows**:

1. Teeth Analyzer → http://127.0.0.1:8001  
2. Diagnosis → http://127.0.0.1:8002  
3. Orchestrator → http://127.0.0.1:8000  

Wait a few seconds, then verify:

```powershell
curl http://127.0.0.1:8000/health
```

Expected: `"status": "ok"` and `"teeth_analyzer"`, `"diagnosis"`, `"mongodb"` all `"ok"`.

### Step 3 — Frontend

In a **new** terminal:

```powershell
cd apps\web
npm run dev
```

Open in browser:

| URL | Feature |
| --- | --- |
| http://localhost:3000 | Teeth scan — snapshot, live camera, file upload |
| http://localhost:3000/chat | AI dental chat (RAG + OpenRouter) |

---

## API docs and useful endpoints

| URL | Description |
| --- | --- |
| http://127.0.0.1:8000/docs | Orchestrator Swagger UI |
| http://127.0.0.1:8000/docs#/RAG | RAG ingest / query / stats |
| http://127.0.0.1:8001/docs | Teeth Analyzer |
| http://127.0.0.1:8002/docs | Diagnosis |

**Key orchestrator routes:**

| Method | Path | Use |
| --- | --- | --- |
| `GET` | `/health` | Service + dependency check |
| `POST` | `/v1/teeth/analyze` | Single image analysis pipeline |
| `WebSocket` | `/v1/live/session` | Live video scan |
| `POST` | `/v1/chat/conversation` | Start chat session |
| `POST` | `/v1/chat/message` | Send chat message |
| `GET` | `/v1/chat/conversations/{user_id}` | List conversations |
| `POST` | `/rag/ingest` | Re-ingest knowledge base |
| `GET` | `/rag/health` | RAG index status |

---

## Run services manually (without the script)

Activate the venv first:

```powershell
.\.venv\Scripts\Activate.ps1
```

Run each in its own terminal (order matters — start analyzer and diagnosis before orchestrator):

```powershell
# Terminal 1 — Teeth Analyzer
uvicorn teeth_analyzer.main:app --host 0.0.0.0 --port 8001 --reload

# Terminal 2 — Diagnosis
uvicorn diagnosis.main:app --host 0.0.0.0 --port 8002 --reload

# Terminal 3 — Orchestrator
uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Quick smoke tests

### Health

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8002/health
curl http://127.0.0.1:8000/rag/health
```

### Chat (browser)

1. Go to http://localhost:3000/chat  
2. Ask: *"Why do gums bleed when brushing?"*  
3. Response should use RAG-grounded dental knowledge (after ingest).

### Scan (browser)

1. Go to http://localhost:3000  
2. Upload a teeth photo or use the camera  
3. Confirm a diagnosis report appears (requires valid `TEETH_ANALYZER_GEMINI_API_KEY`).

---

## Stopping services

- **Frontend:** `Ctrl+C` in the `npm run dev` terminal  
- **Backend:** Close the three PowerShell windows opened by `start-services.ps1`, or `Ctrl+C` in each manual terminal  
- **MongoDB:** Leave running, or `net stop MongoDB` if you use the Windows service  

---

## Troubleshooting

### Port already in use

```powershell
netstat -ano | findstr "8000 8001 8002 3000"
taskkill /PID <process_id> /F
```

### `ModuleNotFoundError: No module named 'motor'`

The orchestrator needs MongoDB + RAG packages that are declared in `orchestrator/pyproject.toml` but may be missing if only partial deps were installed.

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -c constraints.txt
```

This installs `motor`, `pymongo`, `faiss-cpu`, `sentence-transformers`, and related RAG deps. First run can take several minutes (PyTorch download). Then restart services:

```powershell
.\scripts\start-services.ps1
```

### MongoDB connection failed

- Confirm MongoDB is running: `net start MongoDB` or `mongod`  
- Check `.env`: `MONGODB_URI=mongodb://localhost:27017`  
- Orchestrator `/health` will show `"mongodb": "error"` if unreachable  

### Teeth analyzer crashes on import (NumPy / OpenCV)

Symptoms: `ModuleNotFoundError: numpy._utils`, `cv2` errors, WebSocket live scan fails.

```powershell
# Close all uvicorn/python windows first, then:
.\scripts\fix-numpy-opencv.ps1
```

If still broken:

```powershell
.\scripts\recreate-venv.ps1
.\scripts\start-services.ps1
```

### Gemini analysis fails / always shows stub or "Healthy"

1. Set a valid key in `.env`: `TEETH_ANALYZER_GEMINI_API_KEY`  
2. Set `TEETH_ANALYZER_FALLBACK_TO_STUB=false`  
3. Restart the teeth analyzer window  
4. Check logs in the analyzer PowerShell window for API errors  

### Chat returns errors

1. Set `OPENROUTER_API_KEY` in `.env`  
2. Restart orchestrator  
3. Confirm MongoDB is up (`/health` → `"mongodb": "ok"`)  

### RAG not improving chat answers

1. Add files to `data\dental_knowledge\`  
2. Run `.\scripts\ingest-dental-knowledge.ps1`  
3. Restart orchestrator (loads FAISS on startup)  
4. Check `GET http://127.0.0.1:8000/rag/stats` for chunk count  

### Frontend cannot reach backend

- Confirm orchestrator is on port 8000  
- Confirm `.env` has `NEXT_PUBLIC_ORCHESTRATOR_URL=http://127.0.0.1:8000`  
- Restart `npm run dev` after changing `.env` (Next.js reads env at build/dev start)  

### `ModuleNotFoundError: orchestrator` / import errors

Run commands from **repo root** with venv activated. Reinstall editable packages:

```powershell
pip install -r requirements.txt -c constraints.txt
```

---

## Production build (frontend only)

```powershell
cd apps\web
npm run build
npm run start
```

Backend services still run via uvicorn as above; there is no separate production deploy script in this repo yet.

---

## Script reference

| Script | When to use |
| --- | --- |
| `scripts\start-services.ps1` | Start all three backend services |
| `scripts\ingest-dental-knowledge.ps1` | Build / refresh FAISS RAG index |
| `scripts\install-deps.ps1` | Install Python deps from `requirements.txt` |
| `scripts\fix-numpy-opencv.ps1` | Repair NumPy/OpenCV after bad installs |
| `scripts\recreate-venv.ps1` | Nuclear reset of `.venv` |

---

## Related docs

- [README.md](../README.md) — project overview  
- [QUICKSTART.md](../QUICKSTART.md) — minimal commands  
- [SETUP.md](../SETUP.md) — detailed architecture and pipeline notes  
- [PRD.md](./PRD.md) — product requirements  
- [specs/](../specs/) — OpenAPI contracts  

---

*DantShaant run guide — Windows / PowerShell primary; adapt paths for macOS/Linux (`source .venv/bin/activate`, `npm run dev` unchanged).*
