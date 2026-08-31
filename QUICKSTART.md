# DaantShaant Quick Start Guide

## 🚀 Start Development (One Command)

```powershell
# Start all backend services
.\scripts\start-services.ps1
```

This opens 3 PowerShell windows running:
- Teeth Analyzer (port 8001)
- Diagnosis (port 8002)
- Orchestrator (port 8000)

## 🌐 Start Frontend

```powershell
cd apps\web
npm install  # First time only
npm run dev
```

Open http://localhost:3000

## 🔍 Quick Health Check

```powershell
# Check all services
curl -UseBasicParsing http://127.0.0.1:8000/health | ConvertFrom-Json | ConvertTo-Json

# Individual services
curl -UseBasicParsing http://127.0.0.1:8001/health  # Teeth Analyzer
curl -UseBasicParsing http://127.0.0.1:8002/health  # Diagnosis
```

## 📚 API Documentation

- Orchestrator: http://127.0.0.1:8000/docs
- Teeth Analyzer: http://127.0.0.1:8001/docs
- Diagnosis: http://127.0.0.1:8002/docs

## ⚙️ Environment Setup (Already Done)

```powershell
# Virtual environment
uv venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
uv pip install -r requirements.txt -c constraints.txt

# Configure environment
copy .env.example .env
# Edit .env to add TEETH_ANALYZER_GEMINI_API_KEY
```

## 🔑 Enable Gemini Vision (Optional)

1. Get API key: https://aistudio.google.com/apikey
2. Edit `.env`:
   ```
   TEETH_ANALYZER_GEMINI_API_KEY=your_key_here
   ```
3. Restart teeth analyzer service

Without API key, the system uses a stub backend for testing.

## 🛠️ Common Tasks

### Add Python Dependency

```powershell
# Activate environment
.\.venv\Scripts\Activate.ps1

# Install package
uv pip install package-name

# Update requirements if needed
uv pip freeze > requirements-new.txt
```

### Run Individual Service

```powershell
# Teeth Analyzer
.\.venv\Scripts\uvicorn teeth_analyzer.main:app --host 0.0.0.0 --port 8001 --reload

# Diagnosis
.\.venv\Scripts\uvicorn diagnosis.main:app --host 0.0.0.0 --port 8002 --reload

# Orchestrator
.\.venv\Scripts\uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000 --reload
```

### Test Analysis Pipeline

```powershell
# Create test image (base64 encoded)
$imageBytes = [System.IO.File]::ReadAllBytes("path\to\image.jpg")
$imageBase64 = [Convert]::ToBase64String($imageBytes)

# Test analysis
$body = @{
    user_id = "123e4567-e89b-12d3-a456-426614174000"
    image_base64 = $imageBase64
    locale = "en"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/v1/teeth/analyze" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body
```

## 📁 Project Structure

```
DaantShaant/
├── orchestrator/          # API Gateway (8000)
├── services/
│   ├── teeth_analyzer/   # Vision AI (8001)
│   └── diagnosis/        # Clinical Logic (8002)
├── packages/
│   └── dantshaant_common/ # Shared code
├── apps/web/             # Next.js frontend
├── specs/                # OpenAPI contracts
└── scripts/              # Automation scripts
```

## 🐛 Troubleshooting

### Services won't start

```powershell
# Check if ports are in use
netstat -ano | findstr "8000 8001 8002"

# Kill process if needed
taskkill /PID <process_id> /F

# Recreate virtual environment
.\scripts\recreate-venv.ps1
```

### Import errors

```powershell
# Reinstall dependencies
uv pip install -r requirements.txt -c constraints.txt --force-reinstall
```

### OpenCV/NumPy issues

```powershell
.\scripts\fix-numpy-opencv.ps1
```

## 📊 Current Status

✅ Virtual environment created (`.venv`)  
✅ All dependencies installed  
✅ Services running and healthy  
✅ Service connectivity verified  
⚠️ Gemini API key not configured (optional)

## 📖 Full Documentation

See `SETUP.md` for complete setup details and architecture explanation.

## 🔗 Useful Links

- Repository: https://github.com/Develosphere/DaantShant
- Gemini API: https://aistudio.google.com/apikey
- FastAPI Docs: https://fastapi.tiangolo.com/
- Next.js Docs: https://nextjs.org/docs
