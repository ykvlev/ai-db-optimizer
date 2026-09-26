# Установка AI Database Optimizer (Windows). Запуск из папки проекта:
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# Повторный запуск безопасен: уже установленное пропускается.
param([switch]$NoDocker)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Say($text, $color = 'White') { Write-Host $text -ForegroundColor $color }
function Fail($text) { Say "ОШИБКА: $text" 'Red'; exit 1 }

Say "`n== AI Database Optimizer: установка ==`n" 'Cyan'

# 1. Python 3.11+
$py = $null
foreach ($cand in @('py -3', 'python')) {
    try {
        $v = & ([scriptblock]::Create("$cand -c `"import sys; print('%d.%d' % sys.version_info[:2])`"")) 2>$null
        if ($v -and [version]$v -ge [version]'3.11') { $py = $cand; break }
    } catch {}
}
if (-not $py) { Fail 'Нужен Python 3.11 или новее: https://www.python.org/downloads/ (отметьте «Add python.exe to PATH»).' }
Say "Python: найден ($py)" 'Green'

# 2. Node.js 20+
try { $node = (node --version) -replace 'v', '' } catch { $node = $null }
if (-not $node -or [version]$node -lt [version]'20.0') { Fail 'Нужен Node.js 20 или новее: https://nodejs.org (версия LTS).' }
Say "Node.js: $node" 'Green'

# 3. Сервер: окружение Python и библиотеки
Push-Location "$root\backend"
if (-not (Test-Path '.venv')) {
    Say 'Создаю окружение Python…'
    & ([scriptblock]::Create("$py -m venv .venv"))
}
Say 'Устанавливаю библиотеки сервера (1–3 минуты)…'
& .\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { Pop-Location; Fail 'pip install не выполнен.' }
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env'; Say 'Создан backend\.env — сюда можно дописать ключ GigaChat.' 'Yellow' }
Pop-Location
Say 'Сервер: готов' 'Green'

# 4. Интерфейс
Push-Location "$root\frontend"
Say 'Устанавливаю пакеты интерфейса (1–2 минуты)…'
npm install --no-fund --no-audit --loglevel=error
if ($LASTEXITCODE -ne 0) { Pop-Location; Fail 'npm install не выполнен.' }
Pop-Location
Say 'Интерфейс: готов' 'Green'

# 5. Демо-базы данных в Docker
if (-not $NoDocker) {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        Say 'Docker не найден — демо-базы пропущены. Установите Docker Desktop, если нужны демо-данные.' 'Yellow'
    } else {
        docker info *> $null
        if ($LASTEXITCODE -ne 0) {
            Say 'Docker установлен, но не запущен — откройте Docker Desktop и запустите setup ещё раз.' 'Yellow'
        } else {
            Say 'Запускаю демо-базы MySQL и PostgreSQL (первый раз — несколько минут)…'
            docker compose -f "$root\docker\docker-compose.yml" up -d
        }
    }
}

Say "`nГотово. Запуск программы:  powershell -ExecutionPolicy Bypass -File scripts\start.ps1`n" 'Cyan'
