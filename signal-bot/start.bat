@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist config.json (
  copy config.example.json config.json >nul
  echo Created config.json - fill it in and run start.bat again.
  notepad config.json
  pause
  exit /b
)
docker compose up -d
echo.
echo Bot started. Logs: docker compose logs -f bot
pause
