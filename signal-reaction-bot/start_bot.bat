@echo off
rem Прихований запуск. JAVA_HOME задано прямо тут, бо подвійний клік
rem по .bat не бачить змінних, створених через setx, до перезавантаження.
set "JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-25.0.4.101-hotspot"
set "PATH=%JAVA_HOME%\bin;%PATH%"
cd /d C:\signal-cli
start "" pythonw "C:\signal-cli\signal_reaction_bot.py"
