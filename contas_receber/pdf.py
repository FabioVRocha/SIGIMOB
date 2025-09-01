"""Geração simplificada de boletos em PDF.

Esta rotina produz um boleto bancário em formato PDF sem depender de
bibliotecas externas. Todo o layout é desenhado "na mão" por meio de
comandos PDF diretos (``re`` para retângulos, ``m``/``l`` para linhas e
``Tj`` para textos), o que garante portabilidade do arquivo para qualquer
leitor de PDF.

O desenho foi ajustado para seguir o padrão visual de um boleto bancário
com "Recibo do Pagador" (parte superior) e "Ficha de Compensação"
(inferior), tomando como referência os modelos anexos (por exemplo,
``Temporario/boleto/Modelo Boleto2.pdf``). Mantém-se os rótulos que já
eram usados nos testes automatizados para não quebrar integrações
existentes, mas as posições e blocos foram alinhados ao layout padrão.
"""

from datetime import datetime, date
import re


def _num(x: str) -> str:
    """Extrai apenas dígitos de uma string."""
    return re.sub(r"\D", "", x or "")


def _linha_digitavel(conta, nosso_numero: str, vencimento, valor: float) -> str:
    """Gera uma linha digitável com 47 dígitos no formato visual padrão.

    Obs.: Não calcula os dígitos verificadores oficiais. O objetivo aqui é
    produzir um placeholder com o agrupamento típico para uso visual no PDF.
    """
    banco = (_num(conta.banco) or "000").rjust(3, "0")[:3]
    moeda = "9"  # Real
    # aceita date ou datetime para o vencimento
    if isinstance(vencimento, datetime):
        venc_date = vencimento.date()
    else:
        venc_date = vencimento  # assume date
    fator = (venc_date - date(1997, 10, 7)).days
    fator_str = str(max(fator, 0)).rjust(4, "0")[:4]
    valor_str = ("%010d" % int(round(float(valor) * 100)))[:10]
    ag = _num(conta.agencia)[:4].ljust(4, "0")
    cc = _num(conta.conta).replace("-", "")[:8].ljust(8, "0")
    nn = _num(nosso_numero)[:11].rjust(11, "0")
    carteira = _num(getattr(conta, "carteira", "17") or "17")[:2].rjust(2, "0")

    # Monta 47 dígitos (placeholder):
    base = (banco + moeda + carteira + ag + nn + cc + fator_str + valor_str)
    base = (base + ("0" * 47))[:47]
    # Agrupamento visual: 5.5  5.6  5.6  1  14
    c1 = f"{base[0:5]}.{base[5:10]}"
    c2 = f"{base[10:15]}.{base[15:21]}"
    c3 = f"{base[21:26]}.{base[26:32]}"
    dv = base[32]
    c5 = base[33:47]
    return f"{c1} {c2} {c3} {dv} {c5}"


def _codigo_barras_itf(numero: str, x: int, y: int, largura_total: int, altura: int) -> list[str]:
    """Gera comandos PDF para um código de barras *Interleaved 2 of 5*.

    O padrão ``Interleaved 2 of 5`` é utilizado nos boletos bancários e
    codifica números em pares de dígitos. Cada par é convertido em cinco
    barras e cinco espaços intercalados, combinando larguras finas (``n``)
    e largas (``w``). Este algoritmo replica a mesma lógica empregada na
    visualização HTML, permitindo que o código seja lido por scanners
    compatíveis. Adiciona‑se ainda a "*quiet zone*" (margem em branco
    obrigatória) de 10 módulos em cada lado, requisito para leitura
    correta do código por leitores óticos.
    """

    padroes = {
        "0": "nnwwn",
        "1": "wnnnw",
        "2": "nwnnw",
        "3": "wwnnn",
        "4": "nnwnw",
        "5": "wnwnn",
        "6": "nwwnn",
        "7": "nnnww",
        "8": "wnnwn",
        "9": "nwnwn",
    }

    numero = _num(numero)
    if len(numero) % 2:
        numero = "0" + numero

    sequencia = []  # lista de tuplas (is_bar, unidades)

    def add_padroes(barras: str, espacos: str) -> None:
        for b, e in zip(barras, espacos):
            sequencia.append((True, 3 if b == "w" else 1))
            sequencia.append((False, 3 if e == "w" else 1))

    # Guarda inicial: barra/espaco/barra/espaco finos
    add_padroes("nn", "nn")

    # Dígitos codificados em pares
    for i in range(0, len(numero), 2):
        barras = padroes[numero[i]]
        espacos = padroes[numero[i + 1]]
        add_padroes(barras, espacos)

    # Guarda final: barra larga, espaço fino, barra fina
    sequencia.extend([(True, 3), (False, 1), (True, 1)])

    total_unidades = sum(u for _, u in sequencia)
    
    # Reserva 10 módulos à esquerda e à direita como áreas de silêncio. Para
    # garantir que o espaço reservado não "invada" o código de barras, o
    # cálculo do módulo considera também essas margens antes de converter os
    # valores em pixels.
    quiet_modules = 10
    modulo = max(int(largura_total / (total_unidades + 2 * quiet_modules)), 1)
    quiet = quiet_modules * modulo

    # Garante que o espaço do código de barras esteja limpo e com as
    # margens de silêncio adequadas. Primeiro preenchemos toda a área
    # com branco, restaurando a cor preta em seguida para desenhar as
    # barras propriamente ditas.
    comandos = [
        "1 g",
        f"{x} {y} {largura_total} {altura} re f",
        "0 g",
    ]

    pos = x + quiet
    for is_bar, unidades in sequencia:
        largura = unidades * modulo
        if is_bar:
            comandos.append(f"{pos} {y} {largura} {altura} re f")
        pos += largura
    return comandos


def gerar_pdf_boleto(titulo, empresa, conta, cliente, filepath: str) -> None:
    """Gera um PDF de boleto com layout semelhante ao modelo fornecido.

    Os dados do beneficiário, da conta bancária e do sacado (cliente) são
    preenchidos de acordo com os registros ``Empresa Licenciada``,
    ``Contas Bancárias`` e ``Pessoas`` cadastrados no sistema.
    """

    due_date = titulo.data_vencimento.strftime('%d/%m/%Y')
    valor = f"{float(titulo.valor_previsto):.2f}"
    nosso_numero = titulo.nosso_numero or ""
    doc_num = str(titulo.id)
    beneficiario = empresa.razao_social_nome
    agencia_conta = f"{conta.agencia}/{conta.conta}"
    banco_nome = conta.nome_banco or conta.banco
    linha_digitavel = _linha_digitavel(conta, nosso_numero, titulo.data_vencimento, float(titulo.valor_previsto))
    cnpj = empresa.documento or ""
    data_doc = datetime.now().strftime('%d/%m/%Y')
    pagador_nome = cliente.razao_social_nome or ""
    pagador_doc = cliente.documento or ""
    pagador_endereco = " ".join(
        filter(
            None,
            [
                cliente.endereco,
                cliente.bairro,
                f"{cliente.cidade}/{cliente.estado}" if cliente.cidade and cliente.estado else None,
                cliente.cep,
            ],
        )
    )

    # Dimensões de página A4
    width, height = 595, 842

    # Construção do layout padrão
    conteudo_pdf = [
        "0.5 w",  # espessura das linhas
        # --- Recibo do Pagador (topo) ---
        "BT /F1 12 Tf 60 800 Td (Recibo do Pagador) Tj ET",
        # Cabeçalho com banco e linha digitável
        "50 780 495 28 re S",
        "50 780 m 140 808 l S",  # espaço p/ logo
        "140 780 m 140 808 l S",
        f"BT /F1 12 Tf 60 792 Td ({banco_nome}) Tj ET",
        "BT /F1 8 Tf 330 806 Td (Linha Digitavel) Tj ET",
        f"BT /F1 12 Tf 330 792 Td ({linha_digitavel}) Tj ET",

        # Moldura principal do recibo
        "50 590 495 180 re S",
        # Linhas horizontais
        "50 740 m 545 740 l S",  # local pagto / vencimento
        "50 710 m 545 710 l S",  # cedente / ag codigo
        "50 680 m 545 680 l S",  # nosso número / num doc / valor doc
        "50 650 m 545 650 l S",  # cnpj / ... / nosso numero
        "50 620 m 545 620 l S",  # uso do banco / datas / carteira / especie / quantidade / valor
        # Colunas
        "370 740 m 370 768 l S",
        "320 710 m 320 740 l S",
        "240 680 m 240 710 l S",
        "420 680 m 420 740 l S",
        "120 650 m 120 680 l S",
        "200 650 m 200 680 l S",
        "280 650 m 280 680 l S",
        "360 650 m 360 680 l S",
        "440 650 m 440 680 l S",
        "140 620 m 140 650 l S",
        "240 620 m 240 650 l S",
        "320 620 m 320 650 l S",
        "400 620 m 400 650 l S",
        "480 620 m 480 650 l S",

        # Rótulos
        "BT /F1 8 Tf 60 748 Td (Local do Pagamento) Tj ET",
        "BT /F1 8 Tf 380 748 Td (Data de Vencimento) Tj ET",
        "BT /F1 8 Tf 60 718 Td (Nome do Beneficiario) Tj ET",
        "BT /F1 8 Tf 330 718 Td (Agencia/Codigo do Beneficiario) Tj ET",
        "BT /F1 8 Tf 60 688 Td (Nosso numero) Tj ET",
        "BT /F1 8 Tf 250 688 Td (Numero do documento) Tj ET",
        "BT /F1 8 Tf 430 688 Td (Valor do Documento) Tj ET",
        "BT /F1 8 Tf 60 658 Td (CNPJ) Tj ET",
        "BT /F1 8 Tf 130 658 Td (Nr. do documento) Tj ET",
        "BT /F1 8 Tf 210 658 Td (Esp. Doc) Tj ET",
        "BT /F1 8 Tf 290 658 Td (Aceite) Tj ET",
        "BT /F1 8 Tf 370 658 Td (Data Proces.) Tj ET",
        "BT /F1 8 Tf 450 658 Td (Nosso numero) Tj ET",
        "BT /F1 8 Tf 60 628 Td (Uso do Banco) Tj ET",
        "BT /F1 8 Tf 150 628 Td (Data Documento) Tj ET",
        "BT /F1 8 Tf 250 628 Td (Carteira) Tj ET",
        "BT /F1 8 Tf 330 628 Td (Especie) Tj ET",
        "BT /F1 8 Tf 410 628 Td (Quantidade) Tj ET",
        "BT /F1 8 Tf 490 628 Td ((x) Valor) Tj ET",

        # Valores
        "BT /F1 14 Tf 60 755 Td (Boleto Bancario) Tj ET",
        "BT /F1 10 Tf 60 735 Td (Pagavel em qualquer banco ate o vencimento.) Tj ET",
        f"BT /F1 10 Tf 380 735 Td ({due_date}) Tj ET",
        f"BT /F1 10 Tf 60 705 Td ({beneficiario}) Tj ET",
        f"BT /F1 10 Tf 330 705 Td ({agencia_conta}) Tj ET",
        f"BT /F1 10 Tf 60 675 Td ({nosso_numero}) Tj ET",
        f"BT /F1 10 Tf 250 675 Td ({doc_num}) Tj ET",
        f"BT /F1 10 Tf 430 675 Td ({valor}) Tj ET",
        f"BT /F1 10 Tf 60 645 Td ({cnpj}) Tj ET",
        f"BT /F1 10 Tf 130 645 Td ({doc_num}) Tj ET",
        "BT /F1 10 Tf 210 645 Td (DM) Tj ET",
        "BT /F1 10 Tf 290 645 Td (N) Tj ET",
        f"BT /F1 10 Tf 370 645 Td ({data_doc}) Tj ET",
        f"BT /F1 10 Tf 450 645 Td ({nosso_numero}) Tj ET",
        f"BT /F1 10 Tf 150 615 Td ({data_doc}) Tj ET",
        f"BT /F1 10 Tf 250 615 Td ({getattr(conta, 'carteira', '17') or '17'}) Tj ET",
        "BT /F1 10 Tf 330 615 Td (R$) Tj ET",
        f"BT /F1 10 Tf 490 615 Td ({valor}) Tj ET",

        # Sacado
        "50 590 m 545 590 l S",
        "BT /F1 8 Tf 60 598 Td (Nome do Pagador / Endereco) Tj ET",
        "BT /F1 8 Tf 490 598 Td (CPF/CNPJ) Tj ET",
        f"BT /F1 10 Tf 60 582 Td ({pagador_nome}) Tj ET",
        f"BT /F1 10 Tf 60 567 Td ({pagador_endereco}) Tj ET",
        f"BT /F1 10 Tf 490 582 Td ({pagador_doc}) Tj ET",

        # --- Ficha de Compensação (base) ---
        "50 80 495 460 re S",
        # Cabeçalho banco + linha digitável (repete)
        "50 512 495 28 re S",
        "50 512 m 140 540 l S",
        "140 512 m 140 540 l S",
        f"BT /F1 12 Tf 60 524 Td ({banco_nome}) Tj ET",
        "BT /F1 8 Tf 330 538 Td (Linha Digitavel) Tj ET",
        f"BT /F1 12 Tf 330 524 Td ({linha_digitavel}) Tj ET",

        # Campos principais
        "50 500 m 545 500 l S",
        "50 470 m 545 470 l S",
        "50 440 m 545 440 l S",
        "50 410 m 545 410 l S",
        "50 380 m 545 380 l S",
        "50 350 m 545 350 l S",
        "50 320 m 545 320 l S",

        # Colunas
        "370 500 m 370 540 l S",
        "320 470 m 320 500 l S",
        "240 440 m 240 470 l S",
        "420 440 m 420 500 l S",
        "120 410 m 120 440 l S",
        "200 410 m 200 440 l S",
        "280 410 m 280 440 l S",
        "360 410 m 360 440 l S",
        "440 410 m 440 440 l S",
        "140 380 m 140 410 l S",
        "240 380 m 240 410 l S",
        "320 380 m 320 410 l S",
        "400 380 m 400 410 l S",
        "480 380 m 480 410 l S",

        # Títulos
        "BT /F1 12 Tf 60 540 Td (Ficha de Compensacao) Tj ET",
        "BT /F1 8 Tf 60 508 Td (Local do Pagamento) Tj ET",
        "BT /F1 8 Tf 380 508 Td (Data de Vencimento) Tj ET",
        "BT /F1 8 Tf 60 478 Td (Nome do Beneficiario) Tj ET",
        "BT /F1 8 Tf 330 478 Td (Agencia/Codigo do Beneficiario) Tj ET",
        "BT /F1 8 Tf 60 448 Td (Nosso numero) Tj ET",
        "BT /F1 8 Tf 250 448 Td (Numero do documento) Tj ET",
        "BT /F1 8 Tf 430 448 Td (Valor do Documento) Tj ET",
        "BT /F1 8 Tf 60 418 Td (CNPJ) Tj ET",
        "BT /F1 8 Tf 130 418 Td (Nr. do documento) Tj ET",
        "BT /F1 8 Tf 210 418 Td (Esp. Doc) Tj ET",
        "BT /F1 8 Tf 290 418 Td (Aceite) Tj ET",
        "BT /F1 8 Tf 370 418 Td (Data Proces.) Tj ET",
        "BT /F1 8 Tf 450 418 Td (Nosso numero) Tj ET",
        "BT /F1 8 Tf 60 388 Td (Uso do Banco) Tj ET",
        "BT /F1 8 Tf 150 388 Td (Data Documento) Tj ET",
        "BT /F1 8 Tf 250 388 Td (Carteira) Tj ET",
        "BT /F1 8 Tf 330 388 Td (Especie) Tj ET",
        "BT /F1 8 Tf 410 388 Td (Quantidade) Tj ET",
        "BT /F1 8 Tf 490 388 Td ((x) Valor) Tj ET",

        # Valores
        f"BT /F1 10 Tf 380 495 Td ({due_date}) Tj ET",
        "BT /F1 10 Tf 60 495 Td (Pagavel em qualquer banco ate o vencimento.) Tj ET",
        f"BT /F1 10 Tf 60 465 Td ({beneficiario}) Tj ET",
        f"BT /F1 10 Tf 330 465 Td ({agencia_conta}) Tj ET",
        f"BT /F1 10 Tf 60 435 Td ({nosso_numero}) Tj ET",
        f"BT /F1 10 Tf 250 435 Td ({doc_num}) Tj ET",
        f"BT /F1 10 Tf 430 435 Td ({valor}) Tj ET",
        f"BT /F1 10 Tf 60 405 Td ({cnpj}) Tj ET",
        f"BT /F1 10 Tf 130 405 Td ({doc_num}) Tj ET",
        "BT /F1 10 Tf 210 405 Td (DM) Tj ET",
        "BT /F1 10 Tf 290 405 Td (N) Tj ET",
        f"BT /F1 10 Tf 370 405 Td ({data_doc}) Tj ET",
        f"BT /F1 10 Tf 450 405 Td ({nosso_numero}) Tj ET",
        f"BT /F1 10 Tf 150 375 Td ({data_doc}) Tj ET",
        f"BT /F1 10 Tf 250 375 Td ({getattr(conta, 'carteira', '17') or '17'}) Tj ET",
        "BT /F1 10 Tf 330 375 Td (R$) Tj ET",
        f"BT /F1 10 Tf 490 375 Td ({valor}) Tj ET",

        # Sacado / CPF
        "50 350 m 545 350 l S",
        "BT /F1 8 Tf 60 358 Td (Pagador) Tj ET",
        "BT /F1 8 Tf 490 358 Td (CPF/CNPJ) Tj ET",
        f"BT /F1 10 Tf 60 342 Td ({pagador_nome}) Tj ET",
        f"BT /F1 10 Tf 60 327 Td ({pagador_endereco}) Tj ET",
        f"BT /F1 10 Tf 490 342 Td ({pagador_doc}) Tj ET",

        # Código de barras
        "BT /F1 8 Tf 60 100 Td (Codigo de Barras) Tj ET",
    ]
    # Código de barras: posição inferior e tamanho ajustado ao espaço
    BARCODE_X = 55
    BARCODE_Y = 92
    BARCODE_W = 490
    BARCODE_H = 70
    barcode_num = _num(conta.banco) + _num(nosso_numero or doc_num) + _num(valor)
    conteudo_pdf.extend(
        _codigo_barras_itf(
            barcode_num[:44].ljust(44, "0"),
            BARCODE_X,
            BARCODE_Y,
            BARCODE_W,
            BARCODE_H,
        )
    )
    conteudo_bytes = "\n".join(conteudo_pdf).encode("latin-1")

    header = b"%PDF-1.4\n"
    objs = []
    offsets = []

    def add_obj(data: bytes) -> None:
        offsets.append(len(header) + sum(len(o) for o in objs))
        objs.append(data)

    add_obj(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    add_obj(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    add_obj(
        b"3 0 obj << /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 595 842] /Contents 5 0 R >> endobj\n"
    )
    add_obj(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    add_obj(
        b"5 0 obj << /Length "
        + str(len(conteudo_bytes)).encode("latin-1")
        + b" >> stream\n"
        + conteudo_bytes
        + b"\nendstream endobj\n"
    )
    
    xref_inicio = len(header) + sum(len(o) for o in objs)
    xref = ["xref", "0 6", "0000000000 65535 f "]
    for off in offsets:
        xref.append(f"{off:010d} 00000 n ")
    xref_bytes = "\n".join(xref).encode("latin-1") + b"\n"
    trailer = (
        "trailer<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(xref_inicio)
        + "\n%%EOF"
    ).encode("latin-1")

    with open(filepath, "wb") as f:
        # Escreve o conteúdo completo do PDF no caminho indicado.
        f.write(header + b"".join(objs) + xref_bytes + trailer)
