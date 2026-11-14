# Auditoria técnica — leitor/importador de provas Examix

Data: 13/11/2026

## 1. Escopo e método

Auditoria do fluxo de leitura de provas em PDF, extração de questões/alternativas/gabarito,
gravação no banco, associação manual disponível, uso em simulado e saída/impressão.

Método:

- leitura direta do código atual;
- conferência de migrations e dependências;
- execução de `manage.py check`, `makemigrations --check --dry-run`, `showmigrations` e testes;
- experimento isolado de integração em banco SQLite temporário, fora do projeto e fora de
  qualquer `DATABASE_URL`;
- testes de regressão para cada correção aplicada.

Nenhum banco de produção foi acessado. Nenhum dado real foi alterado. Antes das mudanças
estruturais foi criado o backup `outputs/backup-pre-correcoes-2026-11-13.zip`.

## 2. O que realmente está implementado

| Área | Situação |
|---|---|
| Extração de texto de PDF | Implementada com `pypdf` (`provas/importador.py`). |
| OCR / leitura de imagens | **Não implementada**. Não há `pytesseract`, `pdf2image` ou equivalente. |
| Extração de imagens das questões | Implementada em `provas/imagens.py` com `pypdf.page.images` e parser de posição. |
| Associação imagem → questão | Sugestões automáticas não confirmadas + revisão manual própria. |
| Parser de questões ENEM | Implementado, com heurísticas de marcadores, alternativas e blocos bilíngues. |
| Extração de gabarito | Implementada, incluindo variantes de idioma nas questões 1–5. |
| Gravação de questões/alternativas/gabarito | Implementada e atômica. |
| Associação manual | Tela própria em `provas/imagens.html`, além do Django Admin. |
| Simulado | Implementado. A tentativa usa apenas uma variante de idioma por vez. |
| Resultado/desempenho | Implementados. Passam a refletir o total real de questões da tentativa. |
| Impressão | Implementada em `provas/imprimir.html`, com `@media print`. |
| Reprocessamento | Implementado: apaga questões da própria prova e recria dentro de transação; imagens e confirmações são preservadas. |

## 3. Verificações executadas após as correções

Ambiente isolado: Python 3.13, Django 6.1.1, pypdf 6.19.0, django-allauth 65.19.4.

```text
manage.py check
System check identified no issues (0 silenced).

manage.py makemigrations --check --dry-run
No changes detected

manage.py test
Found 74 test(s).
Ran 74 tests in 148.982s
OK
```

Os testes usaram banco de teste SQLite em memória. O projeto não possui `.env`, `media/`
com PDFs nem banco com dados nesta cópia, então a extração contra o PDF real do ENEM e o
banco de produção não puderam ser validados.

Migrations existentes (sem alterações pendentes):

- `provas`: 0001, 0002, 0003, 0004, 0005 (imagens)
- `simulados`: 0001, 0002
- `usuarios`: 0001, 0002
- `desempenho`: sem migrations (app só de views)

## 4. Evidência do problema de integração e do resultado após a correção

Experimento com texto ENEM sintético (1–5 Inglês, 1–5 Espanhol, 6–90 comuns), gabarito
completo e banco temporário.

Antes da correção:

```text
questoes_extraidas: 95
questoes_importadas: 95
alternativas_corretas_no_banco: 95
respostas_criadas_no_simulado: 95
respostas_por_idioma: {None: 85, Inglês: 5, Espanhol: 5}
respostas_marcadas: 90
acertos: 90
erros: 0
percentual: 94.74
nao_respondidas: 5
```

Depois da correção (mesmo cenário, sem alterar a importação):

```text
questoes_extraidas: 95
questoes_importadas: 95
alternativas_corretas_no_banco: 95
respostas_criadas_no_simulado: 90
questoes_reais_esperadas_enem: 90
respostas_por_idioma: {None: 85, Inglês: 5, Espanhol: 0}
respostas_marcadas: 90
acertos: 90
erros: 0
percentual: 100.00
nao_respondidas: 0
```

Conclusão: as 95 questões continuam no acervo da prova (as duas variantes de idioma são
preservadas), mas cada tentativa agora cria respostas para apenas uma variante. O total e o
percentual passam a refletir as 90 questões reais do ENEM.

## 5. Problemas corrigidos nesta etapa

### P0 — bloqueadores

1. **Variantes de idioma duplicadas no simulado** (`simulados/views.py`,
   `templates/simulados/lista.html`).
   `iniciar()` agora escolhe uma única opção de língua (padrão Inglês, com seletor na lista
   quando a prova oferece as duas). As duas variantes permanecem no banco, mas a tentativa
   cria respostas apenas para a variante escolhida. Simulados antigos não são alterados.

### P1 — alto

2. **Ano 2024 fixo** (`provas/importador.py`).
   A limpeza de rodapé, a remoção de cauda repetida, a limpeza de alternativas e a validação
   de artefatos agora reconhecem `ENEM` seguido de qualquer ano.
3. **Extração parcial não detectada** (`provas/importador.py`).
   `validar_estrutura_questoes()` compara as chaves do gabarito com as questões realmente
   extraídas. Se o gabarito cita uma questão que não foi extraída, o processamento falha e a
   prova fica com status `erro`.
4. **Gabarito podia ser ignorado em chamada direta** (`provas/importador.py`).
   `importar_questoes_no_banco()` agora dá prioridade ao gabarito recebido; a marcação
   `correta` preparada anteriormente só é usada quando não há resposta de gabarito.

### P2 — médio

5. `validar_estrutura_questoes()` detecta duplicidade de `(numero, idioma)` e não possui mais
   o trecho de código morto.
6. `iniciar()` não cria mais simulado vazio: se a prova não tiver questões ativas, exibe
   mensagem e volta para a lista.
7. A lista de simulados mostra o total real de questões (números distintos), não a soma das
   variantes de idioma.
8. `MAILERS` (configuração inválida no Django 6.1) foi substituído por `EMAIL_BACKEND`,
   configurável pela variável de ambiente `EMAIL_BACKEND`.
9. PDF sem texto extraível agora gera erro explícito orientando aplicar OCR antes de importar.

### Testes de regressão adicionados

- duplicidade de `(numero, idioma)`;
- questão presente no gabarito e ausente na prova;
- artefato de impressão de outro ano;
- prioridade do gabarito sobre marcação preparada;
- PDF sem texto orientando OCR;
- remoção de artefato de ano anterior;
- fluxo da view `processar` com sucesso e com extração parcial;
- criação de respostas apenas para o idioma escolhido;
- idioma padrão Inglês;
- prova sem questões não cria simulado;
- total real e seletor de idioma na lista.

## 6. Etapa de imagens (leitor completo)

Antes desta etapa foi criado e validado o backup
`outputs/backup-pre-imagens-2026-11-13.zip` (136 entradas, 2.229.754 bytes).

### 6.1 Arquivos criados

| Arquivo | Função |
|---|---|
| `provas/imagens.py` | Extração das imagens do PDF, posição, marcadores, sugestões, deduplicação, confirmação, remoção, ignorar/reativar e preservação ao reprocessar. |
| `provas/migrations/0005_imagemprova_imagemquestao_and_more.py` | Cria `ImagemProva`, `ImagemQuestao` e as constraints. |
| `templates/provas/imagens.html` | Tela de revisão por página, com miniatura, sugestões, associação manual, confirmação em lote e ignorar/reativar. |
| `templates/provas/imprimir.html` | Versão de impressão com enunciados, imagens confirmadas e alternativas. |

### 6.2 Arquivos modificados

| Arquivo | Alteração |
|---|---|
| `provas/models.py` | Novos modelos `ImagemProva`/`ImagemQuestao` e propriedade `Questao.imagens_exibicao`. |
| `provas/views.py` | Imagens no `processar` (savepoint isolado), `revisar_imagens`, `extrair_imagens`, `acao_imagem` e `imprimir`; contadores no `detalhe`. |
| `provas/urls.py` | Rotas `revisar_imagens`, `extrair_imagens`, `acao_imagem` e `imprimir`. |
| `provas/admin.py` | Admin de `ImagemProva` e `ImagemQuestao`. |
| `templates/provas/detalhe.html` | Contadores de imagens/pendentes e botões de revisão, extração e impressão. |
| `templates/simulados/responder.html` | Exibição das imagens confirmadas durante o simulado. |
| `templates/simulados/resultado.html` | Exibição das imagens confirmadas na revisão do resultado. |
| `simulados/views.py` | Prefetch de `questao__imagens_associadas__imagem` em `responder` e `resultado`. |
| `static/css/examix.css` | Estilos de exibição, revisão e impressão. |
| `provas/tests.py` | Testes de extração, sugestão, persistência, revisão, impressão e falha de imagem no processamento. |
| `simulados/tests.py` | Testes de exibição no simulado, no resultado, de sugestão não confirmada e de fallback legado. |

### 6.3 Regras implementadas

- `ImagemProva` guarda o arquivo original, hash SHA-256, página, índice na página, dimensões
  originais, posição estimada e flag de ignorada.
- `ImagemQuestao` permite várias imagens por questão, no máximo uma associação confirmada por
  imagem (constraint parcial) e registra origem automática/manual.
- Deduplicação por `(prova, hash_sha256, pagina, indice_pagina)`; o arquivo físico é
  compartilhado pelo hash.
- Associações automáticas são sempre sugestões não confirmadas. Só associações confirmadas
  aparecem no simulado/resultado/impressão.
- `Questao.imagem` permanece como campo legado/principal e é sincronizado com a primeira
  associação confirmada. Imagens legadas enviadas manualmente são preservadas quando não há
  confirmação.
- Nenhuma imagem original é apagada: ignorar apenas oculta a imagem e remove sugestões
  automáticas. Uma imagem com associação confirmada não pode ser ignorada sem remover antes.
- Reprocessar o PDF reaproveita imagens já registradas e restaura as confirmações por
  `(numero, idioma)`.
- Falha na extração de imagens não desfaz a importação textual já validada; a prova fica
  `processada` com aviso em `mensagem_importacao`.

### 6.4 Testes específicos desta etapa

- extração de duas imagens com dimensões, página, bytes e posição preservados;
- reprocessamento sem duplicar imagens e com hash conferido no disco;
- mesma imagem em páginas diferentes mantida como dois registros;
- sugestão pelo último marcador acima da imagem, respeitando coluna e idioma;
- ausência de sugestão em caso ambíguo ou sem posição;
- sugestão automática não preenche `Questao.imagem` antes da confirmação;
- confirmação preenche o campo legado e remoção limpa apenas imagens da própria prova;
- múltiplas imagens confirmadas na mesma questão;
- associação manual move a imagem entre questões;
- revisão lista imagens/questões, associa, confirma, remove, ignora/reativa e confirma em lote;
- extração a partir de prova já processada;
- impressão exibe enunciado, imagem confirmada e alternativas;
- simulado e resultado exibem imagem confirmada e fallback legado, e ocultam sugestão não
  confirmada;
- falha simulada de imagem mantendo as questões importadas.

## 7. Pendências que ainda exigem validação ou implementação

Estas pendências **não** foram marcadas como corrigidas porque dependem de PDF real,
ambiente de produção ou são funcionalidades ausentes:

1. **OCR/leitura de imagens**: não existe. PDFs digitalizados são rejeitados com mensagem
   orientando OCR, mas não há OCR automático.
2. **Imagens das questões**: extração, revisão e exibição implementadas. A qualidade da
   associação automática ainda precisa ser validada contra o PDF real do ENEM.
3. **Validação contra PDF real do ENEM**: não há PDF em `media/` nesta cópia. O parser e o
   novo fluxo de 90 respostas foram validados com texto sintético, não com o PDF oficial.
4. **Banco de produção**: não há `.env` nesta cópia; o risco de `DATABASE_URL` ser usado com
   `DEBUG=False` não pôde ser confirmado nem alterado com segurança.
5. **Associação manual**: agora existe tela própria em `provas`, além do Django Admin.
6. **Impressão**: implementada em `provas/imprimir.html`; falta validar o layout em navegador
   real com PDF oficial.
7. **Templates órfãos** (`disciplinas.html`, `questoes.html`, `alternativas.html`,
   `alternativas_form.html`) continuam referenciando URLs inexistentes.
8. **Deploy e mídia**: não há `Procfile`, `render.yaml`, `build.sh` ou `Dockerfile`; PDFs em
   disco local continuam efêmeros em produção.
9. **`SECRET_KEY`**: sem fallback/validação explícita.
10. **Classificação de disciplinas**: questões 1–5 recebem “Inglês”/“Espanhol” e as demais
    “Não classificada”; não há classificação por disciplina real.
11. **Regras de simulado**: sem limite de tempo, limite de tentativas, abandono automático ou
    aviso de questões em branco.
12. **Agregações**: histórico/desempenho ainda têm consultas N+1.

## 8. Como validar em ambiente real

1. Copiar um PDF oficial do ENEM e o gabarito para `media/` em um ambiente de teste.
2. Cadastrar a prova pelo formulário e executar “Processar”.
3. Conferir:
   - 95 questões no acervo (1–5 Inglês, 1–5 Espanhol, 6–90 comuns);
   - 90 números distintos;
   - lista de simulados exibindo 90 questões e o seletor de idioma;
   - tentativa com 90 respostas, apenas uma variante de idioma;
   - ao responder corretamente as 90, resultado de 100%.
4. Abrir “Revisar imagens”, conferir as sugestões, ajustar manualmente o que estiver ambíguo e
   confirmar. Só então as imagens aparecem em “Imprimir prova”, no simulado e no resultado.
5. Reprocessar a prova e confirmar que as imagens não foram duplicadas e que as confirmações
   anteriores foram restauradas.
6. Se o PDF for digitalizado, confirmar a mensagem de OCR e aplicar OCR externo antes de
   importar.

## 9. Limitações desta auditoria

- Não há PDF real em `media/` nesta cópia; a validação do parser e da associação de imagens
  contra o ENEM real permanece pendente.
- Não há `.env`; o risco de banco de produção não pôde ser confirmado.
- Não há dados no `db.sqlite3` desta cópia (o arquivo vazio criado durante as verificações
  foi removido).
- Não há repositório Git nesta cópia (`.git` ausente), apenas o artefato `tatus --short`.
- O visual renderizado da tela de revisão e da impressão não foi avaliado em navegador real;
  a validação foi feita por testes de view/template (200, imagens e textos esperados).
