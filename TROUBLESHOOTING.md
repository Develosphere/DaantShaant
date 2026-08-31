# DaantShaant Troubleshooting Guide

## 🚨 Common Issues

### 1. Services Won't Start

**Problem**: `.\scripts\start-services.ps1` fails or services crash

**Solutions**:
```powershell
# Check if ports are already in use
netstat -ano | findstr "8000 8001 8002"

# Kill existing processes if needed
taskkill /PID <process_id> /F

# Recreate virtual environment using uv
rmdir /s .venv
uv venv
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt -c constraints.txt
```

### 2. MongoDB Connection Failed

**Problem**: `MongoDB connection failed` or `pymongo.errors.ServerSelectionTimeoutError`

**Solutions**:
```powershell
# Check if MongoDB service is running
net start MongoDB

# Or start manually
mongod --dbpath C:\data\db

# Check connection
mongosh --eval "db.runCommand('ping')"
```

### 3. API Key Errors

**Problem**: `OPENROUTER_API_KEY not set` or `TEETH_ANALYZER_GEMINI_API_KEY not set`

**Solutions**:
1. Copy `.env.example` to `.env`
2. Get API keys:
   - Gemini: https://aistudio.google.com/apikey
   - OpenRouter: https://openrouter.ai/keys
3. Add keys to `.env` file
4. Restart services

### 4. Import Errors

**Problem**: `ModuleNotFoundError` or import failures

**Solutions**:
```powershell
# Ensure virtual environment is activated
.\.venv\Scripts\Activate.ps1

# Reinstall dependencies using uv
uv pip install -r requirements.txt -c constraints.txt --force-reinstall

# For OpenCV/NumPy issues
.\scripts\fix-numpy-opencv.ps1
```

### 5. Frontend Won't Start

**Problem**: `npm run dev` fails or frontend not accessible

**Solutions**:
```powershell
cd apps\web

# Clear cache and reinstall
rm -rf node_modules package-lock.json
npm install

# Check Node.js version (requires 18+)
node --version

# Start development server
npm run dev
```

### 6. Image Analysis Fails

**Problem**: 503 errors when uploading images

**Solutions**:
1. Check teeth analyzer service is running (port 8001)
2. Verify Gemini API key is valid
3. Check model name in `.env`: `TEETH_ANALYZER_GEMINI_MODEL=gemini-1.5-flash`
4. Check terminal logs for specific errors

### 7. Chat Responses Are Generic

**Problem**: Getting fallback responses instead of LLM responses

**Solutions**:
1. Check OpenRouter API key is valid
2. Verify orchestrator service logs for errors
3. Verify orchestrator service logs for errors.

### 8. Conversation History Not Persisting

**Problem**: Messages disappear after refresh

**Solutions**:
1. Check MongoDB is running and accessible
2. Clear browser localStorage: `localStorage.clear()`
3. Check browser console for errors
4. Verify conversation ID in localStorage

## 🔍 Debugging Steps

### 1. Check Service Health

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8002/health
```

### 3. Check Logs

Monitor terminal windows for error messages:
- **Orchestrator**: Port 8000 terminal
- **Teeth Analyzer**: Port 8001 terminal
- **Diagnosis**: Port 8002 terminal
- **Frontend**: `npm run dev` terminal

### 4. Test Individual Components

```powershell
# Test MongoDB
mongosh dantshaant --eval "db.stats()"

# Test Gemini API
# (Check teeth analyzer terminal for Gemini errors)

# Test OpenRouter API
# (Check orchestrator terminal for OpenRouter errors)
```

## 📋 Environment Checklist

- [ ] Python 3.11+ installed
- [ ] Node.js 18+ installed
- [ ] MongoDB installed and running
- [ ] Virtual environment activated
- [ ] All dependencies installed
- [ ] `.env` file configured with valid API keys
- [ ] All services running (ports 8000, 8001, 8002)
- [ ] Frontend running (port 3000)

## 🆘 Still Need Help?

1. **Check terminal logs** for specific error messages
2. **Review configuration**: Ensure all API keys are valid
3. **Restart everything**: Stop all services and start fresh
4. **Check system requirements**: Ensure all prerequisites are met

## 📞 Error Codes

| Error | Meaning | Solution |
|-------|---------|----------|
| 503 Service Unavailable | Service not running | Start the service |
| 404 Not Found | Wrong endpoint/model | Check configuration |
| 401 Unauthorized | Invalid API key | Check API keys in `.env` |
| 500 Internal Server Error | Service crashed | Check service logs |
| Connection Refused | Service not accessible | Check if service is running |

## 🔧 Advanced Debugging

### Enable Debug Logging

Add to `.env`:
```
LOG_LEVEL=DEBUG
```

### Check Database State

```javascript
// In MongoDB shell
use dantshaant
db.users.find().pretty()
db.conversations.find().pretty()
db.messages.find().pretty()
```

### Manual API Testing

```powershell
# Test chat API
$body = '{"user_id":"test-user","text":"Hello","locale":"en"}'
Invoke-RestMethod -Uri "http://127.0.0.1:8000/v1/chat/message" -Method Post -ContentType "application/json" -Body $body
```