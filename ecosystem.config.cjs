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

function resolvePython() {
  const venvPython = path.resolve(__dirname, '.venv/bin/python');
  if (fs.existsSync(venvPython)) {
    return venvPython;
  }
  return './.venv/bin/python';
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
      script: resolvePython(),
      args: '-m uvicorn orchestrator.main:app --app-dir orchestrator/src --host 127.0.0.1 --port 8107',
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
      script: resolvePython(),
      args: '-m uvicorn teeth_analyzer.main:app --app-dir services/teeth_analyzer/src --host 127.0.0.1 --port 8108',
      interpreter: 'none',
      instances: 1,
      autorestart: true,
      max_memory_restart: '1536M',
      env: {
        TEETH_ANALYZER_HOST: '127.0.0.1',
        TEETH_ANALYZER_PORT: '8108',
        PYTHONUNBUFFERED: '1',
      },
    },
    {
      name: 'daantshaant-diagnosis',
      cwd: '.',
      script: resolvePython(),
      args: '-m uvicorn diagnosis.main:app --app-dir services/diagnosis/src --host 127.0.0.1 --port 8109',
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
