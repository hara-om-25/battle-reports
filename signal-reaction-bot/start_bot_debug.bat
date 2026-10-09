@echo off
rem Видимий запуск для діагностики: вікно НЕ закривається, видно помилки
set "JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-25.0.4.101-hotspot"
set "PATH=%JAVA_HOME%\bin;%PATH%"
cd /d C:\signal-cli
python "C:\signal-cli\signal_reaction_bot.py"
echo.
echo === Бот зупинився. Скопіюйте/сфотографуйте текст вище ===
pause
