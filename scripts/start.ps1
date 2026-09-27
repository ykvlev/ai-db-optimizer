# Запуск AI Database Optimizer (Windows): базы данных, сервер, интерфейс и браузер.
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1
# Сервер и интерфейс открываются в отдельных окнах — закройте их, чтобы остановить программу.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Say($text, $color = 'White') { Write-Host $text -ForegroundColor $color }

if (-not (Test-Path "$root\backend\.venv") -or -not (Test-Path "$root\frontend\node_modules")) {
    Say 'Программа ещё не установлена. Сначала выполните:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1' 'Red'
    exit 1
}

function Test-Url($url) {
    try { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 | Out-Null; return $true } catch { return $false }
}

# 1. Демо-базы (если Docker запущен)
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker info *> $null
    if ($LASTEXITCODE -eq 0) { Say 'Базы данных: запуск…'; docker compose -f "$root\docker\docker-compose.yml" up -d mysql postgres | Out-Null }
    else { Say 'Docker не запущен — демо-базы недоступны (программа работает и без них).' 'Yellow' }
}

# 2. Сервер
if (Test-Url 'http://127.0.0.1:8000/api/health') { Say 'Сервер уже запущен.' 'Green' }
else {
    Say 'Сервер: запуск в отдельном окне…'
    Start-Process powershell -WorkingDirectory "$root\backend" -ArgumentList '-NoExit', '-Command',
        "`$Host.UI.RawUI.WindowTitle = 'AI DB Optimizer — сервер'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"
}

# 3. Интерфейс
if (Test-Url 'http://localhost:5173') { Say 'Интерфейс уже запущен.' 'Green' }
else {
    Say 'Интерфейс: запуск в отдельном окне…'
    Start-Process powershell -WorkingDirectory "$root\frontend" -ArgumentList '-NoExit', '-Command',
        "`$Host.UI.RawUI.WindowTitle = 'AI DB Optimizer — интерфейс'; npm run dev"
}

# 4. Ждём и открываем браузер
Say 'Жду готовности…'
for ($i = 0; $i -lt 60; $i++) {
    if ((Test-Url 'http://127.0.0.1:8000/api/health') -and (Test-Url 'http://localhost:5173')) { break }
    Start-Sleep -Seconds 1
}
Start-Process 'http://localhost:5173'
Say "`nПрограмма открыта: http://localhost:5173`n" 'Cyan'
