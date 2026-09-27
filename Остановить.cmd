@echo off
chcp 65001 >nul
cd /d "%~dp0"
docker compose -f docker\docker-compose.yml stop
echo Программа остановлена. Данные сохранены.
timeout /t 3 >nul
