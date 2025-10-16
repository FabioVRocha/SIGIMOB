import os
import re
from datetime import datetime
from flask import current_app
from caixa_banco import db
from caixa_banco.models import ContaBanco
from .models import EmpresaLicenciada, ContaReceber, Pessoa
from .cnab import CNAB240Writer, CNAB240Reader, Titulo
from .pdf import gerar_pdf_boleto


def _digits(value):
    return re.sub(r"\D", "", value or "")


def _tipo_inscricao(value):
    doc = _digits(value)
    return '2' if len(doc) == 14 else '1'


def gerar_boletos(ids):
    empresa = EmpresaLicenciada.query.first()
    if not empresa:
        raise ValueError("Empresa licenciada nao cadastrada")
    conta = ContaBanco.query.first()
    if not conta:
        raise ValueError("Conta bancaria nao cadastrada")
    titulos = ContaReceber.query.filter(ContaReceber.id.in_(ids)).all()
    if not titulos:
        raise ValueError("Nenhum titulo encontrado")

    clientes = {}
    cnab_titulos = []
    hoje = datetime.now().date()

    for titulo in titulos:
        if not titulo.nosso_numero:
            titulo.nosso_numero = f"{titulo.id:010d}"
        cliente = clientes.get(titulo.cliente_id)
        if cliente is None:
            cliente = Pessoa.query.get(titulo.cliente_id)
            if not cliente:
                raise ValueError("Cliente nao encontrado")
            clientes[titulo.cliente_id] = cliente
        numero_documento = (titulo.titulo or f"{titulo.id:06d}")[:15]
        uso_empresa = (titulo.titulo or f"{titulo.id:06d}")[:25]
        cnab_titulos.append(
            Titulo(
                nosso_numero=titulo.nosso_numero,
                valor=float(titulo.valor_previsto),
                numero_documento=numero_documento,
                data_vencimento=titulo.data_vencimento,
                data_emissao=hoje,
                juros_mora=float(conta.juros_mora or 0),
                multa=float(conta.multa or 0),
                tipo_inscricao_pagador=_tipo_inscricao(getattr(cliente, 'documento', '')),
                documento_pagador=_digits(getattr(cliente, 'documento', '')),
                nome_pagador=cliente.razao_social_nome or '',
                endereco_pagador=cliente.endereco or '',
                bairro_pagador=cliente.bairro or '',
                cep_pagador=cliente.cep or '',
                cidade_pagador=cliente.cidade or '',
                uf_pagador=cliente.estado or '',
                uso_empresa=uso_empresa,
            )
        )

    writer = CNAB240Writer(empresa, conta)
    remessa = writer.gerar(cnab_titulos)

    base = current_app.config.get('UPLOAD_FOLDER', '.')
    boletos_dir = os.path.join(base, 'boletos')
    rem_dir = os.path.join(base, 'remessas')
    os.makedirs(boletos_dir, exist_ok=True)
    os.makedirs(rem_dir, exist_ok=True)

    pdfs = []
    for titulo in titulos:
        cliente = clientes[titulo.cliente_id]
        pdf_path = os.path.join(boletos_dir, f"boleto_{titulo.id}.pdf")
        gerar_pdf_boleto(titulo, empresa, conta, cliente, pdf_path)
        pdfs.append(pdf_path)

    rem_path = os.path.join(rem_dir, f"remessa_{datetime.now().strftime('%Y%m%d%H%M%S')}.rem")
    with open(rem_path, 'wb') as arquivo:
        arquivo.write(remessa.encode('ascii'))
    db.session.commit()
    return {'pdfs': pdfs, 'remessa': rem_path}


def importar_retorno(conteudo: str):
    reader = CNAB240Reader(conteudo)
    baixados = []
    erros = []
    for nosso_numero, valor in reader.titulos_pagados():
        titulo = ContaReceber.query.filter_by(nosso_numero=nosso_numero).first()
        if not titulo:
            erros.append({'nosso_numero': nosso_numero, 'erro': 'Titulo nao encontrado'})
            continue
        titulo.marcar_pago(valor)
        baixados.append({'id': titulo.id, 'valor_pago': valor})
    db.session.commit()
    return {'baixados': baixados, 'erros': erros}
