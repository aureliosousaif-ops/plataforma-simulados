# Análise técnica — Plataforma de Simulados "Examix"

> Análise **somente leitura**. Nenhum arquivo do projeto foi alterado, nenhuma migração foi executada, nenhum dado foi modificado. Este relatório é o único artefato criado.
>
> Data da análise: 05/10/2026 · Último commit: `edaed7e` (05/10/2026 10:26) · Branch: `main`

---

## 1. Resumo executivo

O projeto é uma **plataforma web de simulados** em Django, com marca "Examix", que faz algo tecnicamente difícil: **ler provas em PDF (ENEM) e transformá-las automaticamente em questões com alternativas e gabarito**, e depois aplicar simulados com correção automática, cronômetro e painel de desempenho por disciplina.

Estado geral: **arquitetura clara e código muito legível** (comentários didáticos, separação por apps, nomes em português), mas com **três problemas críticos no estado atual do working tree** (alterações não commitadas) que impedem o processamento de novas provas e zerariam a correção de novos simulados; além de **riscos operacionais sérios** (ambiente local apontando para o banco de produção, dados de usuários versionados no Git, ausência de arquivos de deploy).

Resumo por gravidade:

| Gravidade | Quantidade | Temas |
|---|---|---|
| P0 — bloqueador | 3 | importação de prova quebrada (disciplina), gabarito ignorado na gravação, banco de produção usado em desenvolvimento |
| P1 — alto | 5 | signal de perfil morto, templates órfãos com URLs inexistentes, deploy incompleto, mídia efêmera, idioma/fuso |
| P2 — médio | 8 | validação de senha inoperante, dados pessoais versionados, PDFs duplicados, ausência de testes, escala das agregações, etc. |
| P3 — baixo | 6 | código inalcançável, imports duplicados, assets órfãos, estilo, etc. |

---

## 2. Stack e ambiente

| Item | Valor |
|---|---|
| Framework | Django **6.1.1** |
| Python | 3.13.14 (venv local) |
| Autenticação | django-allauth **65.19.4** (login por usuário/senha + Google OAuth) |
| Extração de PDF | pypdf 6.19.0 |
| Banco | SQLite local (`db.sqlite3`) **ou** PostgreSQL via `DATABASE_URL` |
| Estáticos | WhiteNoise 6.12.0 + `collectstatic` (pasta `staticfiles/` gerada) |
| Servidor | gunicorn 26.2.0 (destino: Render) |
| Front-end | Bootstrap 5.3.3 via CDN + CSS próprio (`examix.css`) |
| Apps | `usuarios`, `provas`, `simulados`, `desempenho` |

Dependências completas em `requirements.txt` (23 pacotes, todos fixados por versão — bom).

---

## 3. Estrutura de pastas

```
plataforma_simulados/
├── config/            # settings, urls raiz, wsgi/asgi, view CSRF customizada
├── usuarios/          # Perfil, cadastro, login/logout, decorator de permissão, comando tornar_desenvolvedor
├── provas/            # Prova, Disciplina, Questao, Alternativa + importador.py (parser de PDF, 1.584 linhas)
├── simulados/         # Simulado, RespostaSimulado + fluxo de resposta/correção
├── desempenho/        # app só de views (models vazio) — dashboard de desempenho
├── templates/         # 19 templates (base + home + 4 subpastas)
├── static/            # examix.css, home.css*, logosistema.png, a.png*
├── staticfiles/       # saída do collectstatic (gerado)
├── media/             # PDFs de provas e gabaritos enviados
├── venv/              # ambiente virtual
├── db.sqlite3         # banco local (+ db.sqlite3.backup versionado)
├── dados_backup.json  # dump de dados (ignorado pelo Git)
├── backup_antes_limpar_usuarios.json  # dump de dados (VERSIONADO no Git)
├── .env               # segredos reais (não versionado)
└── requirements.txt
```
`*` assets não referenciados por nenhum template (ver §10).

---

## 4. Modelo de dados

**usuarios.Perfil** — 1:1 com `User`; `tipo` (`aluno` | `desenvolvedor`), `idade`, `escolaridade`, `objetivo`.

**provas.Prova** — `nome`, `tipo` (enem, exato, vestibular, concurso, ibge, outro), `ano`, `descricao`, `arquivo_pdf`, `arquivo_gabarito`, `ativa`, `status_importacao` (pendente/processando/processada/erro), `mensagem_importacao`, `data_processamento`.

**provas.Disciplina** — `nome` único.

**provas.Questao** — FK `prova`, FK `disciplina` (**obrigatória**, `PROTECT`), `numero` (único por prova), `enunciado`, `dificuldade`, `imagem`, `ativa`.

**provas.Alternativa** — FK `questao`, `letra` (A–E, única por questão), `texto`, `correta`.

**simulados.Simulado** — FK `usuario`, FK `prova` (`PROTECT`), `status`, `iniciado_em`, `finalizado_em`, `tempo_total_segundos`, `acertos`, `erros`, `percentual`.

**simulados.RespostaSimulado** — FK `simulado`, FK `questao`, FK `alternativa` (nula), `respondida`, `correta`, `iniciada_em`, `respondida_em`, `tempo_segundos`; restrição única (`simulado`, `questao`).

Boas decisões: `PROTECT` em `Simulado→Prova` e em `Questao→Disciplina` preserva histórico; `UniqueConstraint` evita duplicidade de número/letra.

---

## 5. Fluxos principais

**5.1 Cadastro e login** — `CadastroForm` (username, email, idade, escolaridade, objetivo) cria `User` + `Perfil(aluno)` e faz login automático. Login tradicional via `LoginView` (`/usuarios/login/`) e login Google via allauth (`/accounts/...`), com template próprio `templates/socialaccount/login.html`. Permissões de área administrativa via decorator `desenvolvedor_required` (`usuarios/decorators.py:5-49`).

**5.2 Pipeline de importação de prova** (`provas/views.py:139-385` + `provas/importador.py`):

1. só permite POST; 2. bloqueia reprocessamento se a prova já tem simulados (`views.py:181-193` — boa proteção); 3. exige PDF da prova e PDF do gabarito; 4. marca `processando`; 5. `extrair_texto_pdf` (pypdf); 6. `separar_questoes_generico` → localiza marcadores "QUESTÃO n" (aceita variações de acentuação), escolhe o "bloco principal" (com regra especial para o ENEM, que tem 1–5 em português + 1–5 em espanhol: `importador.py:258-404`), extrai as alternativas pela sequência A-B-C-D-E e separa o enunciado das alternativas; 7. `extrair_gabarito_generico` lê pares "nº letra"; 8. `validar_questoes_com_gabarito` reprova questões sem 5 alternativas ou sem gabarito; 9. grava no banco.

O parser é o coração do sistema e está bem pensado: tolera marcadores falsos dentro do texto, remove códigos de rodapé (`*010175AZ5*`), e move texto de apoio absorvido pela alternativa E para a próxima questão (`importador.py:745-805`, `1126-1166`).

**5.3 Simulado** — `/simulados/` (lista pública) → `iniciar` (exige login, cria `Simulado` + uma `RespostaSimulado` vazia por questão via `bulk_create`) → `responder` (uma questão por vez, `?questao=N`, salva alternativa, acerto e tempo por questão, cronômetro JS) → `finalizar_simulado` (calcula tempo, acertos, erros e percentual; não respondidas contam como erro no percentual) → `resultado` (desempenho por disciplina + revisão) → `historico` (todos os simulados, com tempo calculado em tempo real para os em andamento).

**5.4 Desempenho** — `desempenho/views.py` agrega, em Python, totais, média percentual, desempenho por disciplina e evolução ao longo dos simulados; a home (`config/urls.py:15-72`) recalcula um subconjunto dos mesmos números.

---

## 6. Estado atual do repositório e dos dados

- Branch `main`, 20 commits, remoto `https://github.com/aureliosousaif-ops/plataforma-simulados.git`.
- **4 arquivos modificados e não commitados**: `provas/importador.py` (+231/-?), `simulados/views.py` (+120), `templates/base.html`, `templates/simulados/responder.html`. É nesse estado não commitado que estão os problemas P0 descritos abaixo.
- Banco de dados local: 1 prova (ENEM 2024, status *processada*), 90 questões, 450 alternativas, 2 disciplinas, ~9 usuários, 5–6 perfis e 5 simulados finalizados.
- Nos simulados registrados, os alunos responderam entre 3 e 5 questões de 90 (percentuais de 0% a 1,11%) — vale investigar se é teste ou abandono por dificuldade de uso.
- `media/` contém 2 PDFs duplicados (prova 4,8 MB ×2; gabarito 118 KB ×2), provavelmente de reenvios do mesmo arquivo.

---

## 7. Pontos fortes

1. **Parser de PDF genérico e defensivo** — não depende de quantidade fixa de questões, trata variações de acentuação, rodapés, marcadores falsos e o layout bilíngue do ENEM.
2. **Integridade preservada** — `PROTECT` + bloqueio de reprocessamento garantem que o histórico dos alunos não seja corrompido.
3. **Segurança de base correta** — CSRF em todos os formulários, `SECURE_SSL_REDIRECT`/HSTS/cookies seguros quando `DEBUG=False`, segredos em `.env`, uploads validados como PDF, `login_required` e checagem de propriedade do simulado em todas as views sensíveis.
4. **Código legível e consistente** — nomenclatura em português, comentários explicativos, responsabilidade única por arquivo, quase nenhuma duplicação de lógica.
5. **Base de dados bem normalizada** com restrições de unicidade que evitam dados inconsistentes.
6. **UX coerente** — identidade visual própria (Examix), navbar responsiva, cronômetro, badges de status da importação e mensagens de erro amigáveis.

---

## 8. Problemas e riscos (priorizados)

### P0 — Bloqueadores

**P0.1 — Importação de provas quebrada: `disciplina` recebe string vazia**
`provas/importador.py:1473-1490` monta `dados_questao["disciplina"] = ""` quando o campo existe, e em seguida `Questao.objects.create(**dados_questao)` (`:1496`). Como `Questao.disciplina` é FK obrigatória, a criação falha (`ValueError: Field 'id' expected a number but got ''`). Resultado: **toda prova nova cai em `status_importacao='erro'`** com mensagem técnica. O comentário do código ("Não força uma disciplina específica") explica a intenção, mas a implementação não é compatível com o modelo. A prova ENEM que já existe no banco tem 2 disciplinas preenchidas — ou seja, foi importada por uma versão anterior do parser.

**P0.2 — Gabarito é ignorado na gravação: toda alternativa vira "incorreta"**
`provas/views.py:337-340` chama `importar_questoes_no_banco(prova, questoes_preparadas)` **sem passar o gabarito**. A função recalcula internamente `correta = gabarito.get(numero) == letra` (`importador.py:1525-1529`) com `gabarito = {}` → **as 5 alternativas de cada questão são gravadas com `correta=False`**, descartando o valor já calculado corretamente por `preparar_questoes` (`importador.py:1385-1397`). Efeito: qualquer simulado criado a partir de prova nova marcaria **0% para todos os alunos**, mesmo acertando. (Nos dados antigos havia 90 alternativas corretas em 450 — o comportamento era correto antes das alterações não commitadas.)

**P0.3 — Ambiente de desenvolvimento aponta para o banco de PRODUÇÃO**
`.env` (local) tem `DATABASE_URL` preenchido apontando para `dpg-dapm52g473hc73c7e3lg-a.oregon-postgres.render.com/plataforma_simulados_db` (Render/Postgres). Como `config/settings.py:189-210` prioriza `DATABASE_URL` quando ela existe, **rodar o projeto localmente opera direto sobre os dados de produção**. Qualquer `migrate`, teste manual ou script local altera dados reais de alunos — e não há nenhuma trava (confirmação, variável `AMBIENTE`, banco separado de dev). É o risco de maior impacto prático hoje.

### P1 — Alto

**P1.1 — Signal de criação de perfil é código morto**
`usuarios/signals.py` define `post_save` para criar `Perfil` automaticamente, mas **nenhum módulo importa esse arquivo** e `UsuariosConfig` não tem `ready()` (`usuarios/apps.py`). Consequência: usuários criados fora do `CadastroForm` (login Google via allauth, Django admin, superusuário criado por `createsuperuser`) ficam **sem Perfil**. Hoje o sistema tolera isso (`usuarios/decorators.py:19-30` e `context_processors.py:13-23` usam `try/except`), mas `tornar_desenvolvedor` (`usuarios/management/commands/tornar_desenvolvedor.py:44`) e o template de perfil dependem do registro. Atenção ao corrigir: `CadastroForm.save()` já cria o Perfil manualmente (`usuarios/forms.py:176-186`) — ativar o signal sem ajuste geraria `IntegrityError` (OneToOne duplicado).

**P1.2 — Templates órfãos apontando para URLs que não existem**
`provas/urls.py` expõe apenas 4 rotas (`lista`, `criar`, `detalhe`, `processar`), mas existem templates que referenciam rotas inexistentes:
- `templates/provas/disciplinas.html:33, 92, 99` → `provas:criar_disciplina`, `provas:editar_disciplina`, `provas:excluir_disciplina`
- `templates/provas/questoes.html:33, 82` → `provas:criar_questao`, `provas:alternativas`
- `templates/provas/alternativas.html:53` e `alternativas_form.html:176` → `provas:criar_alternativas`, `provas:alternativas`

Nenhuma view renderiza esses 4 templates hoje (sobra de um CRUD anterior de disciplinas/questões/alternativas). Como estão inalcançáveis, não quebram o site — mas se forem reativados, geram `NoReverseMatch` (erro 500). Decidir: remover ou reimplementar as rotas.

**P1.3 — Deploy incompleto**
Os comentários do `settings.py` falam em Render (`SECURE_PROXY_SSL_HEADER`, "log do Render", comando `criar_admin` lendo `ADMIN_*` do ambiente), mas **não existe `Procfile`, `render.yaml`, `build.sh` nem `Dockerfile`** no repositório. Sem eles não há como o Render saber o comando de start (`gunicorn config.wsgi`), o `collectstatic` e as migrações.

**P1.4 — Arquivos de mídia são efêmeros em produção**
`MEDIA_ROOT` é o sistema de arquivos local e o Django só serve mídia com `DEBUG=True` (`config/urls.py:121-126`). Em Render, o disco é efêmero: **os PDFs enviados somem a cada deploy/restart**, e não há storage externo (S3/Cloudinary) nem `STORAGES` configurado. Hoje isso não afeta o aluno (o PDF só serve para importar as questões), mas quebra o reprocessamento futuro e o histórico de arquivos.

**P1.5 — Idioma e fuso horário incompatíveis com o público**
`LANGUAGE_CODE = 'en-us'` e `TIME_ZONE = 'UTC'` (`config/settings.py:249-255`) numa plataforma brasileira: mensagens de validação do Django, telas do admin e erros de formulário aparecem em inglês, e **todos os horários** (cronômetro, histórico, datas de simulado) ficam 3 h à frente. Correção simples: `'pt-br'` e `'America/Sao_Paulo'`.

### P2 — Médio

**P2.1 — Validação de senha não faz o que o comentário diz**
`usuarios/forms.py:119-125` sobrescreve `validate_password()` para "manter a senha sem os validadores extras". No Django 6.1 esse hook **não existe mais**: o fluxo é `validate_passwords()` (confirmação) e `validate_password_for_user()` (validadores de `AUTH_PASSWORD_VALIDATORS`) — verificado no fonte instalado (`venv/Lib/site-packages/django/contrib/auth/forms.py:107-135` e `:199-244`). Logo, o método é código morto e os validadores **continuam ativos** (mínimo 8 caracteres, senha comum, só numérica). Não é falha de segurança — é só um override inoperante. O `clean_password2` (`:131-153`) também duplica a checagem nativa.

**P2.2 — Dados pessoais versionados no Git**
`git ls-files` inclui `backup_antes_limpar_usuarios.json` e `db.sqlite3.backup`, ambos com usuários (e-mails e hashes de senha). O `.gitignore` cobre `db.sqlite3` e `dados_backup.json`, mas **não essas duas cópias**. Se o repositório for público, há exposição de dados pessoais (LGPD) e material para ataque offline contra as senhas. Recomendo remover do índice e do histórico, adicionar ao `.gitignore` e rotacionar o `SECRET_KEY` se houve exposição.

**P2.3 — PDFs duplicados em `media/`**
`2024_PV_impresso_D1_CD1.pdf` e `2024_PV_impresso_D1_CD1_xakTC0f.pdf` (idênticos, 4,8 MB cada) e o gabarito em dobro (118 KB ×2) — reenvios geraram novos arquivos. Sem impacto funcional, mas ~10 MB desperdiçados e risco de confusão sobre qual arquivo é o vigente.

**P2.4 — Nenhum teste automatizado**
Os 4 `tests.py` são os stubs do Django. O parser de PDF (lógica complexa, cheia de heurísticas) e o cálculo de nota **não têm nenhuma cobertura**, e são exatamente as partes que mais mudam (as últimas alterações não commitadas são nelas). Um teste com 2–3 PDFs de exemplo + asserções sobre número de questões/alternativas/gabarito já protegeria contra regressões como P0.1 e P0.2.

**P2.5 — Falta tratamento para PDF escaneado (sem texto)**
O parser depende de texto extraível por pypdf. Prova digitalizada (imagem) retorna 0 questões e o erro exibido ao desenvolvedor é genérico ("A prova não pôde ser processada"), sem indicar a causa real. Também não há limite de tamanho de upload nem mensagem específica.

**P2.6 — Agregações feitas em Python, não no banco**
`desempenho/views.py:65-158`, `simulados/views.py:846-924` (histórico) e a home percorrem respostas em laço e fazem `count()`/`filter()` por simulado dentro do loop (N+1). Com 90 questões e poucos alunos funciona; com escala real o painel fica lento. `desempenho` inclusive não tem modelos — todo o cálculo poderia virar `annotate`/`aggregate`.

**P2.7 — Regras de negócio ausentes no simulado**
Não há **limite de tempo** (só cronômetro), **limite de tentativas** por prova (o aluno pode criar infinitos simulados da mesma prova, poluindo o histórico), opção de **abandonar/excluir** um simulado em andamento, nem aviso antes de finalizar com questões em branco (o `nao_respondidas` é calculado mas aparentemente não bloqueia). Vale decidir se são requisitos.

**P2.8 — Observabilidade mínima**
`LOGGING` (`config/settings.py:384-403`) registra só nível ERROR do logger `django` no console; não há log de aplicação, de importação de provas (sucesso/falha por arquivo) nem integração de erros (Sentry). A view CSRF customizada (`config/csrf.py`) é explicitamente temporária ("serve temporariamente para descobrir por que o celular está recebendo erro 403 CSRF") e continua ativa — bom sinal de que o 403 de celular merece ser reexaminado (hoje o tratamento é genérico, sem orientar o usuário).

### P3 — Baixo / cosmético

1. `provas/importador.py:1172-1183` — `return questoes` antes do bloco "LIMPEZA FINAL DAS ALTERNATIVAS": código inalcançável (a limpeza já é feita em `preparar_questoes`, mas o trecho morto confunde).
2. `provas/importador.py:435-440` — indentação irregular do `re.sub(...)` (funciona, mas destoa do padrão do arquivo).
3. `config/urls.py:4 e 12` — `include`/`path` importados duas vezes.
4. `static/css/home.css` (9,7 KB) e `static/images/a.png` (961 KB) **não são referenciados por nenhum template** — herança do commit "Coloca estilo da home diretamente no template" (a home hoje tem `<style>` inline).
5. `desempenho/models.py` e `admin.py` vazios (a app é só views) — ok, mas poderia ser um módulo de `simulados` em vez de app própria.
6. `AUTHENTICATION_BACKENDS` lista **apenas** o backend do allauth (`config/settings.py:313-315`). Funciona porque o backend do allauth estende `ModelBackend` (permissões e admin continuam válidos), mas depender desse detalhe é frágil — o explícito seria incluir também `django.contrib.auth.backends.ModelBackend`.
7. `SECRET_KEY = os.environ.get('SECRET_KEY')` sem fallback (`settings.py:30`) — se a variável faltar, o valor vira `None` silenciosamente em vez de falhar de forma clara.
8. Não existe `.env.example` documentando as variáveis necessárias (`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL`, `CSRF_TRUSTED_ORIGINS`, `GOOGLE_CLIENT_ID/SECRET`, `ADMIN_USERNAME/EMAIL/PASSWORD`) — hoje isso só se descobre lendo o código.
9. Bootstrap vem de CDN, sem fallback local: sem internet, o layout quebra.

---

## 9. Segurança e privacidade (resumo)

**Bem feito:** CSRF em todos os formulários; cookies `Secure` + HSTS + redirecionamento HTTPS quando `DEBUG=False`; `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` por variável de ambiente; uploads restritos a `.pdf`; todas as views de simulado exigem login **e** verificam que o simulado pertence ao usuário; área de provas restrita a `desenvolvedor`; `SECRET_KEY` e credenciais do Google fora do versionamento.

**A corrigir, por ordem:** (1) banco de produção acessível do ambiente local [P0.3]; (2) dados de usuários versionados no Git [P2.2]; (3) rotação de `SECRET_KEY`/senha do Postgres caso os backups já tenham sido publicados; (4) sem rate limiting no login/cadastro (mitigado em parte pelos validadores do Django); (5) mensagens de erro de importação gravam a exceção técnica no banco e são exibidas ao desenvolvedor — útil hoje, mas revisar antes de expor a terceiros.

---

## 10. Limitações desta análise

Não consegui **executar** o projeto para validar em runtime, porque:

- o `venv` do projeto aponta para `C:\Users\kitiz\AppData\Local\Programs\Python\Python313\python.exe` e esse caminho retorna **"Acesso negado"** para o usuário da sessão atual;
- não há `python` nem `sqlite3` no `PATH` desta sessão.

Portanto: os achados P0.1 e P0.2 foram confirmados por leitura direta do código (e do fonte do Django/allauth instalados no `venv`), não por execução; o banco atual (`db.sqlite3`) não foi consultado — os números de dados vêm de `dados_backup.json`. `manage.py check`, testes e consultas ao banco seguem pendentes de validação em um ambiente com Python acessível. Também não avaliei o visual renderizado das páginas.

---

## 11. Próximos passos sugeridos (não executados)

1. **P0.1/P0.2 (correção funcional, ~1 h):** resolver a disciplina na importação (criar/obter `Disciplina` a partir de um mapa configurável, ou tornar o campo opcional) e passar o gabarito para `importar_questoes_no_banco` (ou respeitar o campo `correta` já calculado em `preparar_questoes`). Reprocessar a prova ENEM em ambiente de teste e conferir 90 questões × 5 alternativas com 90 corretas.
2. **P0.3 (risco operacional):** separar ambientes — `DATABASE_URL` de produção só no Render; no `.env` local, deixar vazio para usar SQLite, ou usar um banco de dev distinto. Adicionar um aviso/`check` que aborte se `DEBUG=True` com host de produção.
3. **P2.2:** remover os dois dumps do Git (índice + histórico), atualizar `.gitignore` e rotacionar credenciais.
4. **P1.5:** `LANGUAGE_CODE='pt-br'` e `TIME_ZONE='America/Sao_Paulo'`.
5. **P1.1:** registrar o signal em `UsuariosConfig.ready()` **e** remover a criação manual de Perfil do formulário (ou usar `get_or_create`), evitando duplicidade.
6. **P1.3/P1.4:** criar `build.sh` + `Procfile` (ou `render.yaml`) com `migrate`, `collectstatic` e `criar_admin`; definir storage de mídia externo se o histórico de PDFs importar.
7. **P1.2 e P3.4:** decidir o destino do CRUD antigo (remover templates órfãos ou reimplementar as rotas) e apagar `home.css`/`a.png` se não forem usados.
8. **P2.4:** criar testes para o parser e para o cálculo de nota (o investimento de maior retorno neste projeto).
9. **P2.7:** definir regras de produto (tempo máximo, limite de tentativas, abandono de simulado).
10. **P2.6/P2.8:** migrar agregações para o ORM e adicionar log de importação por prova.
