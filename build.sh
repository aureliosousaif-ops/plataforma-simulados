#!/usr/bin/env bash
# ============================================================
# BUILD DO RENDER
# ============================================================
# Executado automaticamente a cada deploy. Instala as
# dependências, coleta os arquivos estáticos e aplica as
# migrações no PostgreSQL do Render.
# ============================================================

set -o errexit
set -o pipefail
set -o nounset

echo "==> Instalando dependências"
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "==> Coletando arquivos estáticos (WhiteNoise)"
python manage.py collectstatic --noinput

echo "==> Aplicando migrações no banco de dados"
python manage.py migrate --noinput

echo "==> Verificando configuração de produção"
python manage.py check --deploy || true

# Cria o superusuário apenas se as três variáveis estiverem
# definidas no painel do Render. Se o usuário já existir, o
# comando falha e o build continua normalmente.
if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] \
    && [ -n "${DJANGO_SUPERUSER_EMAIL:-}" ] \
    && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
    echo "==> Garantindo superusuário"
    python manage.py createsuperuser --noinput || true
fi

echo "==> Build concluído"
