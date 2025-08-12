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
from contas_receber.cnab import CNAB240Writer, Titulo


def setup_app(tmp_path):
    app = Flask(__name__)
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
