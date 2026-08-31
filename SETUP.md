# DaantShaant Development Environment Setup

## ✅ Setup Completed Successfully

This document describes the production-grade development environment setup for the DaantShaant project.

## Environment Details

- **Python Version**: 3.12.11
- **Package Manager**: uv (v0.7.13)
- **Virtual Environment**: `.venv` (created with `uv venv`)
- **Operating System**: Windows
- **Repository**: https://github.com/Develosphere/DaantShant.git

## Project Structure

```
DaantShaant/
├── apps/
│   └── web/                          # Next.js frontend (camera + live video)
├── orchestrator/                     # API gateway (port 8000)
│   ├── src/orchestrator/
│   │   ├── main.py                  # FastAPI app with CORS
│   │   ├── pipeline.py              # Teeth analysis pipeline
│   │   ├── live_session.py          # WebSocket handler
│   │   └── config.py
│   └── pyproject.toml
├── services/
│   ├── teeth_analyzer/              # Vision inference service (port 8001)
│   │   ├── src/teeth_analyzer/
│   │   │   ├── main.py             # FastAPI app
│   │   │   ├── inference.py        # Main analysis logic
│   │   │   ├── preprocess.py       # OpenCV image processing
│   │   │   ├── config.py
│   │   │   └── backends/
│   │   │       ├── gemini.py       # Gemini Flash vision API
│   │   │       └── stub.py         # Offline fallback
│   │   └── pyproject.toml
│   └── diagnosis/                   # Clinical classification (port 8002)
│       ├── src/diagnosis/
│       │   ├── main.py             # FastAPI app
│       │   ├── classifier.py       # Rule-based condition mapping
│       │   └── config.py
│       └── pyproject.toml
├── packages/
│   └── dantshaant_common/          # Shared schemas and HTTP clients
│       ├── src/dantshaant_common/
│       │   ├── schemas.py          # Pydantic models
│       │   └── clients.py          # Service clients
│       └── pyproject.toml
├── specs/                           # OpenAPI contracts (source of truth)
│   ├── orchestrator.openapi.yaml
│   ├── teeth_analyzer.openapi.yaml
│   ├── diagnosis.openapi.yaml
│   └── live_session.protocol.md
├── scripts/                         # PowerShell automation
│   ├── start-services.ps1          # Start all backend services
│   ├── install-deps.ps1
│   ├── recreate-venv.ps1
│   └── fix-numpy-opencv.ps1
├── docs/planning/
│   └── MODELS.md                   # Model roadmap (LoRA/QLoRA)
├── .env                            # Environment configuration
├── .env.example                    # Template
├── requirements.txt                # Editable installs
├── constraints.txt                 # NumPy 1.x constraint for OpenCV
└── pyproject.toml files            # Per-service dependencies
```

## Dependencies Installed

All dependencies were installed using `uv pip install -r requirements.txt -c constraints.txt`:

### Core Services (Editable)
- `dantshaant-common` (0.1.0) - Shared types and HTTP clients
- `dantshaant-orchestrator` (0.1.0) - API gateway
- `dantshaant-teeth-analyzer` (0.1.0) - Vision inference
- `dantshaant-diagnosis` (0.1.0) - Clinical classification

### Key Dependencies
- **FastAPI** (0.136.3) - Web framework
- **Uvicorn** (0.48.0) - ASGI server
- **Pydantic** (2.13.4) - Data validation
- **httpx** (0.28.1) - Async HTTP client
- **NumPy** (1.26.4) - Constrained to <2.0 for OpenCV compatibility
- **OpenCV** (4.9.0.80) - Image processing
- **Pillow** (12.2.0) - Image handling
- **google-generativeai** (0.8.6) - Gemini API client

## Setup Steps Executed

1. ✅ Cloned repository from GitHub
2. ✅ Created virtual environment: `uv venv`
3. ✅ Installed all dependencies: `uv pip install -r requirements.txt -c constraints.txt`
4. ✅ Created `.env` file from `.env.example`
5. ✅ Started all three backend services
6. ✅ Verified service health and connectivity

## Running the Project

### Backend Services

All three services are currently running:

```powershell
# Teeth Analyzer (port 8001)
.\.venv\Scripts\uvicorn teeth_analyzer.main:app --host 0.0.0.0 --port 8001

# Diagnosis (port 8002)
.\.venv\Scripts\uvicorn diagnosis.main:app --host 0.0.0.0 --port 8002

# Orchestrator (port 8000)
.\.venv\Scripts\uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000
```

**Or use the convenience script:**
```powershell
.\scripts\start-services.ps1
```

### Frontend (Next.js)

```powershell
cd apps\web
npm install
npm run dev
```

Open http://localhost:3000

## Service Endpoints

- **Orchestrator**: http://127.0.0.1:8000
  - Health: http://127.0.0.1:8000/health
  - Docs: http://127.0.0.1:8000/docs
  - Pipeline: `POST /v1/teeth/analyze`
  - WebSocket: `ws://127.0.0.1:8000/v1/live/session`

- **Teeth Analyzer**: http://127.0.0.1:8001
  - Health: http://127.0.0.1:8001/health
  - Docs: http://127.0.0.1:8001/docs
  - Analyze: `POST /v1/analyze`

- **Diagnosis**: http://127.0.0.1:8002
  - Health: http://127.0.0.1:8002/health
  - Docs: http://127.0.0.1:8002/docs
  - Diagnose: `POST /v1/diagnose`

## Teeth Analysis Pipeline Explained

### Architecture Overview

The system uses a **3-tier microservices architecture**:

```
Client → Orchestrator → Teeth Analyzer → Diagnosis → Response
```

### 1. Teeth Analyzer Service (Vision Inference)

**Location**: `services/teeth_analyzer/`

**Purpose**: Analyzes dental images and extracts visual findings

**Pipeline Flow**:

1. **Image Preprocessing** (`preprocess.py`):
   - Decodes base64 image using OpenCV or Pillow
   - **Quality Assessment**:
     - Blur detection (Laplacian variance)
     - Brightness analysis
     - Size validation
   - **Normalization**:
     - Resize to max 1024px
     - CLAHE (Contrast Limited Adaptive Histogram Equalization)
   - Encodes to JPEG (85% quality)

2. **Vision Backend** (`backends/`):
   - **Gemini Backend** (`gemini.py`):
     - Uses Google Gemini 2.0 Flash vision model
     - Sends structured prompt for dental analysis
     - Returns JSON with visual findings
     - Labels: `healthy_tissue`, `plaque_detected`, `tartar`, `cavity_suspect`, `cavity_advanced`, `gingivitis_signs`, `gum_disease_severe`, `discoloration`, `missing_or_damaged_teeth`
   - **Stub Backend** (`stub.py`):
     - Offline fallback for development
     - Returns deterministic mock findings

3. **Response**:
   - `analysis_id` (UUID)
   - `findings[]` - Array of `VisualFinding` objects
   - `overall_quality_score` - Image quality (0-1)
   - `model_id` - Which model was used
   - `inference_ms` - Processing time

### 2. Diagnosis Service (Clinical Classification)

**Location**: `services/diagnosis/`

**Purpose**: Maps visual findings to clinical conditions and action triggers

**Classification Logic** (`classifier.py`):

1. **Quality Gate**:
   - If quality score < 0.5 → `UNKNOWN` + request clearer photo

2. **Primary Finding Selection**:
   - Filters out healthy findings
   - Prioritizes by severity (gum disease > cavity > plaque)
   - Uses confidence scores as tiebreaker

3. **Condition Mapping**:
   ```python
   Visual Label → Clinical Condition
   ├── healthy_tissue → HEALTHY
   ├── plaque_detected/tartar → PLAQUE_TARTAR
   ├── cavity_suspect → EARLY_CAVITY
   ├── cavity_advanced → ADVANCED_CAVITY
   ├── gingivitis_signs → GINGIVITIS
   ├── gum_disease_severe → SEVERE_GUM_DISEASE
   └── discoloration → DISCOLORATION
   ```

4. **Confidence Thresholds**:
   - Each condition has a minimum confidence threshold
   - If not met → downgrade to `UNKNOWN`

5. **Severity & Action Triggers**:
   ```python
   Condition → (Severity, Action)
   ├── HEALTHY → (NONE, maintenance_reminder)
   ├── PLAQUE_TARTAR → (MILD, product_suggest_brushing)
   ├── EARLY_CAVITY → (MODERATE, product_dentist_2_weeks)
   ├── ADVANCED_CAVITY → (HIGH, dentist_urgent_1_week)
   ├── GINGIVITIS → (MODERATE, antibacterial_dentist)
   ├── SEVERE_GUM_DISEASE → (CRITICAL, immediate_dentist)
   └── DISCOLORATION → (NONE, whitening_product)
   ```

### 3. Orchestrator Service (API Gateway)

**Location**: `orchestrator/`

**Purpose**: Coordinates the full analysis pipeline

**Pipeline** (`pipeline.py`):

1. Receives image from client
2. Calls Teeth Analyzer → gets visual findings
3. Calls Diagnosis with findings → gets clinical assessment
4. Returns combined response

**Features**:
- CORS middleware for web frontend
- WebSocket support for live video streaming
- Health checks for downstream services
- Error handling and retry logic

## Environment Configuration

The `.env` file contains:

```bash
# Orchestrator
ORCHESTRATOR_HOST=0.0.0.0
ORCHESTRATOR_PORT=8000
ORCHESTRATOR_TEETH_ANALYZER_URL=http://127.0.0.1:8001
ORCHESTRATOR_DIAGNOSIS_URL=http://127.0.0.1:8002

# Teeth Analyzer
TEETH_ANALYZER_PORT=8001
TEETH_ANALYZER_BACKEND=gemini          # or "stub" for offline
TEETH_ANALYZER_GEMINI_API_KEY=         # Add your Gemini API key here
TEETH_ANALYZER_GEMINI_MODEL=gemini-2.0-flash
TEETH_ANALYZER_FALLBACK_TO_STUB=false
TEETH_ANALYZER_REJECT_LOW_QUALITY=false

# Diagnosis
DIAGNOSIS_PORT=8002

# Frontend
NEXT_PUBLIC_ORCHESTRATOR_URL=http://127.0.0.1:8000
NEXT_PUBLIC_ORCHESTRATOR_WS=ws://127.0.0.1:8000
```

## Current System Status

✅ **All services running and healthy**

```json
{
  "status": "ok",
  "service": "orchestrator",
  "version": "0.2.0",
  "dependencies": {
    "teeth_analyzer": "ok",
    "diagnosis": "ok"
  }
}
```

## Image Analysis Technology

### Current Implementation

- **Backend**: Gemini 2.0 Flash (Google's multimodal vision model)
- **Fallback**: Stub backend for offline development
- **No local ML models** - uses external API

### Image Processing (OpenCV)

- **Quality Assessment**: Blur detection, brightness analysis
- **Preprocessing**: Resize, CLAHE enhancement
- **Format**: JPEG encoding at 85% quality

### Future Roadmap (from `docs/planning/MODELS.md`)

- **Phase 2**: LoRA/QLoRA fine-tuning on LLaVA
- **Phase 3**: Hybrid RAG for recommendations
- **Phase 4**: MCP tools integration

## Camera/Upload Handling

**Frontend** (`apps/web/`):
- Next.js application
- Camera capture via browser APIs
- WebSocket for live video streaming
- HTTP POST for single image analysis

**Orchestrator Routes**:
- `POST /v1/teeth/analyze` - Single image analysis
- `WebSocket /v1/live/session` - Live video stream

## Known Issues & Fixes

### NumPy/OpenCV Compatibility

**Issue**: OpenCV 4.9 requires NumPy 1.x (breaks with NumPy 2.x)

**Solution**: Enforced via `constraints.txt`:
```
numpy>=1.26.4,<2.0.0
opencv-python-headless==4.9.0.80
```

**Recovery Script**: `.\scripts\fix-numpy-opencv.ps1`

## Development Workflow

### Spec-Driven Development

1. Modify OpenAPI specs in `specs/*.openapi.yaml`
2. Update shared schemas in `packages/dantshaant_common/src/dantshaant_common/schemas.py`
3. Implement in service code
4. Test via `/docs` endpoints

### Testing Services

```powershell
# Test teeth analyzer
curl -UseBasicParsing http://127.0.0.1:8001/health

# Test diagnosis
curl -UseBasicParsing http://127.0.0.1:8002/health

# Test orchestrator
curl -UseBasicParsing http://127.0.0.1:8000/health

# Full pipeline test (requires base64 image)
curl -X POST http://127.0.0.1:8000/v1/teeth/analyze `
  -H "Content-Type: application/json" `
  -d '{"user_id":"...","image_base64":"...","locale":"en"}'
```

## Session Logging

Analysis sessions are logged to:
```
orchestrator/data/sessions/sessions.jsonl
```

## Blockers & Warnings

### ⚠️ Gemini API Key Required

The teeth analyzer is configured to use Gemini but **no API key is set**.

**To enable Gemini vision**:
1. Get API key from https://aistudio.google.com/apikey
2. Add to `.env`:
   ```
   TEETH_ANALYZER_GEMINI_API_KEY=your_key_here
   ```
3. Restart teeth analyzer service

**Current behavior**: Will fail on analysis unless `TEETH_ANALYZER_FALLBACK_TO_STUB=true`

### ✅ No Other Blockers

- All dependencies installed successfully
- All services start without errors
- Service connectivity verified
- No missing environment variables (except optional Gemini key)
- No import/module errors
- No broken paths

## Next Steps

1. **Add Gemini API key** to enable real vision analysis
2. **Install frontend dependencies**: `cd apps\web && npm install`
3. **Start frontend**: `npm run dev`
4. **Test full pipeline** with camera or image upload
5. **Review OpenAPI specs** in `specs/` directory
6. **Explore MCP integration** (Phase 4 roadmap)

## Useful Commands

```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install new dependency
uv pip install package-name

# List installed packages
uv pip list

# Recreate environment
.\scripts\recreate-venv.ps1

# Start all services
.\scripts\start-services.ps1

# View service logs
# (Check the PowerShell windows opened by start-services.ps1)
```

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Client (Browser)                        │
│              Camera Capture / Image Upload                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Orchestrator (Port 8000)                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  POST /v1/teeth/analyze                              │  │
│  │  WebSocket /v1/live/session                          │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────┬──────────────────────┬───────────────────────┘
               │                      │
               ▼                      ▼
┌──────────────────────────┐  ┌──────────────────────────────┐
│  Teeth Analyzer (8001)   │  │   Diagnosis (8002)           │
│  ┌────────────────────┐  │  │  ┌────────────────────────┐  │
│  │ 1. Preprocess      │  │  │  │ 1. Quality Gate        │  │
│  │    - Decode        │  │  │  │ 2. Primary Finding     │  │
│  │    - Quality Check │  │  │  │ 3. Condition Mapping   │  │
│  │    - Normalize     │  │  │  │ 4. Threshold Check     │  │
│  │    - CLAHE         │  │  │  │ 5. Severity & Action   │  │
│  │ 2. Vision Backend  │  │  │  └────────────────────────┘  │
│  │    - Gemini API    │  │  │                              │
│  │    - Stub Fallback │  │  │  Rule-based Classifier       │
│  │ 3. Visual Findings │  │  │  (No ML models)              │
│  └────────────────────┘  │  └──────────────────────────────┘
│                          │
│  OpenCV + Gemini Flash   │
└──────────────────────────┘
```

---

**Setup completed by**: Kiro AI Assistant  
**Date**: May 27, 2026  
**Environment**: Windows, Python 3.12.11, uv 0.7.13
