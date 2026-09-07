// DaantShaant Production PM2 Configuration
// Target domain: https://daantshaant.codemelodies.com
//
// PM2 manages the Next.js frontend ONLY.
// FastAPI microservices (Orchestrator, Teeth Analyzer, Diagnosis)
// are managed via systemd user services:
//   ~/.config/systemd/user/daantshaant-orchestrator.service
//   ~/.config/systemd/user/daantshaant-teeth-analyzer.service
//   ~/.config/systemd/user/daantshaant-diagnosis.service

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
  ],
};
