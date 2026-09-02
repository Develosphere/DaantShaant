@echo off
rem DaantShaant Windows Backend Launcher
rem Delegates to start-backends.ps1 using repository-relative path
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-backends.ps1" %*
