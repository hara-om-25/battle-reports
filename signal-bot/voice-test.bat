@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist config.json copy config.example.json config.json >nul
docker compose run --rm bot python bot.py -c config.json voice-test
if exist voice-test.mp3 start "" voice-test.mp3
pause
