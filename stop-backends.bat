@echo off
rem DaantShaant Windows Backend Stopper
rem Delegates to stop-backends.ps1 using repository-relative path
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-backends.ps1" %*
