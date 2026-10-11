# Análise atualizada — Examix

Data: 10/10/2026

## Resumo

O sistema é uma plataforma Django de simulados com cadastro de usuários, importação automática de provas em PDF, aplicação de simulados, correção, histórico e painel de desempenho.

A correção da FK `disciplina` foi aplicada em `provas/importador.py`, usando a disciplina padrão `Não classificada`. Entretanto, a importação ainda possui um erro crítico independente dessa correção.

## Prioridade P0 — corrigir antes de usar novas importações

### 1. O gabarito continua sendo descartado na gravação

Em `provas/views.py:337-340`, a chamada está assim:

```python
quantidade = importar_questoes_no_banco(
    prova,
    questoes_preparadas
)
```

A função `importar_questoes_no_banco` recebe `gabarito=None` e calcula `correta` usando um dicionário vazio (`provas/importador.py:1518-1522`). Como resultado, as alternativas importadas ficam com `correta=False`.

A preparação já calcula corretamente as alternativas em `preparar_questoes`, mas esse valor não é aproveitado na gravação.

**Correção recomendada:** passar o gabarito na chamada:

```python
quantidade = importar_questoes_no_banco(
    prova,
    questoes_preparadas,
    gabarito
)
```

Ou alterar o importador para usar o campo `correta` já presente em cada alternativa preparada.

### 2. A importação não usa transação

Se a questão 40 falhar depois de 39 questões salvas, o banco fica parcialmente importado. Como a prova pode não ter simulados ainda, uma nova tentativa poderá gerar conflito pela restrição única de número da questão.

**Correção recomendada:** envolver a criação de questões e alternativas em `transaction.atomic()` e apagar/reverter tudo automaticamente em caso de erro.

### 3. Reprocessamento de prova parcialmente importada

O bloqueio atual só impede reprocessamento quando já existem simulados vinculados. Se uma importação falhar depois de gravar parte das questões, o próximo processamento tentará inserir números repetidos e poderá falhar novamente.

**Correção recomendada:** usar transação atômica e, antes de importar uma prova sem simulados, remover questões antigas da própria prova ou exigir limpeza explícita.

### 4. `data_processamento` nunca é atualizada no sucesso

A model possui `data_processamento`, mas o fluxo marca a prova como processada sem atribuir a data/hora atual. O campo pode permanecer vazio mesmo após uma importação bem-sucedida.

**Correção recomendada:** gravar `timezone.now()` junto com `status_importacao='processada'` e limpar a data quando houver erro, conforme a regra desejada.

## Prioridade P1 — segurança e produção

### 5. O ambiente local continua apontando para o banco de produção

O `.env` local possui `DATABASE_URL` do PostgreSQL no Render. O `settings.py` usa essa variável sempre que preenchida, portanto o projeto local pode ler e alterar dados reais.

**Correção recomendada:** usar SQLite ou um PostgreSQL separado no desenvolvimento e manter o `DATABASE_URL` de produção somente no ambiente do Render. Também é recomendável adicionar uma proteção que impeça `DEBUG=True` usando o host de produção.

### 6. Os backups ainda estão versionados no Git

O `.gitignore` agora contém os nomes dos dois backups, mas isso não remove arquivos já rastreados. O comando `git rm --cached` não pôde ser executado neste dispositivo por bloqueio da política de controle de aplicativos.

Arquivos envolvidos:

- `backup_antes_limpar_usuarios.json`
- `db.sqlite3.backup`

Além de removê-los do índice, se já foram publicados no remoto, será necessário removê-los também do histórico do Git. Como possuem dados pessoais e hashes de senha, as credenciais relacionadas devem ser rotacionadas se houver possibilidade de exposição.

### 7. Arquivo `.gitignore` está duplicado

As regras de ambiente virtual, `.env` e `db.sqlite3` aparecem novamente nas linhas 38–52. Não quebra o sistema, mas indica que o arquivo foi acumulando alterações e precisa de limpeza.

## Prioridade P1 — contas e perfis

### 8. O signal de criação de perfil não está registrado

`usuarios/signals.py` define um signal para criar `Perfil`, mas `usuarios/apps.py` não possui `ready()` e nenhum módulo importa o signal.

Usuários criados pelo Google, pelo admin ou por comandos podem ficar sem perfil. O sistema trata isso com `try/except`, mas isso apenas esconde o problema.

Há ainda risco de duplicidade: o `CadastroForm.save()` já cria o perfil manualmente. A solução deve escolher uma única estratégia, preferencialmente signal + `get_or_create`, removendo a criação duplicada do formulário.

## Prioridade P1 — templates e rotas

### 9. Os quatro templates órfãos provavelmente continuam na pasta

A tentativa de exclusão foi bloqueada anteriormente. As rotas ausentes continuam sendo:

- `provas:criar_alternativas`
- `provas:alternativas`
- `provas:criar_disciplina`
- `provas:editar_disciplina`
- `provas:excluir_disciplina`
- `provas:criar_questao`

Os templates antigos são:

- `templates/provas/disciplinas.html`
- `templates/provas/questoes.html`
- `templates/provas/alternativas.html`
- `templates/provas/alternativas_form.html`

Como não são renderizados pelo fluxo atual, não afetam as telas atuais. Devem ser excluídos ou as rotas/views devem ser reconstruídas — manter os dois estados misturados gera confusão.

## Prioridade P2 — importador e qualidade dos dados

### 10. Todas as questões novas ficarão em `Não classificada`

A correção atual resolve a FK obrigatória, mas não classifica as questões. O painel por disciplina funcionará, porém todas as questões ficarão agrupadas na disciplina padrão.

**Melhoria recomendada:** criar uma tela ou regra de classificação após a importação, ou permitir selecionar uma disciplina padrão para a prova antes do processamento.

### 11. O importador aceita apenas cinco alternativas

A validação rejeita qualquer questão que não possua exatamente A, B, C, D e E. Isso é adequado para ENEM, mas limita vestibulares e concursos que usam quatro alternativas, itens certo/errado ou formatos diferentes.

**Melhoria recomendada:** configurar o formato de alternativas por tipo de prova ou deixar o parser registrar o formato detectado.

### 12. PDFs escaneados não são tratados

O parser depende de texto extraível via `pypdf`. PDFs formados apenas por imagens retornarão poucas ou nenhuma questão.

**Melhoria recomendada:** detectar texto insuficiente e exibir uma mensagem específica informando que OCR é necessário.

### 13. Imagens das questões não são importadas

O model possui `Questao.imagem`, mas o parser só extrai texto. Questões que dependem de gráficos, mapas, tabelas ou imagens perderão parte do conteúdo.

**Melhoria recomendada:** planejar extração de imagens dos PDFs ou permitir anexar imagens manualmente no admin.

## Prioridade P2 — experiência do aluno

### 14. Não existe limite de tempo real

Há cronômetro, mas ele apenas mede o tempo. Não há tempo máximo nem encerramento automático.

### 15. Não existe controle de tentativas

O mesmo usuário pode iniciar infinitas tentativas da mesma prova, gerando histórico excessivo e dificuldade para análise.

### 16. Simulado abandonado permanece em andamento

Não existe ação clara para abandonar, excluir ou retomar um simulado antigo. O histórico pode acumular várias tentativas abertas.

### 17. O aluno pode finalizar com questões em branco

O sistema calcula `nao_respondidas`, mas não há confirmação ou aviso forte antes da finalização. É necessário decidir se questões em branco devem ser permitidas — atualmente elas entram no denominador do percentual e não contam como erro.

## Prioridade P2 — configuração e deploy

### 18. Idioma e horário estão inadequados para o público brasileiro

O settings usa:

```python
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
```

Recomendado:

```python
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
```

### 19. Arquivos de mídia são locais e podem desaparecer no Render

Os PDFs ficam em `MEDIA_ROOT`. Em infraestrutura efêmera, arquivos enviados podem desaparecer após reinício ou novo deploy.

**Melhoria recomendada:** storage persistente ou serviço externo para mídia.

### 20. Deploy não está documentado por arquivos próprios

Não foram encontrados `Procfile`, `render.yaml`, `build.sh` ou `Dockerfile`. O projeto possui `gunicorn` e comandos de administração, mas o processo de implantação não está formalizado no repositório.

## Prioridade P3 — manutenção

- `provas/importador.py` contém código inalcançável depois de `return questoes`.
- Há imports duplicados em `config/urls.py`.
- `home.css` e `static/images/a.png` parecem não ser usados.
- Os testes estão praticamente vazios.
- As agregações de desempenho usam vários loops e consultas; com muitos alunos podem ficar lentas.
- O projeto não possui `.env.example` documentando as variáveis necessárias.
- O campo `SECRET_KEY` não possui validação explícita quando ausente.
- Bootstrap é carregado por CDN, sem fallback local.

## Ordem recomendada de execução

1. Corrigir o uso do gabarito na gravação.
2. Adicionar transação atômica no importador.
3. Corrigir reprocessamento e atualizar `data_processamento`.
4. Separar banco local do banco de produção.
5. Remover os backups do índice e do histórico Git.
6. Limpar o `.gitignore` duplicado.
7. Resolver definitivamente a criação de `Perfil`.
8. Excluir templates órfãos ou reconstruir o CRUD.
9. Ajustar idioma, fuso e armazenamento de mídia.
10. Criar testes do parser e do cálculo de resultados antes de novas mudanças.

## Conclusão

A plataforma tem uma boa base e o fluxo principal está bem estruturado. A correção da disciplina eliminou um bloqueio específico, mas **a importação ainda não está pronta para produção enquanto o gabarito continuar sendo ignorado e não houver transação**. O maior risco operacional fora do código é o ambiente local utilizar o banco de produção.
