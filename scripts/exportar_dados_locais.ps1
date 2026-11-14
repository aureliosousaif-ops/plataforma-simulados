# ============================================================
# EXPORTA OS DADOS LOCAIS (SQLITE) PARA UM JSON
# ============================================================
# Gera o arquivo dados_producao.json com usuários, provas,
# questões, alternativas, imagens, textos-base, simulados e
# respostas. O SQLite original NÃO é alterado.
#
# O arquivo contém hashes de senha, por isso está no .gitignore
# e NUNCA deve ser enviado ao GitHub.
# ============================================================

$ErrorActionPreference = 'Stop'

$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$python = Join-Path $raiz '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    throw "Python do ambiente virtual não encontrado em $python"
}

Write-Host '==> Exportando dados locais (SQLite)'

& $python -X utf8 manage.py dumpdata `
    --natural-foreign `
    --natural-primary `
    --exclude contenttypes `
    --exclude auth.permission `
    --exclude auth.group `
    --exclude sessions `
    --exclude admin.logentry `
    --indent 2 `
    -o dados_producao.json

if ($LASTEXITCODE -ne 0) {
    throw 'Falha ao exportar os dados.'
}

$arquivo = Join-Path $raiz 'dados_producao.json'
$tamanho = [math]::Round((Get-Item $arquivo).Length / 1KB, 1)

Write-Host "==> Arquivo gerado: $arquivo ($tamanho KB)"
Write-Host '==> O SQLite local permanece intacto.'
Write-Host ''
Write-Host 'Próximo passo: scripts\carregar_dados_render.ps1 -DatabaseUrl "<URL externa do Render>"'
