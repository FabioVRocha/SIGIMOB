import sys
from pathlib import Path
from datetime import date, timedelta
from flask import Flask

sys.path.append(str(Path(__file__).resolve().parents[1]))

from caixa_banco import init_app as init_caixa, db
from contas_receber import init_app as init_contas
from contas_receber.models import ContaReceber, Pessoa, ReceitaCadastro


def setup_app():
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    init_caixa(app)
    init_contas(app)
    return app


def test_cobrancas_titulos_includes_vencidos():
    app = setup_app()
    with app.app_context():
        cliente = Pessoa(documento='1', razao_social_nome='Cliente')
        db.session.add(cliente)
        receita = ReceitaCadastro(descricao='Aluguel')
        db.session.add(receita)
        db.session.flush()
        titulo = ContaReceber(
            cliente_id=cliente.id,
            receita_id=receita.id,
            titulo='Teste Vencido',
            data_vencimento=date.today() - timedelta(days=1),
            valor_previsto=100.0,
            status_conta='Vencida',
        )
        db.session.add(titulo)
        db.session.commit()

        hoje = date.today()
        titulos = (
            db.session.query(ContaReceber, Pessoa)
            .join(Pessoa, ContaReceber.cliente_id == Pessoa.id)
            .filter(
                ContaReceber.status_conta.in_(["Aberta", "Parcial", "Vencida"]),
                ContaReceber.data_vencimento < hoje,
            )
            .all()
        )
        assert len(titulos) == 1
        assert titulos[0][0].id == titulo.id
