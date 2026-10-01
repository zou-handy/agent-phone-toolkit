@echo off
taskkill /F /IM clipboard_sync.exe >nul 2>&1
echo [OK] Clipboard sync process terminated.
timeout /t 2 >nul
