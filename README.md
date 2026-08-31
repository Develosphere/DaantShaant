# DaantShaant

**Conversational AI Oral Health Assistant** with vision-based teeth analysis, persistent chat memory, and real-time diagnosis.

## 🎯 Features

- **Conversational AI Assistant** - Natural language chat powered by LLM with **grounded dental knowledge**
- **RAG-Enhanced Responses** - Retrieval-augmented generation using curated dental knowledge base
- **Teeth Image Analysis** - Vision-based analysis using Gemini
- **Clinical Diagnosis** - Automated condition classification
- **Persistent Memory** - MongoDB-backed conversation history
- **Real-time Analysis** - WebSocket support for live video
- **Multi-language Support** - English and Urdu (planned)

## 🏗️ Architecture

```
Frontend (Next.js)
    ↓
Orchestrator (FastAPI) - Port 8000
    ├── RAG System (Local Vector Store)
    ├── Conversation Engine (Enhanced)
    └── Services Integration
        ↓
├── Teeth Analyzer (FastAPI) - Port 8001
├── Diagnosis Service (FastAPI) - Port 8002
└── MongoDB (Local) - Port 27017
```

## 📋 Prerequisites

- **Python 3.11+**
- **Node.js 18+**
- **MongoDB** (local installation)
- **Gemini API Key** (for image analysis)
- **OpenRouter API Key** (for conversational AI)

## 🚀 Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/yourusername/DaantShaant.git
cd DaantShaant
```

### 2. Setup Python Environment

```powershell
# Create virtual environment
uv venv

# Activate virtual environment
.venv\Scripts\activate

# Install dependencies
uv pip install -r requirements.txt -c constraints.txt
```

### 3. Setup MongoDB

Install MongoDB locally:
- Download from: https://www.mongodb.com/try/download/community
- Install and start MongoDB service
- Default connection: `mongodb://localhost:27017`

### 4. Configure Environment

```powershell
# Copy example environment file
copy .env.example .env

# Edit .env and add your API keys:
# - TEETH_ANALYZER_GEMINI_API_KEY (get from https://aistudio.google.com/apikey)
# - OPENROUTER_API_KEY (get from https://openrouter.ai/keys)
```

### 5. Start Backend Services

```powershell
.\scripts\start-services.ps1
```

This will start:
- **Orchestrator** on http://127.0.0.1:8000
- **Teeth Analyzer** on http://127.0.0.1:8001
- **Diagnosis Service** on http://127.0.0.1:8002

### 6. Initialize RAG Knowledge Base

```powershell
# Ingest dental knowledge documents
.\scripts\ingest-dental-knowledge.ps1
```

This will populate the RAG system with curated dental knowledge for enhanced responses.

### 7. Start Frontend

```powershell
cd apps\web
npm install
npm run dev
```

Frontend will be available at: **http://localhost:3000**

## 📚 API Documentation

Once services are running:
- **Orchestrator API**: http://127.0.0.1:8000/docs
- **RAG Management**: http://127.0.0.1:8000/docs#/RAG
- **Teeth Analyzer API**: http://127.0.0.1:8001/docs
- **Diagnosis API**: http://127.0.0.1:8002/docs

## 🧪 Testing

### Health Check

```powershell
curl http://127.0.0.1:8000/health
```

### Test Enhanced Chat

1. Open http://localhost:3000/chat
2. Ask: "Why do my gums bleed when I brush my teeth?"
3. Notice the detailed, grounded response with specific dental knowledge
4. Try: "How often should I brush my teeth?"
5. Upload a teeth image for analysis

## 📁 Project Structure

```
DaantShaant/
├── orchestrator/              # API Gateway + RAG System
│   └── src/orchestrator/
│       ├── main.py           # FastAPI app
│       ├── chat_service.py   # Chat logic
│       ├── conversation_engine.py  # Enhanced LLM responses
│       ├── intent_classifier.py    # Intent detection
│       ├── openrouter_client.py    # LLM client
│       └── rag/              # RAG Implementation
│           ├── embeddings.py     # Local embeddings
│           ├── vector_store.py   # FAISS vector store
│           ├── retrieval_service.py # Semantic search
│           └── ingest.py         # Document ingestion
├── services/
│   ├── teeth_analyzer/       # Vision analysis
│   └── diagnosis/            # Clinical classification
├── packages/
│   └── dantshaant_common/    # Shared schemas
├── apps/web/                 # Next.js frontend
├── specs/                    # OpenAPI contracts
├── data/                     # Data storage
│   ├── dental_knowledge/     # RAG knowledge base
│   └── rag/                  # Vector store files
└── scripts/                  # Automation scripts
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TEETH_ANALYZER_GEMINI_API_KEY` | Gemini API key for image analysis | Required |
| `OPENROUTER_API_KEY` | OpenRouter API key for chat | Required |
| `MONGODB_URI` | MongoDB connection string | `mongodb://localhost:27017` |
| `MONGODB_DB` | MongoDB database name | `dantshaant` |
| `ORCHESTRATOR_PORT` | Orchestrator service port | `8000` |
| `TEETH_ANALYZER_PORT` | Analyzer service port | `8001` |
| `DIAGNOSIS_PORT` | Diagnosis service port | `8002` |

### Models

- **Image Analysis**: `gemini-1.5-flash` (vision)
- **Conversational AI**: `meta-llama/llama-3.2-3b-instruct:free` (text)

## 🛠️ Development

### Run Individual Service

```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Run specific service
cd orchestrator
uvicorn orchestrator.main:app --reload --port 8000
```

### Add Python Dependency

```powershell
uv pip install package-name
# Or add it to pyproject.toml / requirements.txt
```

### Frontend Development

```powershell
cd apps\web
npm run dev    # Development server
npm run build  # Production build
npm run lint   # Lint code
```

## 🐛 Troubleshooting

### Services won't start

```powershell
# Check if ports are in use
netstat -ano | findstr "8000 8001 8002"

# Kill process if needed
taskkill /PID <process_id> /F
```

### MongoDB connection failed

```powershell
# Check MongoDB service status
net start MongoDB

# Or start manually
mongod --dbpath C:\data\db
```

### Import errors

```powershell
# Reinstall dependencies using uv
uv pip install -r requirements.txt -c constraints.txt --force-reinstall
```

### OpenCV/NumPy issues

```powershell
.\scripts\fix-numpy-opencv.ps1
```

## 📊 MongoDB Collections

The system uses 4 main collections:

- **users** - User profiles
- **conversations** - Chat conversations
- **messages** - Individual messages
- **analysis_history** - Teeth analysis records

## 🔐 Security Notes

- Never commit `.env` file (already in `.gitignore`)
- Keep API keys secure
- MongoDB runs locally (no cloud database)
- All analysis data stored locally

## 📖 Documentation

- [Setup Guide](SETUP.md) - Detailed setup instructions
- [Quick Start](QUICKSTART.md) - Fast setup guide
- [API Specs](specs/) - OpenAPI specifications

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📝 License

Confidential - DaantShaant © 2026

## 🔗 Links

- **Gemini API**: https://aistudio.google.com/apikey
- **OpenRouter**: https://openrouter.ai/keys
- **MongoDB**: https://www.mongodb.com/try/download/community

## ⚠️ Disclaimer

DaantShaant is an **awareness tool**, not a medical diagnosis system. Always consult a licensed dentist for professional evaluation and treatment.
