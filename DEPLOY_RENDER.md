# Deploy do Examix no Render

Este guia descreve a implantação do projeto no Render usando o
`render.yaml` (Blueprint), sem alterar a branch `main`.

- **Repositório:** `aureliosousaif-ops/plataforma-simulados`
- **Branch de deploy:** `corrigir_processar_provas`
- **Arquivo de configuração do Django:** `config/settings.py`
- **Aplicação WSGI:** `config.wsgi:application`
- **Servidor:** Gunicorn
- **Estáticos:** WhiteNoise
- **Banco:** PostgreSQL gerenciado pelo Render

---

## 1. Pré-requisitos

- Conta no [Render](https://render.com) conectada ao GitHub.
- O repositório acima deve estar acessível para a conta.
- A branch `corrigir_processar_provas` já contém `build.sh`,
  `render.yaml` e as configurações de produção.

---

## 2. Criar o Blueprint no Render

1. No painel do Render, clique em **New +** → **Blueprint**.
2. Conecte o GitHub e selecione o repositório
   `plataforma-simulados`.
3. Selecione a branch **`corrigir_processar_provas`**.
4. O Render detecta o `render.yaml` e mostra:
   - um banco **`examix-db`** (PostgreSQL, plano free);
   - um serviço web **`examix`** (Python, plano free).
5. Clique em **Apply**.

O primeiro build executa automaticamente:

```text
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
```

---

## 3. Variáveis de ambiente

O `render.yaml` já define automaticamente:

| Variável | Origem |
|---|---|
| `SECRET_KEY` | gerada pelo Render |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `.onrender.com,localhost,127.0.0.1` |
| `DATABASE_URL` | banco `examix-db` |
| `PYTHON_VERSION` | `3.13.7` |

O `settings.py` também inclui automaticamente o domínio real do
serviço (`RENDER_EXTERNAL_HOSTNAME`) em `ALLOWED_HOSTS` e em
`CSRF_TRUSTED_ORIGINS`, então não é necessário corrigir o domínio
manualmente caso o nome `examix` já esteja em uso.

### Variáveis que você deve preencher

No painel do Render, em **examix → Environment**:

| Variável | Para que serve |
|---|---|
| `DJANGO_SUPERUSER_USERNAME` | cria o administrador no build |
| `DJANGO_SUPERUSER_EMAIL` | e-mail do administrador |
| `DJANGO_SUPERUSER_PASSWORD` | senha do administrador |
| `GOOGLE_CLIENT_ID` | opcional, login com Google |
| `GOOGLE_CLIENT_SECRET` | opcional, login com Google |

> Se as três variáveis do superusuário não forem preenchidas, o
> build continua normalmente e o administrador pode ser criado
> depois pelo **Shell** do Render com `python manage.py createsuperuser`.

---

## 4. Migrar os dados locais para o PostgreSQL (recomendado)

O SQLite local (`db.sqlite3`) **não é enviado** ao GitHub e
**não é alterado** por este processo. A migração copia os dados
para o banco do Render.

1. No Render, abra **examix-db → Connect** e copie a
   **External Database URL**.
2. No seu computador, na pasta do projeto, rode:

```powershell
# Exporta usuários, provas, questões, imagens, simulados e respostas.
scripts\exportar_dados_locais.ps1

# Carrega no PostgreSQL do Render (cole a URL quando solicitado).
scripts\carregar_dados_render.ps1 -DatabaseUrl "<External Database URL>"
```

- O arquivo `dados_producao.json` contém hashes de senha e está no
  `.gitignore`. **Não o envie ao GitHub.**
- Rode a carga apenas uma vez, com o banco do Render ainda vazio.
- Ao final, o script mostra a contagem de registros dos dois lados.

---

## 5. Verificar o site

Após o build terminar (status **Live**):

1. Abra `https://examix.onrender.com/` (ou o domínio mostrado no
   painel).
2. Confira a página inicial, o login e o painel `/admin/`.
3. Entre com o superusuário criado no passo 3.
4. Abra uma prova e um simulado para confirmar que as questões e
   as imagens carregam.

---

## 6. O que foi configurado

| Item | Arquivo |
|---|---|
| Aplicação WSGI | `config/wsgi.py` (`config.wsgi:application`) |
| Segurança e banco | `config/settings.py` |
| Build | `build.sh` |
| Blueprint | `render.yaml` |
| Mídia em produção | `config/urls.py` |
| Dados | `scripts/` |

- **WhiteNoise:** `CompressedManifestStaticFilesStorage` comprime e
  versiona os arquivos coletados em `staticfiles/`.
- **Mídia:** os arquivos de `media/` foram versionados no
  repositório para que as imagens e PDFs existentes apareçam no
  primeiro deploy. Em produção, `MEDIA_ROOT` pode ser redirecionado
  para um disco persistente com a variável `MEDIA_ROOT`
  (ex.: `/var/data/media`).
- **Banco:** `DATABASE_URL` é lida com `dj_database_url` e SSL
  obrigatório.

---

## 7. Limitações do plano free

- O serviço "hiberna" após alguns minutos sem acesso; a primeira
  requisição pode demorar ~50 segundos.
- O disco é efêmero: arquivos enviados depois do deploy (novos PDFs
  ou imagens) são perdidos em um novo deploy. Para persistir,
  use um **Disco** do Render (plano pago) e defina
  `MEDIA_ROOT=/var/data/media`.
- O PostgreSQL free expira após o período definido pelo Render;
  faça backup pelo painel antes disso.

---

## 8. Segurança

- `SECRET_KEY`, `DATABASE_URL` e credenciais ficam apenas nas
  variáveis de ambiente do Render.
- `.env`, `db.sqlite3`, `*.sqlite3`, `dados_producao.json` e
  backups `.zip` estão no `.gitignore`.
- Com `DEBUG=False`, o projeto ativa redirecionamento HTTPS,
  cookies seguros e HSTS.
