def gerar_pdf_boleto(titulo, filepath: str):
    """Gera um arquivo PDF simples com informações básicas do boleto.

    Esta implementação não depende de bibliotecas externas e grava um
    PDF mínimo contendo texto plano. É suficiente para testes e para
    oferecer um arquivo para download.
    """
    conteudo = (
        f"Boleto - Título {titulo.id}\n"
        f"Nosso número: {titulo.nosso_numero}\n"
        f"Valor: {float(titulo.valor_previsto):.2f}\n"
        f"Vencimento: {titulo.data_vencimento.isoformat()}\n"
    )
    # Construção de um PDF mínimo com uma página e texto simples
    texto_bytes = conteudo.encode('latin-1')
    header = b"%PDF-1.1\n1 0 obj<<>>endobj\n"
    stream = (
        b"2 0 obj<< /Length "
        + str(len(texto_bytes) + 1).encode()
        + b" >>stream\n"
        + texto_bytes
        + b"\nendstream endobj\n"
    )
    body = (
        b"3 0 obj<< /Type /Page /Parent 4 0 R /Contents 2 0 R>>endobj\n"
        b"4 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1>>endobj\n"
        b"5 0 obj<< /Type /Catalog /Pages 4 0 R>>endobj\n"
    )
    xref = b"xref\n0 6\n0000000000 65535 f \n0000000010 00000 n \n0000000053 00000 n \n0000000114 00000 n \n0000000165 00000 n \n0000000223 00000 n \n"
    trailer = b"trailer<< /Root 5 0 R /Size 6>>\nstartxref\n274\n%%EOF"
    with open(filepath, 'wb') as f:
        f.write(header + stream + body + xref + trailer)