# ============================================================
# CARREGA OS DADOS EXPORTADOS NO POSTGRESQL DO RENDER
# ============================================================
# Uso:
#   scripts\carregar_dados_render.ps1 -DatabaseUrl "<URL externa>"
#
# A URL externa fica em:
#   Render > examix-db > Connect > External Database URL
#
# IMPORTANTE:
# - Rode o export primeiro: scripts\exportar_dados_locais.ps1
# - Rode apenas uma vez, com o banco do Render vazio (recém-criado).
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
$fixture = Join-Path $raiz 'dados_producao.json'

if (-not (Test-Path $python)) {
    throw "Python do ambiente virtual não encontrado em $python"
}

if (-not (Test-Path $fixture)) {
    throw 'dados_producao.json não encontrado. Rode scripts\exportar_dados_locais.ps1 antes.'
}

if ($DatabaseUrl -notmatch '^postgres') {
    throw 'A URL informada não parece ser de PostgreSQL.'
}

# Guarda os valores atuais para restaurar no final.
$anteriores = @{
    DATABASE_URL          = $env:DATABASE_URL
    DEBUG                 = $env:DEBUG
    SECRET_KEY            = $env:SECRET_KEY
    ALLOWED_HOSTS         = $env:ALLOWED_HOSTS
    CSRF_TRUSTED_ORIGINS  = $env:CSRF_TRUSTED_ORIGINS
}

try {
    $env:DATABASE_URL = $DatabaseUrl
    $env:DEBUG = 'False'
    # Valor temporário: nenhuma sessão real é criada neste processo.
    $env:SECRET_KEY = 'migracao-temporaria-apenas-para-carga'
    $env:ALLOWED_HOSTS = 'localhost,127.0.0.1'
    $env:CSRF_TRUSTED_ORIGINS = ''

    Write-Host '==> Aplicando migrações no PostgreSQL do Render'
    & $python -X utf8 manage.py migrate --noinput

    if ($LASTEXITCODE -ne 0) {
        throw 'Falha ao aplicar as migrações.'
    }

    Write-Host '==> Carregando dados_producao.json'
    & $python -X utf8 manage.py loaddata dados_producao.json

    if ($LASTEXITCODE -ne 0) {
        throw 'Falha ao carregar os dados.'
    }

    Write-Host '==> Conferindo os registros no Render'
    & $python -X utf8 scripts\contar_dados.py

    Write-Host ''
    Write-Host '==> Migração concluída.'
}
finally {
    # Restaura o ambiente para não deixar a URL do banco na sessão.
    foreach ($chave in $anteriores.Keys) {
        if ($null -eq $anteriores[$chave]) {
            Remove-Item "Env:$chave" -ErrorAction SilentlyContinue
        }
        else {
            Set-Item "Env:$chave" $anteriores[$chave]
        }
    }
}
