"""Geração simplificada de boletos em PDF.

O objetivo desta rotina é produzir um arquivo PDF com layout básico de
boleto bancário sem depender de bibliotecas externas. São utilizados
comandos PDF diretos para desenhar caixas e textos, possibilitando que o
arquivo final seja visualizado em leitores de PDF comuns.

Esta implementação foi ajustada para que o layout se aproxime do arquivo
``Modelo Boleto.pdf`` disponibilizado na raiz do projeto. O desenho dos
principais campos do boleto é feito manualmente através de comandos PDF
como ``re`` (retângulos) e ``m/l`` (movimentos de linha).
"""


def gerar_pdf_boleto(titulo, empresa, conta, filepath: str) -> None:
    """Gera um PDF de boleto com layout semelhante ao modelo fornecido.

    Os dados do beneficiário e da conta bancária são preenchidos de acordo
    com os registros ``Empresa Licenciada`` e ``Contas Bancárias``
    cadastrados no sistema.
    """

    due_date = titulo.data_vencimento.strftime('%d/%m/%Y')
    valor = f"{float(titulo.valor_previsto):.2f}"
    nosso_numero = titulo.nosso_numero or ""
    doc_num = str(titulo.id)
    beneficiario = empresa.razao_social_nome
    agencia_conta = f"{conta.agencia}/{conta.conta}"
    banco_nome = conta.nome_banco or conta.banco
    linha_digitavel = "Linha Digitavel"

    conteudo_pdf = [
        "0.5 w",  # espessura das linhas
        # Cabeçalho superior com banco e linha digitável
        "50 750 500 25 re S",
        "200 750 m 200 775 l S",
        f"BT /F1 12 Tf 60 760 Td ({banco_nome}) Tj ET",
        f"BT /F1 12 Tf 210 760 Td ({linha_digitavel}) Tj ET",
        # Moldura principal
        "50 450 500 300 re S",
        # Linhas horizontais
        "50 720 m 550 720 l S",
        "50 680 m 550 680 l S",
        "50 640 m 550 640 l S",
        "50 600 m 550 600 l S",
        # Linhas verticais para dividir colunas
        "300 720 m 300 750 l S",
        "300 680 m 300 720 l S",
        "200 640 m 200 680 l S",
        "360 640 m 360 720 l S",
        # Textos
        "BT /F1 14 Tf 60 730 Td (Boleto Bancario) Tj ET",
        "BT /F1 8 Tf 60 705 Td (Local do Pagamento) Tj ET",
        "BT /F1 8 Tf 360 705 Td (Data de Vencimento) Tj ET",
        "BT /F1 10 Tf 60 690 Td (Pagavel em qualquer banco ate o vencimento.) Tj ET",
        f"BT /F1 10 Tf 360 690 Td ({due_date}) Tj ET",
        "BT /F1 8 Tf 60 665 Td (Nome do Beneficiario) Tj ET",
        "BT /F1 8 Tf 360 665 Td (Agencia/Codigo do Beneficiario) Tj ET",
        f"BT /F1 10 Tf 60 650 Td ({beneficiario}) Tj ET",
        f"BT /F1 10 Tf 360 650 Td ({agencia_conta}) Tj ET",
        "BT /F1 8 Tf 60 625 Td (Nosso numero) Tj ET",
        "BT /F1 8 Tf 200 625 Td (Numero do documento) Tj ET",
        "BT /F1 8 Tf 360 625 Td (Valor do Documento) Tj ET",
        f"BT /F1 10 Tf 60 610 Td ({nosso_numero}) Tj ET",
        f"BT /F1 10 Tf 200 610 Td ({doc_num}) Tj ET",
        f"BT /F1 10 Tf 360 610 Td ({valor}) Tj ET",
    ]
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
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >> endobj\n"
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
        f.write(header + b"".join(objs) + xref_bytes + trailer)