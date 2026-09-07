// DaantShaant Production PM2 Configuration
// Target domain: https://daantshaant.codemelodies.com
//
// Candidate production ports:
//   Next.js:          3107
//   Orchestrator:     8107
//   Teeth Analyzer:   8108
//   Diagnosis:        8109

const fs = require('fs');
const path = require('path');

function resolveUvicorn(preferredRelPath, fallbackRelPath = './orchestrator/.venv/bin/uvicorn') {
  const preferred = path.resolve(__dirname, preferredRelPath);
  if (fs.existsSync(preferred)) {
    return preferred;
  }
  const fallback = path.resolve(__dirname, fallbackRelPath);
  if (fs.existsSync(fallback)) {
    return fallback;
  }
  return preferredRelPath;
}

module.exports = {
  apps: [
    {
      name: 'daantshaant-web',
      cwd: './apps/web',
      script: 'npm',
      args: 'run start -- -H 127.0.0.1 -p 3107',
      interpreter: 'none',
      instances: 1,
      autorestart: true,
      max_memory_restart: '1G',
      env: {
        NODE_ENV: 'production',
        PORT: '3107',
        HOSTNAME: '127.0.0.1',
      },
    },
    {
      name: 'daantshaant-orchestrator',
      cwd: '.',
      script: resolveUvicorn('./orchestrator/.venv/bin/uvicorn'),
      args: 'orchestrator.main:app --app-dir orchestrator/src --host 127.0.0.1 --port 8107',
      interpreter: 'none',
      instances: 1,
      autorestart: true,
      max_memory_restart: '1G',
      env: {
        ORCHESTRATOR_HOST: '127.0.0.1',
        ORCHESTRATOR_PORT: '8107',
        ORCHESTRATOR_TEETH_ANALYZER_URL: 'http://127.0.0.1:8108',
        ORCHESTRATOR_DIAGNOSIS_URL: 'http://127.0.0.1:8109',
        PYTHONUNBUFFERED: '1',
      },
    },
    {
      name: 'daantshaant-teeth-analyzer',
      cwd: '.',
      script: resolveUvicorn('./services/teeth_analyzer/.venv/bin/uvicorn'),
      args: 'teeth_analyzer.main:app --app-dir services/teeth_analyzer/src --host 127.0.0.1 --port 8108',
      interpreter: 'none',
      instances: 1,
      autorestart: true,
      max_memory_restart: '1.5G',
      env: {
        TEETH_ANALYZER_HOST: '127.0.0.1',
        TEETH_ANALYZER_PORT: '8108',
        PYTHONUNBUFFERED: '1',
      },
    },
    {
      name: 'daantshaant-diagnosis',
      cwd: '.',
      script: resolveUvicorn('./services/diagnosis/.venv/bin/uvicorn'),
      args: 'diagnosis.main:app --app-dir services/diagnosis/src --host 127.0.0.1 --port 8109',
      interpreter: 'none',
      instances: 1,
      autorestart: true,
      max_memory_restart: '512M',
      env: {
        DIAGNOSIS_HOST: '127.0.0.1',
        DIAGNOSIS_PORT: '8109',
        PYTHONUNBUFFERED: '1',
      },
    },
  ],
};
