"""Auditoria de integridade do backup pre-imagens (somente leitura)."""

import hashlib
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BACKUP = RAIZ / 'outputs' / 'backup-pre-imagens-2026-11-13.zip'


def sha256(dados):
    return hashlib.sha256(dados).hexdigest()


def main():
    print(f'arquivo: {BACKUP}')
    print(f'existe: {BACKUP.exists()}')

    if not BACKUP.exists():
        return 1

    bruto = BACKUP.read_bytes()
    print(f'tamanho_bytes: {len(bruto)}')
    print(f'sha256_zip: {sha256(bruto)}')

    with zipfile.ZipFile(BACKUP) as arquivo:
        corrompido = arquivo.testzip()
        print(f'testzip: {corrompido or "OK (nenhuma entrada corrompida)"}')

        entradas = arquivo.infolist()
        print(f'entradas: {len(entradas)}')
        print(
            'tamanho_descomprimido:',
            sum(item.file_size for item in entradas),
        )
        print(
            'compactado:',
            sum(item.compress_size for item in entradas),
        )

        esperados = [
            'manage.py',
            'requirements.txt',
            'db.sqlite3',
            'config/settings.py',
            'config/urls.py',
            'provas/models.py',
            'provas/views.py',
            'provas/importador.py',
            'provas/urls.py',
            'provas/admin.py',
            'provas/tests.py',
            'simulados/views.py',
            'simulados/models.py',
            'simulados/tests.py',
            'templates/base.html',
            'templates/provas/detalhe.html',
            'templates/simulados/responder.html',
            'templates/simulados/resultado.html',
            'static/css/examix.css',
            'usuarios/decorators.py',
        ]

        nomes = {item.filename.replace('\\', '/') for item in entradas}
        faltando = [nome for nome in esperados if nome not in nomes]
        print(f'membros_esperados_faltando: {faltando or "nenhum"}')

        # Confere leitura de todo o conteúdo (valida CRC na prática).
        erros_leitura = []
        conteudos = {}
        for item in entradas:
            if item.is_dir():
                continue
            try:
                conteudos[item.filename.replace('\\', '/')] = (
                    arquivo.read(item)
                )
            except Exception as erro:  # noqa: BLE001
                erros_leitura.append((item.filename, repr(erro)))
        print(f'erros_leitura: {erros_leitura or "nenhum"}')

        marcadores = {
            'migration_0005_presente': any(
                '0005_imagemprova' in nome for nome in nomes
            ),
            'imagens_py_presente': 'provas/imagens.py' in nomes,
            'templates_imagens_presente': (
                'templates/provas/imagens.html' in nomes
            ),
            'templates_imprimir_presente': (
                'templates/provas/imprimir.html' in nomes
            ),
        }
        print(f'marcadores: {marcadores}')

        db = conteudos.get('db.sqlite3')
        print(f'db_sqlite3_bytes: {len(db) if db is not None else "ausente"}')

        # Compara com a árvore atual: arquivos não alterados pela etapa
        # de imagens devem ser idênticos byte a byte.
        identicos = []
        diferentes = []
        ausentes = []

        for nome, conteudo in conteudos.items():
            if nome == 'db.sqlite3' or nome.endswith('/'):
                continue
            atual = RAIZ / nome
            if not atual.exists():
                ausentes.append(nome)
            elif atual.is_file() and sha256(atual.read_bytes()) == sha256(
                conteudo
            ):
                identicos.append(nome)
            else:
                diferentes.append(nome)

        print(f'arquivos_identicos_ao_atual: {len(identicos)}')
        print(f'arquivos_diferentes_do_atual: {len(diferentes)}')
        print(f'arquivos_do_backup_ausentes_hoje: {len(ausentes)}')
        print('lista_diferentes:')
        for nome in sorted(diferentes):
            print(f'  - {nome}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
