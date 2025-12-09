from datetime import date
from caixa_banco import db
from contas_receber.models import ContaReceber


class Cobranca(db.Model):
    __tablename__ = 'cobrancas'

    id = db.Column(db.Integer, primary_key=True)
    conta_id = db.Column(db.Integer, db.ForeignKey('contas_a_receber.id'), nullable=False)
    cobrador = db.Column(db.String(255))
    contato = db.Column(db.String(255))
    data_cobranca = db.Column(db.Date, default=date.today, nullable=False)
    historico = db.Column(db.Text)
    data_prevista_pagamento = db.Column(db.Date)

    conta = db.relationship('ContaReceber', backref=db.backref('cobrancas', lazy=True))