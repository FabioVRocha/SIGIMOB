"""Geração simplificada de boletos em PDF.

Esta rotina produz um boleto bancário em formato PDF sem depender de
bibliotecas externas. Todo o layout é desenhado "na mão" por meio de
comandos PDF diretos (``re`` para retângulos, ``m``/``l`` para linhas e
``Tj`` para textos), o que garante portabilidade do arquivo para qualquer
leitor de PDF.

O desenho foi calibrado para se assemelhar ao arquivo ``Modelo
Boleto.pdf`` disponível na raiz do projeto. O arquivo serve como base de
referência visual e os elementos abaixo procuram replicar seus campos
principais, permitindo que o boleto gerado seja facilmente reconhecido
por sistemas bancários e usuários finais. A ideia é gerar um boleto
funcional o suficiente para testes e integrações, contendo os campos
usuais do documento bancário.
"""

from datetime import datetime

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
    cnpj = empresa.documento or ""
    data_doc = datetime.now().strftime('%d/%m/%Y')

    conteudo_pdf = [
        "0.5 w",  # espessura das linhas
        "BT /F1 12 Tf 60 780 Td (Recibo do Pagador) Tj ET",
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
        "BT /F1 8 Tf 60 585 Td (CNPJ) Tj ET",
        "BT /F1 8 Tf 140 585 Td (Nr. do documento) Tj ET",
        "BT /F1 8 Tf 260 585 Td (Esp. Doc) Tj ET",
        "BT /F1 8 Tf 340 585 Td (Aceite) Tj ET",
        "BT /F1 8 Tf 420 585 Td (Data Proces.) Tj ET",
        "BT /F1 8 Tf 500 585 Td (Nosso numero) Tj ET",
        f"BT /F1 10 Tf 60 570 Td ({cnpj}) Tj ET",
        f"BT /F1 10 Tf 140 570 Td ({doc_num}) Tj ET",
        "BT /F1 10 Tf 260 570 Td (DM) Tj ET",
        "BT /F1 10 Tf 340 570 Td (N) Tj ET",
        f"BT /F1 10 Tf 420 570 Td ({data_doc}) Tj ET",
        f"BT /F1 10 Tf 500 570 Td ({nosso_numero}) Tj ET",
        "BT /F1 8 Tf 60 545 Td (Uso do Banco) Tj ET",
        "BT /F1 8 Tf 140 545 Td (Data Documento) Tj ET",
        "BT /F1 8 Tf 260 545 Td (Carteira) Tj ET",
        "BT /F1 8 Tf 340 545 Td (Especie) Tj ET",
        "BT /F1 8 Tf 420 545 Td (Quantidade) Tj ET",
        "BT /F1 8 Tf 500 545 Td ((x) Valor) Tj ET",
        f"BT /F1 10 Tf 140 530 Td ({data_doc}) Tj ET",
        "BT /F1 10 Tf 260 530 Td (17) Tj ET",
        "BT /F1 10 Tf 340 530 Td (R$) Tj ET",
        f"BT /F1 10 Tf 500 530 Td ({valor}) Tj ET",
        "BT /F1 8 Tf 60 505 Td (Informacoes de Responsabilidade do Beneficiario) Tj ET",
        "BT /F1 8 Tf 500 505 Td ((=) Valor do Documento) Tj ET",
        f"BT /F1 10 Tf 500 490 Td ({valor}) Tj ET",
        "BT /F1 8 Tf 60 470 Td (Nome do Pagador / Endereco) Tj ET",
        "BT /F1 8 Tf 500 470 Td (CPF) Tj ET",
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