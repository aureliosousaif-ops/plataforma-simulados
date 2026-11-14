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

O comando de start já faz o bind na porta `$PORT` exigida pelo
Render (padrão `10000`) e usa o WSGI `config.wsgi:application`.

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

> **Atenção ao migrar dados:** se você vai carregar o
> `dados_producao.json` (passo 4), **deixe as três variáveis do
> superusuário em branco**. O arquivo já contém os usuários locais,
> incluindo o superusuário; criar outro com o mesmo nome faria a
> carga falhar por duplicidade.
>
> O plano free **não oferece Shell**. Se você não preencher as
> variáveis e também não migrar os dados, crie o administrador do
> seu computador apontando para o banco do Render:
>
> ```powershell
> $env:DATABASE_URL = "<External Database URL>"
> $env:DEBUG = "False"
> .venv\Scripts\python.exe -X utf8 manage.py createsuperuser
> Remove-Item Env:\DATABASE_URL, Env:\DEBUG
> ```

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
- Rode a carga apenas uma vez, depois que o primeiro deploy
  terminar (o build já cria as tabelas com `migrate`).
- **Não preencha** `DJANGO_SUPERUSER_*` no Render se for usar este
  caminho: os usuários já vêm no arquivo.
- Se a carga falhar no meio, o banco do Render fica parcialmente
  preenchido. Nesse caso, apague o banco pelo painel e crie outro
  antes de repetir — não rode `loaddata` duas vezes.
- Ao final, o script mostra a contagem de registros do banco novo.

---

## 5. Verificar o site

Após o build terminar (status **Live**):

1. Abra `https://examix.onrender.com/` (ou o domínio mostrado no
   painel). Na primeira visita o Render pode levar cerca de
   1 minuto para acordar o serviço.
2. Confira a página inicial, o login e o painel `/admin/`.
3. Entre com o superusuário migrado (ou o criado no passo 3).
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

## 7. Backup do banco (importante no plano free)

O PostgreSQL free **não tem backup automático** e **expira 30 dias
após a criação** (com 14 dias de carência antes da exclusão).

Depois que o site estiver no ar, rode periodicamente:

```powershell
scripts\backup_render.ps1 -DatabaseUrl "<External Database URL>"
```

O arquivo é salvo em `backups/` (ignorado pelo Git e protegido por
conter hashes de senha). Para restaurar em um banco novo:

```powershell
scripts\carregar_dados_render.ps1 -DatabaseUrl "<nova URL externa>"
```

---

## 8. Limitações do plano free

- O serviço hiberna após **15 minutos** sem acesso. A primeira
  requisição depois disso demora cerca de **1 minuto**.
- O workspace tem **750 horas/mês** de instância free.
- O disco é efêmero: arquivos enviados depois do deploy (novos PDFs
  ou imagens) são perdidos em um redeploy ou reinício. O plano free
  **não permite anexar disco persistente**. Para persistir envios,
  use um plano pago e defina `MEDIA_ROOT=/var/data/media`.
  As imagens e PDFs já versionados no repositório continuam
  disponíveis porque são recriados a cada build.
- Apenas **um** PostgreSQL free por workspace, com **1 GB** fixo.
- O PostgreSQL free expira em **30 dias** e não oferece Shell nem
  backups. Para um uso contínuo, troque o banco para um plano pago
  em **examix-db → Plan** antes do vencimento (os dados são
  preservados na troca de plano).
- O plano free não permite Shell, nem escala além de uma instância.

---

## 9. Segurança

- `SECRET_KEY`, `DATABASE_URL` e credenciais ficam apenas nas
  variáveis de ambiente do Render.
- `.env`, `db.sqlite3`, `*.sqlite3`, `dados_producao.json` e
  backups `.zip` estão no `.gitignore`.
- Com `DEBUG=False`, o projeto ativa redirecionamento HTTPS,
  cookies seguros e HSTS.
