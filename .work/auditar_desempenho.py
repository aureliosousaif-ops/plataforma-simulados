"""Medições de desempenho do leitor de imagens com PDFs sintéticos.

Gera PDFs temporários (texto + imagens JPEG embutidas) e mede tempo,
pico de memória e consultas. Usa apenas o banco temporário de auditoria.
"""

import os
import time
import tracemalloc
from io import BytesIO

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'audit_settings')
django.setup()

from django.contrib.auth.models import User  # noqa: E402
from django.core.files.base import ContentFile  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from django.urls import reverse  # noqa: E402
from PIL import Image  # noqa: E402

from provas.imagens import (  # noqa: E402
    extrair_e_registrar_imagens,
    extrair_imagens_pdf,
    gerar_sugestoes_associacao,
    mapear_marcadores_pdf,
)
from provas.models import (  # noqa: E402
    Disciplina,
    ImagemProva,
    ImagemQuestao,
    Prova,
    Questao,
)
from usuarios.models import Perfil  # noqa: E402


def jpeg_da_pagina(indice, tamanho=(1200, 1600), ruido=False):
    """Gera um JPEG diferente por página."""
    if ruido:
        largura, altura = tamanho
        imagem = Image.frombytes(
            'RGB',
            tamanho,
            os.urandom(largura * altura * 3),
        )
    else:
        cor = (
            (indice * 37) % 256,
            (indice * 71) % 256,
            (indice * 113) % 256,
        )
        imagem = Image.new('RGB', tamanho, cor)

    buffer = BytesIO()
    imagem.save(
        buffer,
        'JPEG',
        quality=80,
    )
    return buffer.getvalue()


def gerar_pdf_com_texto_e_imagens(
    quantidade_paginas,
    largura=595,
    altura=842,
    tamanho_imagem=(1200, 1600),
    ruido=False,
):
    """Monta um PDF com um JPEG de fundo e um marcador QUESTAO n por página."""
    objetos = []

    def adicionar(corpo):
        objetos.append(corpo)
        return len(objetos)

    # 1: catálogo, 2: páginas, 3: fonte.
    catalogo = adicionar(b'<< /Type /Catalog /Pages 2 0 R >>')
    paginas = adicionar(b'')  # preenchido no final
    fonte = adicionar(
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'
    )

    ids_paginas = []

    for numero in range(1, quantidade_paginas + 1):
        jpeg = jpeg_da_pagina(
            numero,
            tamanho=tamanho_imagem,
            ruido=ruido,
        )
        imagem = adicionar(
            (
                f'<< /Type /XObject /Subtype /Image /Width 1200 '
                f'/Height 1600 /ColorSpace /DeviceRGB '
                f'/BitsPerComponent 8 /Filter /DCTDecode '
                f'/Length {len(jpeg)} >>\nstream\n'
            ).encode('ascii')
            + jpeg
            + b'\nendstream'
        )

        conteudo = (
            'q\n'
            f'{largura} 0 0 {altura} 0 0 cm\n'
            f'/Im0 Do\n'
            'Q\n'
            'BT\n'
            '/F1 16 Tf\n'
            '40 800 Td\n'
            f'(QUESTAO {numero}) Tj\n'
            'ET\n'
            'BT\n'
            '/F1 10 Tf\n'
            '40 770 Td\n'
            f'(Enunciado sintetico da questao {numero}.) Tj\n'
            'ET\n'
        ).encode('ascii')

        fluxo = adicionar(
            f'<< /Length {len(conteudo)} >>\nstream\n'.encode('ascii')
            + conteudo
            + b'endstream'
        )

        pagina = adicionar(
            (
                f'<< /Type /Page /Parent {paginas} 0 R '
                f'/MediaBox [0 0 {largura} {altura}] '
                f'/Resources << /Font << /F1 {fonte} 0 R >> '
                f'/XObject << /Im0 {imagem} 0 R >> >> '
                f'/Contents {fluxo} 0 R >>'
            ).encode('ascii')
        )
        ids_paginas.append(pagina)

    kids = ' '.join(f'{item} 0 R' for item in ids_paginas)
    objetos[paginas - 1] = (
        f'<< /Type /Pages /Kids [{kids}] /Count {len(ids_paginas)} >>'
    ).encode('ascii')

    saida = BytesIO()
    saida.write(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = [0]

    for numero, corpo in enumerate(objetos, start=1):
        offsets.append(saida.tell())
        saida.write(f'{numero} 0 obj\n'.encode('ascii'))
        saida.write(corpo)
        saida.write(b'\nendobj\n')

    inicio_xref = saida.tell()
    saida.write(f'xref\n0 {len(objetos) + 1}\n'.encode('ascii'))
    saida.write(b'0000000000 65535 f \n')
    for offset in offsets[1:]:
        saida.write(f'{offset:010d} 00000 n \n'.encode('ascii'))

    saida.write(
        (
            f'trailer\n<< /Size {len(objetos) + 1} '
            f'/Root {catalogo} 0 R >>\n'
            f'startxref\n{inicio_xref}\n%%EOF\n'
        ).encode('ascii')
    )

    return saida.getvalue()


def medir(rotulo, funcao):
    tracemalloc.start()
    inicio = time.perf_counter()
    resultado = funcao()
    duracao = time.perf_counter() - inicio
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(
        f'[perf] {rotulo}: {duracao:.2f}s, pico_tracemalloc='
        f'{pico / (1024 * 1024):.1f} MiB'
    )
    return resultado, duracao


def main():
    paginas = int(os.environ.get('PERF_PAGINAS', '40'))
    ruido = os.environ.get('PERF_RUIDO') == '1'
    tamanho = (1240, 1754) if ruido else (1200, 1600)
    print(
        f'[perf] gerando PDF sintético com {paginas} páginas/imagens '
        f'(ruido={ruido}, tamanho={tamanho})...'
    )
    pdf = gerar_pdf_com_texto_e_imagens(
        paginas,
        tamanho_imagem=tamanho,
        ruido=ruido,
    )
    print(
        f'[perf] pdf_sintetico: {len(pdf) / (1024 * 1024):.2f} MiB, '
        f'{paginas} páginas'
    )

    caminho = os.path.join(
        os.path.dirname(__file__),
        'perf_sintetico.pdf',
    )
    with open(caminho, 'wb') as arquivo:
        arquivo.write(pdf)

    imagens, tempo_extracao = medir(
        'extrair_imagens_pdf',
        lambda: extrair_imagens_pdf(caminho),
    )
    print(
        f'[perf] imagens extraídas: {len(imagens)}, '
        f'bytes de imagem: '
        f'{sum(len(item["dados"]) for item in imagens) / (1024 * 1024):.2f} MiB'
    )

    marcadores, tempo_marcadores = medir(
        'mapear_marcadores_pdf',
        lambda: mapear_marcadores_pdf(caminho),
    )
    print(f'[perf] marcadores encontrados: {len(marcadores)}')

    # Banco temporário de auditoria.
    usuario, _ = User.objects.get_or_create(
        username='perf_dev',
        defaults={'is_staff': False},
    )
    Perfil.objects.update_or_create(
        usuario=usuario,
        defaults={'tipo': 'desenvolvedor'},
    )
    disciplina, _ = Disciplina.objects.get_or_create(nome='Perf')

    prova = Prova.objects.create(
        nome='Prova sintética de desempenho',
        tipo='enem',
        ano=2026,
    )
    prova.arquivo_pdf.save(
        'perf_sintetico.pdf',
        ContentFile(pdf),
        save=True,
    )

    for numero in range(1, paginas + 1):
        Questao.objects.create(
            prova=prova,
            disciplina=disciplina,
            numero=numero,
            enunciado=f'Enunciado sintético {numero}.',
        )

    with CaptureQueriesContext(connection) as consultas_extracao:
        resultado, tempo_persistencia = medir(
            'extrair_e_registrar_imagens',
            lambda: extrair_e_registrar_imagens(prova),
        )
    print(
        f'[perf] persistência: {resultado}, consultas='
        f'{len(consultas_extracao)}'
    )

    sugestoes, tempo_sugestoes = medir(
        'gerar_sugestoes_associacao',
        lambda: gerar_sugestoes_associacao(prova),
    )
    print(f'[perf] sugestões criadas: {sugestoes}')

    # Confirma tudo para medir as telas no pior caso.
    from provas.imagens import confirmar_todas_sugestoes

    with CaptureQueriesContext(connection) as consultas_confirmacao:
        confirmadas, tempo_confirmacao = medir(
            'confirmar_todas_sugestoes',
            lambda: confirmar_todas_sugestoes(prova),
        )
    print(
        f'[perf] sugestões confirmadas: {confirmadas}, consultas='
        f'{len(consultas_confirmacao)}'
    )

    cliente = Client()
    cliente.force_login(usuario)

    for nome, url in (
        ('revisar_imagens', reverse(
            'provas:revisar_imagens', kwargs={'prova_id': prova.id}
        )),
        ('imprimir', reverse(
            'provas:imprimir', kwargs={'prova_id': prova.id}
        )),
    ):
        with CaptureQueriesContext(connection) as consultas:
            tracemalloc.start()
            inicio = time.perf_counter()
            resposta = cliente.get(url)
            duracao = time.perf_counter() - inicio
            _, pico = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        print(
            f'[perf] GET {nome}: status={resposta.status_code}, '
            f'{duracao:.2f}s, consultas={len(consultas)}, '
            f'pico_tracemalloc={pico / (1024 * 1024):.1f} MiB, '
            f'html={len(resposta.content) / 1024:.0f} KiB'
        )

    # Limpeza do banco temporário (arquivos em .work/audit_media ficam).
    ImagemQuestao.objects.filter(imagem__prova=prova).delete()
    ImagemProva.objects.filter(prova=prova).delete()
    Questao.objects.filter(prova=prova).delete()
    prova.delete()

    print(
        f'[perf] tempos: extração={tempo_extracao:.2f}s, '
        f'marcadores={tempo_marcadores:.2f}s, '
        f'persistência={tempo_persistencia:.2f}s, '
        f'sugestões={tempo_sugestoes:.2f}s, '
        f'confirmação={tempo_confirmacao:.2f}s'
    )


if __name__ == '__main__':
    main()
