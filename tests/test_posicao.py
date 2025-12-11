from datetime import date
from flask import Flask
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from caixa_banco import init_app as init_caixa, db
from caixa_banco.models import ContaCaixa, PosicaoDiaria
from caixa_banco.services import criar_movimento, recalcular_posicoes


def setup_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    init_caixa(app)
    with app.app_context():
        db.create_all()
        caixa = ContaCaixa(
            nome='Caixa Principal',
            saldo_inicial=100.0,
            saldo_atual=100.0,
            data_saldo_inicial=date(2024, 1, 1),
        )
        db.session.add(caixa)
        db.session.commit()
    return app


def test_recalculo_posicoes():
    app = setup_app()
    with app.app_context():
        # Movimento de entrada em 05/01
        criar_movimento(
            {
                'conta_origem_id': 1,
                'conta_origem_tipo': 'caixa',
                'data_movimento': date(2024, 1, 5),
                'tipo': 'entrada',
                'valor': 50.0,
            }
        )

        # Calcula posições desde o início
        recalcular_posicoes(date(2024, 1, 1))
        pos = PosicaoDiaria.query.filter_by(
            conta_id=1, conta_tipo='caixa', data=date(2024, 1, 5)
        ).first()
        assert float(pos.saldo) == 150.0

        # Movimento retroativo de saída em 03/01
        criar_movimento(
            {
                'conta_origem_id': 1,
                'conta_origem_tipo': 'caixa',
                'data_movimento': date(2024, 1, 3),
                'tipo': 'saida',
                'valor': 20.0,
            }
        )

        # Recalcula posições desde 01/01 devido à alteração retroativa
        recalcular_posicoes(date(2024, 1, 1))
        pos = PosicaoDiaria.query.filter_by(
            conta_id=1, conta_tipo='caixa', data=date(2024, 1, 5)
        ).first()
        assert float(pos.saldo) == 130.0
