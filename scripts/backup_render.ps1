# ============================================================
# BACKUP DO POSTGRESQL DO RENDER PARA UM ARQUIVO LOCAL
# ============================================================
# Uso:
#   scripts\backup_render.ps1 -DatabaseUrl "<URL externa do Render>"
#
# A URL externa fica em:
#   Render > examix-db > Connect > External Database URL
#
# IMPORTANTE:
# - O banco free do Render NÃO tem backup automático e expira em
#   30 dias. Rode este script periodicamente.
# - O arquivo gerado contém hashes de senha. Fica em backups/,
#   que está no .gitignore. NUNCA envie ao GitHub.
# - A URL não é exibida nem gravada em arquivo.
# - O SQLite local não é tocado.
# ============================================================

param(
    [Parameter(Mandatory = $true)]
    [string]$DatabaseUrl
)

$ErrorActionPreference = 'Stop'

$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$python = Join-Path $raiz '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    throw "Python do ambiente virtual não encontrado em $python"
}

if ($DatabaseUrl -notmatch '^postgres') {
    throw 'A URL informada não parece ser de PostgreSQL.'
}

$pasta = Join-Path $raiz 'backups'
New-Item -ItemType Directory -Force -Path $pasta | Out-Null

$carimbo = Get-Date -Format 'yyyyMMdd-HHmm'
$destino = Join-Path $pasta "render-$carimbo.json"

# Guarda os valores atuais para restaurar no final.
$anteriores = @{
    DATABASE_URL         = $env:DATABASE_URL
    DEBUG                = $env:DEBUG
    SECRET_KEY           = $env:SECRET_KEY
    ALLOWED_HOSTS        = $env:ALLOWED_HOSTS
    CSRF_TRUSTED_ORIGINS = $env:CSRF_TRUSTED_ORIGINS
}

try {
    $env:DATABASE_URL = $DatabaseUrl
    $env:DEBUG = 'False'
    # Valor temporário: nenhuma sessão real é criada neste processo.
    $env:SECRET_KEY = 'backup-temporario-apenas-para-exportacao'
    $env:ALLOWED_HOSTS = 'localhost,127.0.0.1'
    $env:CSRF_TRUSTED_ORIGINS = ''

    Write-Host '==> Exportando o banco do Render'

    & $python -X utf8 manage.py dumpdata `
        --natural-foreign `
        --natural-primary `
        --exclude contenttypes `
        --exclude auth.permission `
        --exclude auth.group `
        --exclude sessions `
        --exclude admin.logentry `
        --indent 2 `
        -o $destino

    if ($LASTEXITCODE -ne 0) {
        throw 'Falha ao exportar o banco do Render.'
    }

    $tamanho = [math]::Round((Get-Item $destino).Length / 1KB, 1)

    Write-Host "==> Backup gerado: $destino ($tamanho KB)"
}
finally {
    foreach ($chave in $anteriores.Keys) {
        if ($null -eq $anteriores[$chave]) {
            Remove-Item "Env:$chave" -ErrorAction SilentlyContinue
        }
        else {
            Set-Item "Env:$chave" $anteriores[$chave]
        }
    }
}
