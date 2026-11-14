# Homologação final — leitor de imagens do Examix

Data: 13/11/2026

## 1. Veredito

| Classificação | Quantidade | Situação |
|---|---:|---|
| **P0** — bloqueador crítico | 0 | Nenhum encontrado. |
| **P1** — alto | 1 | Mídia não é servida/persistida no deploy com `DEBUG=False`. |
| **P2** — médio/baixo | 10 | Consistência, limpeza, desempenho e higiene operacional. |

**Conclusão:** o leitor de imagens está **aprovado em desenvolvimento e nos testes automatizados**, mas **não está homologado para produção** enquanto o P1-01 não for resolvido ou comprovado como tratado pelo ambiente de deploy. Não foi encontrado P0. Nenhuma funcionalidade foi alterada nesta auditoria.

## 2. Escopo e método

Foram auditados os 10 pontos solicitados: backup, migrations/constraints, SQLite/PostgreSQL, segurança das views, permissão de desenvolvedor, persistência de mídia, imagens órfãs/sincronização, substituição de PDF, impressão/miniaturas e desempenho em PDFs grandes.

Método:

- leitura do código atual (`provas/imagens.py`, `provas/models.py`, `provas/views.py`, `provas/urls.py`, templates, `config/settings.py`, `config/urls.py`, `usuarios/decorators.py`);
- execução da suíte existente e de suítes temporárias de homologação em `.work/`;
- banco SQLite temporário em `.work/audit_migrate.sqlite3`, criado e migrado do zero;
- geração do DDL real do PostgreSQL com `schema_editor(collect_sql=True)`, sem abrir conexão;
- PDFs sintéticos com imagens JPEG embutidas e marcadores de questão;
- simulação de `DEBUG=False` para verificar o comportamento de deploy.

**Nenhum banco de produção foi acessado ou alterado.** Não há `.env`, repositório Git, PDF real do ENEM, arquivos em `media/` nem servidor PostgreSQL nesta cópia. Os artefatos da auditoria estão em `.work/`; o `db.sqlite3` local está sem registros de provas/usuários.

## 3. Resultado por item auditado

### 3.1 Integridade do backup

Arquivo: `outputs/backup-pre-imagens-2026-11-13.zip`

| Verificação | Resultado |
|---|---|
| Tamanho | 2.229.754 bytes |
| SHA-256 do zip | `476a844376faaf2e3a10cd84405ff10d9a31f513aad5613f0354313c91cf9836` |
| Entradas | 136 |
| `testzip` | OK, nenhuma entrada corrompida |
| Leitura de todo o conteúdo | OK, nenhum erro |
| Membros esperados | Todos presentes |
| `.env` / segredos | Não incluídos |
| `media/` | Ausente (pasta estava vazia) |
| `db.sqlite3` | 0 bytes |
| Migrations no backup | Até `provas/0004` (sem a 0005, como esperado) |
| Arquivos idênticos ao estado atual | 117 |
| Arquivos diferentes | 18, exatamente os alterados pela etapa de imagens + `__pycache__` |
| Restauração | Zip extraído em diretório temporário; `manage.py check` executou sem problemas; `showmigrations` mostrou 0001–0004 |

Os 18 arquivos diferentes são: `provas/admin.py`, `models.py`, `tests.py`, `urls.py`, `views.py`, `simulados/tests.py`, `simulados/views.py`, `static/css/examix.css`, `templates/provas/detalhe.html`, `templates/simulados/responder.html`, `templates/simulados/resultado.html` e 7 `.pyc` de `__pycache__`.

Conclusão: o backup é **estruturalmente íntegro e restaurável como snapshot de código**. Ele não é um backup de dados nem de mídia: o `db.sqlite3` está vazio e `media/` não foi incluído. Há 52 entradas de `__pycache__`, o que é apenas higiene (P2-01).

### 3.2 Migrations e constraints

Executado em SQLite temporário, do zero:

```text
0001_initial -> 0002 -> 0003 -> 0004 -> 0005   OK
0005 -> 0004 (rollback)                        OK
0004 -> 0005 (reaplicação)                     OK
```

O `sqlmigrate` confirmou tabelas, FKs, `CHECK` de campos positivos, unique constraints e o índice parcial:

```sql
CREATE UNIQUE INDEX "imagem_confirmada_unica"
ON "provas_imagemquestao" ("imagem_id")
WHERE "confirmada" = 1;
```

Constraints exercitadas diretamente no banco temporário:

| Cenário | Resultado |
|---|---|
| Várias associações **não confirmadas** para a mesma imagem | Permitido, como esperado |
| Duas associações **confirmadas** para a mesma imagem | Bloqueado por `IntegrityError` |
| Associação duplicada imagem/questão | Bloqueada |
| Imagem duplicada por `(prova, hash, página, índice)` | Bloqueada |
| Exclusão de questão | Remove associações em cascata |
| Exclusão de imagem/prova | Remove registros dependentes em cascata |

`manage.py check` não apontou problemas e `makemigrations --check --dry-run` retornou `No changes detected`.

### 3.3 Compatibilidade SQLite/PostgreSQL

O DDL real do backend PostgreSQL foi gerado sem conexão:

- `bigint identity` para as PKs;
- `boolean`, `timestamptz` e `double precision` para os campos correspondentes;
- FKs `DEFERRABLE INITIALLY DEFERRED`;
- unique constraints `imagem_unica_por_prova_hash_pagina` e `associacao_unica_imagem_questao`;
- índice parcial `CREATE UNIQUE INDEX "imagem_confirmada_unica" ... WHERE "confirmada"`.

O SQLite aplicou a mesma migration e as mesmas constraints. O projeto tem `psycopg==3.3.6`, `psycopg-binary==3.3.6` e `dj-database-url==3.1.2` em `requirements.txt`.

**Limitação:** não há servidor PostgreSQL local; a compatibilidade foi verificada pelo DDL e pelo comportamento SQLite, não por execução dinâmica no PostgreSQL. O risco específico de `arquivo` com `max_length=100` está no P2-09.

### 3.4 Segurança das views de extração, revisão, confirmação e remoção

Suíte temporária `audit_homologacao`: **13 testes, todos aprovados**.

| Verificação | Resultado |
|---|---|
| Anônimo em revisão, impressão, extração e ações | Redirecionado para login |
| Aluno autenticado | Redirecionado para a home e sem escrita no banco |
| Desenvolvedor | Acessa revisão (200) e impressão (200) |
| GET em endpoints de escrita | Redirecionado, sem executar ação |
| Imagem de outra prova via `imagem_id` | 404, sem associação |
| Questão de outra prova via `questao_id` | 404, sem associação |
| Confirmação/remoção de associação de outra prova | 404 |
| POST sem CSRF | 403, sem escrita |
| POST com token CSRF | Executa e confirma a associação |
| Ação desconhecida | Redireciona sem alterar dados |
| Tentativa de ignorar imagem com associação confirmada | Bloqueada |

Não foi encontrado bypass de autorização, IDOR ou ausência de CSRF nas rotas auditadas.

### 3.5 Proteção contra usuários sem perfil de desenvolvedor

Todas as views do fluxo (`processar`, `revisar_imagens`, `extrair_imagens`, `acao_imagem`, `imprimir`, além de lista/detalhe/criar) usam `@desenvolvedor_required`. O decorator:

- exige autenticação;
- exige `request.user.perfil.tipo == 'desenvolvedor'`;
- redireciona para a home quando o perfil não existe ou é de aluno.

Os testes confirmaram aluno e anônimo bloqueados sem alteração de dados. O Django Admin continua sendo um caminho separado, restrito a `is_staff`; ele permite editar `ImagemProva`/`ImagemQuestao` (ver P2-02 e P2-05).

### 3.6 Persistência de mídia em deploy

**P1-01 confirmado por teste e por código.**

Com `DEBUG=False` (settings de simulação de deploy):

```text
GET /media/provas/imagens/prod.png -> 404
GET /provas/<id>/imagens/          -> 200, mas o <img> aponta para a URL 404
```

Evidências de código:

- `config/urls.py` adiciona `static(settings.MEDIA_URL, ...)` **somente** quando `settings.DEBUG` é verdadeiro;
- `MEDIA_ROOT = BASE_DIR / 'media'`, dentro do diretório da aplicação;
- não há `STORAGES`/S3/Cloudinary configurado;
- `media/` está no `.gitignore`;
- não há `render.yaml`, `Procfile`, `build.sh` ou configuração de disco persistente no repositório;
- WhiteNoise está instalado, mas serve apenas arquivos estáticos de `STATIC_ROOT`.

Consequência: em deploy com `DEBUG=False`, os PDFs e as imagens extraídas não são servidos pela aplicação e, em filesystem efêmero (por exemplo, Render sem disco persistente), podem ser perdidos a cada deploy/restart.

### 3.7 Imagens órfãs e sincronização `ImagemQuestao` ↔ `Questao.imagem`

Suíte temporária `audit_consistencia`: **8 testes, todos aprovados**, cada um reproduzindo um cenário real.

| Cenário | Comportamento observado |
|---|---|
| Excluir `ImagemProva` | Arquivo físico permanece no storage e `Questao.imagem` continua apontando para ele |
| Excluir `Prova` | PDF e imagens permanecem no storage (órfãos) |
| Remover arquivo do disco mantendo registros | `Questao.imagens_exibicao` e a impressão continuam apontando para o link quebrado |
| Associar imagem da prova A à questão da prova B via ORM | Permitido; a imagem aparece na questão da outra prova |
| Associar/confirmar imagem marcada como `ignorada=True` | Permitido; a imagem aparece na impressão/simulado |
| Fluxo normal de confirmação/remoção | Sincroniza corretamente `Questao.imagem`; testes existentes confirmam que imagem legada manual é preservada |
| Troca de PDF | Imagens antigas continuam no banco e no disco |
| Restauração de confirmação após recriar questões | Confirmação antiga é reaplicada à questão nova de mesmo número/idioma, mesmo sendo imagem do PDF anterior |
| Falha no meio da extração | O savepoint desfaz o banco, mas arquivos já gravados podem permanecer |

Os três primeiros cenários e a associação cruzada são os achados P2-03, P2-04, P2-05 e P2-06.

### 3.8 Comportamento ao substituir o PDF

Teste reproduzindo o mecanismo usado por `processar` (`capturar_confirmacoes` → recriar questões → `restaurar_confirmacoes`):

1. PDF A com 2 imagens: extraídas 2, ambas com arquivo no disco.
2. Uma imagem é confirmada para a questão 1.
3. PDF é substituído por PDF B, com imagens diferentes.
4. Nova extração cria mais 2 imagens: total passa a 4; as 2 antigas continuam no banco e no disco.
5. Questões são recriadas com o mesmo número; a confirmação antiga é restaurada e a questão nova passa a exibir a imagem do PDF antigo.

O código não versiona imagens por hash do PDF nem remove imagens que não existem mais no PDF atual. Isso é útil para preservar confirmações legítimas ao reprocessar o mesmo PDF, mas é arriscado quando o PDF é realmente trocado. Classificado como P2-06.

### 3.9 Impressão e miniaturas

Testes aprovados:

| Verificação | Resultado |
|---|---|
| Página de impressão para desenvolvedor | 200 |
| `window.print()` e `@media print` | Presentes |
| Imagem confirmada aparece exatamente uma vez | Confirmado |
| Fallback legado não duplica a imagem confirmada | Confirmado |
| Sugestão não confirmada não aparece na impressão | Confirmado |
| CSS de impressão e classes `examix-print-question`/`examix-print-images` | Presentes |
| Tela de revisão mostra miniatura, página, índice e dimensões | Confirmado |
| Consultas com 40 imagens | Revisão: 10 consultas; impressão: 8 consultas |
| Tempo de renderização com 60 imagens | Revisão: 2,13 s e 1.599 KiB de HTML; impressão: 0,21 s e 74 KiB |

A impressão é restrita a desenvolvedores (a rota usa o mesmo decorator). Não foi possível validar visualmente o resultado em navegador/impressora; a validação foi de HTML/CSS e resposta HTTP.

**Miniaturas:** a tela usa o arquivo original (`{{ imagem.arquivo.url }}`) com apenas `max-height: 260px` no CSS. Não há geração de thumbnail. Em 60 imagens de 77,5 MiB, a revisão baixa os arquivos em resolução original no navegador (P2-07).

### 3.10 Desempenho em PDFs grandes

PDFs sintéticos com uma imagem JPEG por página e um marcador `QUESTAO n` por página. Medições em ambiente local, sem rede:

| Métrica | 40 páginas / 1,19 MiB | 60 páginas / 83,47 MiB |
|---|---:|---:|
| `extrair_imagens_pdf` | 1,52 s | 5,68 s |
| Pico de memória na extração | 4,0 MiB | 245,3 MiB |
| `mapear_marcadores_pdf` | 0,30 s | 0,62 s |
| `extrair_e_registrar_imagens` | 3,28 s | 8,27 s |
| Consultas na persistência | 82 (40 imagens) | 122 (60 imagens) |
| Sugestões criadas / tempo | 40 / 0,82 s | 60 / 1,51 s |
| `confirmar_todas_sugestoes` | 40 / 0,85 s / 283 consultas | 60 / 2,15 s |
| GET revisão | 1,08 s / 10 consultas / 854 KiB | 2,13 s / 10 consultas / 1.599 KiB |
| GET impressão | 0,13 s / 8 consultas / 54 KiB | 0,21 s / 8 consultas / 74 KiB |

Observações:

- o pico de memória da extração ficou em **~3× o tamanho das imagens** (77,5 MiB de imagens → 245,3 MiB de pico);
- a persistência faz aproximadamente **2 consultas por imagem**;
- `confirmar_todas_sugestoes` faz aproximadamente **7 consultas por associação** (283/40), com crescimento linear;
- a extração é **síncrona**, abre o PDF duas vezes (imagens e marcadores) e mantém todas as imagens em memória antes de gravar;
- o fluxo completo de imagens no `processar` somou ~15,5 s no cenário de 60 páginas grandes, sem contar a extração de texto/importação. Em PDFs reais maiores, há risco de ultrapassar o timeout padrão de 30 s do Gunicorn (não há configuração de timeout no repositório). Classificado como P2-08.

A tela de revisão mantém consultas constantes, mas o custo de banda do navegador é proporcional ao tamanho original das imagens.

## 4. Achados

### P0 — bloqueadores

Nenhum.

### P1 — alto

#### P1-01 — Mídia não é servida nem persistida no deploy

**Evidência:** `GET /media/...` retorna 404 com `DEBUG=False`; `config/urls.py` só publica `/media/` quando `DEBUG=True`; não há storage externo nem configuração de disco persistente; `media/` é ignorado pelo Git.

**Impacto:** em produção, PDFs e imagens extraídas podem aparecer quebrados para alunos e desenvolvedores, e podem ser perdidos em redeploy/restart. A feature de imagens depende inteiramente desses arquivos.

**Recomendação:** configurar disco persistente e servir `/media/` por proxy/web server, ou migrar para object storage (S3/Cloudinary/etc.); incluir a mídia no backup; validar em staging com `DEBUG=False`.

### P2 — médio/baixo

| ID | Achado | Evidência | Impacto | Recomendação |
|---|---|---|---|---|
| P2-01 | Backup não é snapshot de dados/mídia e inclui `__pycache__` | `db.sqlite3` com 0 bytes, `media/` ausente, 52 entradas de cache | Rollback restaura código, não dados nem arquivos | Excluir `__pycache__`; documentar escopo; usar backup do banco do provedor para dados |
| P2-02 | Imagem `ignorada=True` ainda pode ser associada/confirmada | POST `associar` e `confirmar` aceitam; imagem aparece na impressão | Imagem que deveria estar oculta pode ir ao simulado | Bloquear confirmação/associação de imagem ignorada na view e no helper; esconder o formulário |
| P2-03 | Exclusões não removem arquivos físicos | Excluir `ImagemProva`/`Prova` mantém arquivos; falha no meio da extração deixa arquivos | Crescimento de disco e órfãos | Signals/comando de limpeza, removendo apenas arquivos não compartilhados por hash |
| P2-04 | `Questao.imagem` pode apontar para arquivo removido/órfão | Teste removeu o arquivo e a impressão continuou com a URL | Link quebrado na impressão/simulado | Revalidar existência no storage e sincronizar ao excluir `ImagemProva` |
| P2-05 | Associação cruzada entre provas é aceita pelo ORM/Admin | `associar_imagem(imagem_A, questao_B)` confirmou e exibiu | Conteúdo de uma prova pode aparecer em outra | Validar `imagem.prova_id == questao.prova_id` no modelo/helper e limitar o Admin |
| P2-06 | Troca de PDF mantém imagens e confirmações antigas | 2 imagens → troca → 4 imagens; confirmação antiga restaurada na questão nova | Pode exibir imagem do PDF anterior em questão recriada | Versionar por hash do PDF, não restaurar confirmações quando o PDF mudar e revisar/prunar imagens obsoletas |
| P2-07 | Miniaturas baixam a imagem em resolução original | Template usa `imagem.arquivo.url`; CSS só limita altura | Revisão pesada (77,5 MiB para 60 imagens) e consumo móvel | Gerar thumbnails com Pillow e usar `loading="lazy"` |
| P2-08 | Extração síncrona, memória ~3× e consultas lineares | 60 páginas/83,5 MiB: 5,68 s e 245 MiB de pico; 2 consultas/imagem; 283 consultas para confirmar 40 | Risco de timeout de worker e pressão de memória em PDFs grandes | Processamento em background/fila, leitura em streaming, `bulk_create`, cache de marcadores; medir PDF real |
| P2-09 | `ImagemProva.arquivo` com `max_length=100` pode estourar em colisão de nome | Caminho base de 94 caracteres + sufixo `_xxxxxxx` = 102 em `default_storage.save` | Erro `value too long` no PostgreSQL em cenário de concorrência/arquivo residual | Aumentar para 255 ou encurtar o caminho; tratar colisão explicitamente |
| P2-10 | Extração sem lock e sem tratamento de concorrência | `extrair_imagens` não usa `select_for_update`; duas execuções podem violar unique constraint ou gerar arquivo órfão | Erro 500 ou arquivo duplicado | Lock por prova, tratamento de `IntegrityError` e idempotência explícita |

## 5. Testes realmente executados

| Suíte / comando | Resultado |
|---|---|
| `manage.py test provas simulados` | **74 testes, OK** (57,169 s) |
| `.work/audit_homologacao` (segurança, escopo, CSRF, impressão, consultas) | **13 testes, OK** |
| `.work/audit_consistencia` (órfãos, sincronização, PDF, imagens ignoradas) | **8 testes, OK** |
| `.work/audit_media_prod` (mídia com `DEBUG=False`) | **1 teste, OK**, confirmando 404 |
| `manage.py check` | Sem problemas |
| `manage.py makemigrations --check --dry-run` | `No changes detected` |
| Migrations SQLite 0001→0005 | OK |
| Rollback 0005→0004 e reaplicação | OK |
| Geração do DDL PostgreSQL | OK, sem conexão |
| Restauração do backup + `manage.py check` | OK |
| Medições de desempenho | Executadas nos cenários A e B |

Total: **96 testes executados** (74 existentes + 22 temporários), todos aprovados.

## 6. O que não foi validado

1. **PDF real do ENEM**: não há arquivo em `media/`; a extração foi validada com PDFs sintéticos. Layout, imagens inline, fontes e marcadores do PDF oficial continuam pendentes de validação.
2. **PostgreSQL dinâmico**: sem servidor local; compatibilidade verificada apenas pelo DDL gerado e pelo comportamento SQLite.
3. **Deploy real**: sem `.env`, sem configuração de disco/storage e sem acesso ao ambiente; o P1-01 foi demonstrado em settings de simulação, mas a correção depende da infraestrutura.
4. **Banco de produção**: não acessado, conforme solicitado.
5. **Impressão visual**: HTML/CSS verificados; não houve teste em navegador/impressora real.
6. **Órfãos existentes**: `media/` está vazio nesta cópia, então não há inventário de arquivos órfãos reais.
7. **Concorrência real**: os cenários de corrida foram analisados por código; não foram executados com múltiplos workers.
8. **Miniaturas em rede**: o custo foi medido pelo tamanho dos arquivos, não por teste de banda em navegador.

## 7. Recomendações priorizadas

1. **Antes de produção:** resolver P1-01 (disco persistente + publicação de `/media/` ou storage externo) e validar em staging com `DEBUG=False`.
2. **Antes de liberar a operação em escala:** P2-02 (imagem ignorada), P2-06 (troca de PDF), P2-03/P2-04 (órfãos/links quebrados) e P2-05 (associação cruzada).
3. **Melhoria de desempenho:** P2-07 (thumbnails), P2-08 (background/streaming) e P2-09/P2-10 (limites de nome e concorrência).
4. **Higiene operacional:** P2-01 (backup sem `__pycache__`, com escopo documentado).

Nenhuma alteração de código de produção foi feita nesta etapa.
