# DaantShaant Setup Checklist

Follow this checklist to ensure everything is properly configured.

## ✅ Prerequisites

- [ ] Python 3.11+ installed
- [ ] Node.js 18+ installed
- [ ] MongoDB installed and running
- [ ] Git installed

## ✅ Initial Setup

- [ ] Clone repository
- [ ] Create virtual environment (`.venv`) using `uv venv`
- [ ] Activate virtual environment
- [ ] Install Python dependencies (`uv pip install -r requirements.txt -c constraints.txt`)
- [ ] Copy `.env.example` to `.env`

## ✅ API Keys

- [ ] Get Gemini API key from https://aistudio.google.com/apikey
- [ ] Get OpenRouter API key from https://openrouter.ai/keys
- [ ] Add `TEETH_ANALYZER_GEMINI_API_KEY` to `.env`
- [ ] Add `OPENROUTER_API_KEY` to `.env`

## ✅ MongoDB

- [ ] MongoDB service is running
- [ ] Can connect to `mongodb://localhost:27017`
- [ ] Database `dantshaant` will be created automatically

## ✅ Backend Services

- [ ] Run `.\scripts\start-services.ps1`
- [ ] Orchestrator running on port 8000
- [ ] Teeth Analyzer running on port 8001
- [ ] Diagnosis running on port 8002
- [ ] All services show "healthy" status

## ✅ Frontend

- [ ] Navigate to `apps\web`
- [ ] Run `npm install`
- [ ] Run `npm run dev`
- [ ] Frontend accessible at http://localhost:3000

## ✅ Testing

- [ ] Health check: `curl http://127.0.0.1:8000/health`
- [ ] Open http://localhost:3000/chat
- [ ] Send text message - should get LLM response
- [ ] Upload teeth image - should get analysis
- [ ] Refresh page - conversation should restore

## ✅ Verification

- [ ] No errors in orchestrator terminal
- [ ] No errors in teeth analyzer terminal
- [ ] No errors in diagnosis terminal
- [ ] No errors in frontend terminal
- [ ] MongoDB collections created (users, conversations, messages, analysis_history)

## 🎉 Ready!

If all checkboxes are checked, your DaantShaant installation is complete!

## 🆘 Need Help?

- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Review terminal logs for errors
- Ensure all API keys are valid
- Verify MongoDB is running
