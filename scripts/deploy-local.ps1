[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('staging', 'production')][string]$Environment,
    [Parameter(Mandatory)][ValidatePattern('^ghcr\.io/ykvlev/ai-db-optimizer@sha256:[a-f0-9]{64}$')][string]$Image
)
$ErrorActionPreference = 'Stop'
$composeFile = Join-Path $PSScriptRoot '../docker/deploy.compose.yml'
$project = "science-$Environment"
$stateDirectory = Join-Path $env:LOCALAPPDATA 'ScienceDeploy'
New-Item -ItemType Directory -Force -Path $stateDirectory | Out-Null
$receipt = Join-Path $stateDirectory "$Environment.json"
if ($Environment -eq 'production') {
    $stagingReceipt = Join-Path $stateDirectory 'staging.json'
    if (!(Test-Path -LiteralPath $stagingReceipt) -or
        (Get-Content -LiteralPath $stagingReceipt -Raw | ConvertFrom-Json).image -ne $Image) {
        throw 'This image has not passed staging on this computer.'
    }
}
$passwordFile = Join-Path $stateDirectory "$Environment-db-password.txt"
if (!(Test-Path -LiteralPath $passwordFile)) {
    [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)) |
        Set-Content -LiteralPath $passwordFile -Encoding utf8 -NoNewline
}
$variableNames = @('DEPLOY_IMAGE', 'DEPLOY_PORT', 'DEPLOY_MYSQL_PORT', 'DEPLOY_POSTGRES_PORT', 'DEPLOY_DB_PASSWORD')
$previousVariables = @{}
foreach ($name in $variableNames) { $previousVariables[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
$oldImage = if (Test-Path -LiteralPath $receipt) { (Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json).image } else { $null }
function Invoke-Compose([string[]]$Arguments) {
    & docker compose --project-name $project --file $composeFile @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed with exit code $LASTEXITCODE" }
}
try {
    $env:DEPLOY_IMAGE = $Image
    $env:DEPLOY_PORT = if ($Environment -eq 'staging') { '8081' } else { '8082' }
    $env:DEPLOY_MYSQL_PORT = if ($Environment -eq 'staging') { '3308' } else { '3309' }
    $env:DEPLOY_POSTGRES_PORT = if ($Environment -eq 'staging') { '5435' } else { '5436' }
    $env:DEPLOY_DB_PASSWORD = (Get-Content -LiteralPath $passwordFile -Raw).Trim()
    Invoke-Compose -Arguments @('pull', 'app')
    Invoke-Compose -Arguments @('up', '-d', '--wait', '--wait-timeout', '300')
    $uri = "http://127.0.0.1:$($env:DEPLOY_PORT)"
    $health = Invoke-RestMethod "$uri/api/health" -TimeoutSec 15
    if ($health.status -ne 'ok') { throw 'Application health endpoint did not return ok.' }
    $page = Invoke-WebRequest $uri -TimeoutSec 15
    if ($page.Content -notmatch '<div id="root"') { throw 'Frontend did not load.' }
    @{ image = $Image; previousImage = $oldImage; checkedAt = [DateTime]::UtcNow.ToString('o'); url = $uri } |
        ConvertTo-Json | Set-Content -LiteralPath $receipt -Encoding utf8
    Write-Output "$Environment deployed and checked: $uri"
} catch {
    $failure = $_
    if ($oldImage) {
        Write-Warning 'Deployment failed; restoring the previous application image.'
        $env:DEPLOY_IMAGE = $oldImage
        Invoke-Compose -Arguments @('up', '-d', '--no-deps', '--wait', '--wait-timeout', '120', 'app')
    }
    throw $failure
} finally {
    foreach ($name in $variableNames) { [Environment]::SetEnvironmentVariable($name, $previousVariables[$name], 'Process') }
}
