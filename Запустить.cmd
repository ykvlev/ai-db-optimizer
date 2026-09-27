@echo off
chcp 65001 >nul
title AI Database Optimizer
cd /d "%~dp0"

where docker >nul 2>nul || (
  echo Docker не установлен. Скачайте Docker Desktop: https://www.docker.com/products/docker-desktop/
  pause & exit /b 1
)

docker info >nul 2>nul
if errorlevel 1 (
  echo Запускаю Docker Desktop...
  start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
  for /l %%i in (1,1,90) do (
    timeout /t 2 /nobreak >nul
    docker info >nul 2>nul && goto docker_ready
  )
  echo Docker Desktop не запустился. Откройте его вручную и запустите этот файл ещё раз.
  pause & exit /b 1
)
:docker_ready

echo Запускаю программу (при первом запуске сборка займёт несколько минут)...
docker compose -f docker\docker-compose.yml up -d --build --wait
if errorlevel 1 (
  echo Не удалось запустить. Подробности: docker compose -f docker\docker-compose.yml logs app
  pause & exit /b 1
)

start "" http://localhost:8080
echo.
echo Программа открыта: http://localhost:8080
echo Остановить: Остановить.cmd
timeout /t 5 >nul
