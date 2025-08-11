def gerar_pdf_boleto(titulo, filepath: str):
    """Gera um arquivo PDF simples contendo informações do boleto.

    A implementação continua independente de bibliotecas externas, porém
    agora escreve um conteúdo que os visualizadores de PDF conseguem
    renderizar corretamente. O arquivo final possui uma página com texto
    básico descrevendo o título gerado.
    """
    
    linhas = [
        f"Boleto - Título {titulo.id}",
        f"Nosso número: {titulo.nosso_numero}",
        f"Valor: {float(titulo.valor_previsto):.2f}",
        f"Vencimento: {titulo.data_vencimento.isoformat()}",
    ]

    # Monta o stream de conteúdo com comandos PDF para exibir texto
    # O operador "Td" posiciona o texto de forma relativa, por isso
    # definimos a posição inicial uma única vez e depois movimentamos o
    # cursor apenas na direção vertical. A forma anterior usava
    # coordenadas absolutas com "Td", o que fazia apenas a primeira linha
    # ficar visível no documento gerado.

    conteudo_pdf = ["BT", "/F1 12 Tf", "72 750 Td"]
    primeira = True
    for linha in linhas:
        if primeira:
            conteudo_pdf.append(f"({linha}) Tj")
            primeira = False
        else:
            # Move 14 pontos para baixo a cada nova linha
            conteudo_pdf.append(f"0 -14 Td ({linha}) Tj")
    conteudo_pdf.append("ET")
    conteudo_bytes = "\n".join(conteudo_pdf).encode("latin-1")

    header = b"%PDF-1.4\n"
    objs = []
    offsets = []

    def add_obj(data: bytes):
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