#!/usr/bin/env pwsh
# Ingest dental knowledge documents into RAG system

Write-Host "🦷 DaantShaant - Ingesting Dental Knowledge" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# Check if virtual environment is activated
if (-not $env:VIRTUAL_ENV) {
    Write-Host "❌ Virtual environment not activated" -ForegroundColor Red
    Write-Host "Please run: .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
    exit 1
}

# Check if dental knowledge directory exists
$knowledgeDir = "data\dental_knowledge"
if (-not (Test-Path $knowledgeDir)) {
    Write-Host "❌ Dental knowledge directory not found: $knowledgeDir" -ForegroundColor Red
    exit 1
}

Write-Host "📁 Knowledge directory: $knowledgeDir" -ForegroundColor Green

# Count files to ingest
$files = Get-ChildItem -Path $knowledgeDir -Include "*.md", "*.txt", "*.pdf" -Recurse
Write-Host "📄 Found $($files.Count) files to ingest" -ForegroundColor Green

if ($files.Count -eq 0) {
    Write-Host "⚠️  No supported files found in $knowledgeDir" -ForegroundColor Yellow
    Write-Host "Supported formats: .md, .txt, .pdf" -ForegroundColor Gray
    exit 0
}

# List files
Write-Host "`n📋 Files to ingest:" -ForegroundColor Blue
foreach ($file in $files) {
    $relativePath = $file.FullName.Replace((Get-Location).Path + "\", "")
    Write-Host "   • $relativePath" -ForegroundColor Gray
}

Write-Host "`n🚀 Starting ingestion..." -ForegroundColor Yellow

# Run ingestion
try {
    python -m orchestrator.rag.ingest $knowledgeDir
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n✅ Ingestion completed successfully!" -ForegroundColor Green
        Write-Host "🎯 RAG system is now ready with dental knowledge" -ForegroundColor Cyan
        Write-Host "`nNext steps:" -ForegroundColor Blue
        Write-Host "1. Start the orchestrator: .\scripts\start-services.ps1" -ForegroundColor Gray
        Write-Host "2. Test RAG queries at: http://127.0.0.1:8000/docs#/RAG" -ForegroundColor Gray
        Write-Host "3. Chat with enhanced knowledge at: http://localhost:3000/chat" -ForegroundColor Gray
    } else {
        Write-Host "`n❌ Ingestion failed with exit code: $LASTEXITCODE" -ForegroundColor Red
        exit $LASTEXITCODE
    }
} catch {
    Write-Host "`n❌ Ingestion failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}