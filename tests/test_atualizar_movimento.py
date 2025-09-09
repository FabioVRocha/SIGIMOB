from datetime import date
from flask import Flask
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from caixa_banco import init_app as init_caixa, db
from caixa_banco.models import ContaCaixa
from caixa_banco.services import criar_movimento, atualizar_movimento


def setup_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    init_caixa(app)
    with app.app_context():
        db.create_all()
        caixa = ContaCaixa(
            nome='Caixa Teste',
            saldo_inicial=100.0,
            saldo_atual=100.0,
            data_saldo_inicial=date(2024, 1, 1),
        )
        db.session.add(caixa)
        db.session.commit()
    return app


def test_atualizar_movimento_data_string():
    app = setup_app()
    with app.app_context():
        movimento = criar_movimento(
            {
                'conta_origem_id': 1,
                'conta_origem_tipo': 'caixa',
                'data_movimento': date(2024, 1, 5),
                'tipo': 'entrada',
                'valor': 50.0,
            }
        )
        atualizar_movimento(movimento, {'data_movimento': '2024-01-03'})
        assert movimento.data_movimento == date(2024, 1, 3)