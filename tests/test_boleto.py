import os
import sys
from pathlib import Path
from datetime import date
from flask import Flask

sys.path.append(str(Path(__file__).resolve().parents[1]))

from caixa_banco import init_app as init_caixa, db
from contas_receber import init_app as init_contas
from caixa_banco.models import ContaBanco
from contas_receber.models import EmpresaLicenciada, ContaReceber, Pessoa
from contas_receber.services import gerar_boletos, importar_retorno
from contas_receber.routes import _barcode_html
from contas_receber.boleto_utils import linha_digitavel, codigo_barras_numero, digits
from contas_receber.cnab import CNAB240Writer, Titulo


def setup_app(tmp_path):
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = str(tmp_path)
    init_caixa(app)
    init_contas(app)
    with app.app_context():
        db.create_all()
        emp = EmpresaLicenciada(documento='123', razao_social_nome='Empresa Teste')
        db.session.add(emp)
        conta = ContaBanco(banco='001', nome_banco='Banco', agencia='1234', conta='5678')
        db.session.add(conta)
        cliente = Pessoa(
            documento='00000000000',
            razao_social_nome='Cliente Teste',
            endereco='Rua 1',
            bairro='Centro',
            cidade='Cidade',
            estado='ST',
            cep='00000-000',
        )
        db.session.add(cliente)
        db.session.flush()
        titulo = ContaReceber(
            cliente_id=cliente.id,
            titulo='Teste',
            data_vencimento=date.today(),
            valor_previsto=100.00,
        )
        db.session.add(titulo)
        db.session.commit()
    return app


def test_gerar_boletos(tmp_path):
    app = setup_app(tmp_path)
    with app.app_context():
        resultado = gerar_boletos([1])
        assert os.path.exists(resultado['remessa'])
        assert len(resultado['pdfs']) == 1
        with open(resultado['pdfs'][0], 'rb') as f:
            conteudo = f.read()
        # Verifica se os principais campos do layout foram inseridos
        assert b'Boleto Bancario' in conteudo
        assert b'Local do Pagamento' in conteudo
        assert b'Data de Vencimento' in conteudo
        assert b'Linha Digitavel' in conteudo
        assert b'Nosso numero' in conteudo
        assert b'Empresa Teste' in conteudo
        assert b'1234/5678' in conteudo
        assert b'Recibo do Pagador' in conteudo
        assert b'Ficha de Compensacao' in conteudo
        assert b'Codigo de Barras' in conteudo
        assert b'CNPJ' in conteudo
        assert b'Uso do Banco' in conteudo
        assert b'CPF/CNPJ' in conteudo
        assert b'Cliente Teste' in conteudo
        assert b'00000000000' in conteudo


def test_preview_boleto_html(tmp_path):
    app = setup_app(tmp_path)
    with app.app_context():
        client = app.test_client()
        resp = client.get('/api/contas-receber/1/boleto')
        assert resp.status_code == 200
        assert b'Boleto Banc\xc3\xa1rio' in resp.data
        assert b'Cliente Teste' in resp.data
        assert b"<div id=\"barcode\"><span" in resp.data
        assert b".n {border-left: 1px solid}" in resp.data


def test_importar_retorno(tmp_path):
    app = setup_app(tmp_path)
    with app.app_context():
        gerar_boletos([1])
        titulo = ContaReceber.query.get(1)
        writer = CNAB240Writer(EmpresaLicenciada.query.first(), ContaBanco.query.first())
        cnab = writer.gerar([Titulo(titulo.nosso_numero, float(titulo.valor_previsto))])
        resultado = importar_retorno(cnab)
        titulo = ContaReceber.query.get(1)
        assert titulo.status_conta == 'Paga'
        assert resultado['baixados'][0]['id'] == 1


def test_pagamento_parcial(tmp_path):
    app = setup_app(tmp_path)
    with app.app_context():
        client = app.test_client()
        # paga parcialmente
        resp = client.post('/api/contas-receber/1/pagamento', json={'valor': 40})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'Parcial'
        assert data['valor_pago'] == 40.0
        assert data['valor_pendente'] == 60.0
        # paga restante
        resp = client.post('/api/contas-receber/1/pagamento', json={'valor': 60})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'Paga'
        assert data['valor_pago'] == 100.0
        assert data['valor_pendente'] == 0.0


def test_barcode_html_interleaved():
    start = (
        "<span class='n'></span><span class='n s'></span>"
        "<span class='n'></span><span class='n s'></span>"
    )
    pair12 = (
        "<span class='w'></span><span class='n s'></span>"
        "<span class='n'></span><span class='w s'></span>"
        "<span class='n'></span><span class='n s'></span>"
        "<span class='n'></span><span class='n s'></span>"
        "<span class='w'></span><span class='w s'></span>"
    )
    stop = "<span class='w'></span><span class='n s'></span><span class='n'></span>"
    expected = start + pair12 + stop
    assert _barcode_html('12') == expected


def test_linha_digitavel_and_barcode_alignment(tmp_path):
    app = setup_app(tmp_path)
    with app.app_context():
        conta = ContaBanco.query.first()
        titulo = ContaReceber.query.get(1)
        documento = str(titulo.id)
        linha = linha_digitavel(
            conta,
            titulo.nosso_numero or '',
            titulo.data_vencimento,
            float(titulo.valor_previsto),
            documento,
        )
        codigo = codigo_barras_numero(
            conta,
            titulo.nosso_numero or '',
            documento,
            float(titulo.valor_previsto),
            titulo.data_vencimento,
        )

        assert len(codigo) == 44

        numeros = digits(linha)
        assert len(numeros) == 47

        campo1 = numeros[:9]
        dv1 = numeros[9]
        campo2 = numeros[10:20]
        dv2 = numeros[20]
        campo3 = numeros[21:31]
        dv3 = numeros[31]
        dv = numeros[32]
        campo5 = numeros[33:]

        def mod10(valor):
            soma = 0
            peso = 2
            for digito in reversed(valor):
                parcial = int(digito) * peso
                soma += parcial // 10 + parcial % 10
                peso = 1 if peso == 2 else 2
            return str((10 - (soma % 10)) % 10)

        pesos = [2, 3, 4, 5, 6, 7, 8, 9]

        def mod11(valor):
            soma = 0
            idx = 0
            for digito in reversed(valor):
                soma += int(digito) * pesos[idx]
                idx = (idx + 1) % len(pesos)
            resto = soma % 11
            resultado = 11 - resto
            if resultado in (0, 10, 11):
                return '1'
            return str(resultado)

        assert mod10(campo1) == dv1
        assert mod10(campo2) == dv2
        assert mod10(campo3) == dv3

        campo_livre = campo1[4:] + campo2 + campo3
        reconstruido = campo1[:4] + dv + campo5[:4] + campo5[4:] + campo_livre
        assert codigo == reconstruido
        assert mod11(codigo[:4] + codigo[5:]) == dv


def test_gerar_boleto_handles_unexpected_error(tmp_path, monkeypatch):
    app = setup_app(tmp_path)
    with app.app_context():
        def boom(ids):
            raise RuntimeError('boom')

        import contas_receber.routes as routes
        monkeypatch.setattr(routes, 'gerar_boletos', boom)

        client = app.test_client()
        resp = client.post('/api/contas-receber/1/boleto')
        assert resp.status_code == 500
        data = resp.get_json()
        assert data['error'] == 'boom'
