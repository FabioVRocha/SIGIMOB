import os
from datetime import datetime
from flask import current_app
from caixa_banco import db
from caixa_banco.models import ContaBanco
from .models import EmpresaLicenciada, ContaReceber, Pessoa
from .cnab import CNAB240Writer, CNAB240Reader, Titulo
from .pdf import gerar_pdf_boleto


def gerar_boletos(ids):
    empresa = EmpresaLicenciada.query.first()
    if not empresa:
        raise ValueError("Empresa licenciada não cadastrada")
    conta = ContaBanco.query.first()
    if not conta:
        raise ValueError("Conta bancária não cadastrada")
    titulos = ContaReceber.query.filter(ContaReceber.id.in_(ids)).all()
    if not titulos:
        raise ValueError("Nenhum título encontrado")
    # garante nosso número
    for t in titulos:
        if not t.nosso_numero:
            t.nosso_numero = f"{t.id:010d}"
    cnab_titulos = [Titulo(t.nosso_numero, float(t.valor_previsto)) for t in titulos]
    writer = CNAB240Writer(empresa, conta)
    remessa = writer.gerar(cnab_titulos)
    base = current_app.config.get('UPLOAD_FOLDER', '.')
    boletos_dir = os.path.join(base, 'boletos')
    rem_dir = os.path.join(base, 'remessas')
    os.makedirs(boletos_dir, exist_ok=True)
    os.makedirs(rem_dir, exist_ok=True)
    pdfs = []
    for t in titulos:
        cliente = Pessoa.query.get(t.cliente_id)
        if not cliente:
            raise ValueError("Cliente não encontrado")
        pdf_path = os.path.join(boletos_dir, f"boleto_{t.id}.pdf")
        gerar_pdf_boleto(t, empresa, conta, cliente, pdf_path)
        pdfs.append(pdf_path)
    rem_path = os.path.join(rem_dir, f"remessa_{datetime.now().strftime('%Y%m%d%H%M%S')}.rem")
    with open(rem_path, 'w') as f:
        f.write(remessa)
    db.session.commit()
    return {'pdfs': pdfs, 'remessa': rem_path}


def importar_retorno(conteudo: str):
    reader = CNAB240Reader(conteudo)
    baixados = []
    erros = []
    for nosso_numero, valor in reader.titulos_pagados():
        titulo = ContaReceber.query.filter_by(nosso_numero=nosso_numero).first()
        if not titulo:
            erros.append({'nosso_numero': nosso_numero, 'erro': 'Título não encontrado'})
            continue
        titulo.marcar_pago(valor)
        baixados.append({'id': titulo.id, 'valor_pago': valor})
    db.session.commit()
    return {'baixados': baixados, 'erros': erros}