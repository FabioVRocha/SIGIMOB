from datetime import date
from caixa_banco import db


class EmpresaLicenciada(db.Model):
    __tablename__ = 'empresa_licenciada'

    id = db.Column(db.Integer, primary_key=True)
    documento = db.Column(db.String(20), unique=True, nullable=False)
    razao_social_nome = db.Column(db.String(255), nullable=False)
    nome_fantasia = db.Column(db.String(255))
    endereco = db.Column(db.String(255))
    bairro = db.Column(db.String(100))
    cidade = db.Column(db.String(100))
    estado = db.Column(db.String(2))
    cep = db.Column(db.String(10))
    telefone = db.Column(db.String(20))
    observacao = db.Column(db.Text)
    status = db.Column(db.String(10), default='Ativo')
    data_cadastro = db.Column(db.DateTime, default=db.func.now())

class Pessoa(db.Model):
    __tablename__ = 'pessoas'

    id = db.Column(db.Integer, primary_key=True)
    documento = db.Column(db.String(20))
    razao_social_nome = db.Column(db.String(255))
    endereco = db.Column(db.String(255))
    bairro = db.Column(db.String(100))
    cidade = db.Column(db.String(100))
    estado = db.Column(db.String(2))
    cep = db.Column(db.String(10))



class ContaReceber(db.Model):
    __tablename__ = 'contas_a_receber'

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, nullable=False)
    titulo = db.Column(db.String(255))
    data_vencimento = db.Column(db.Date, nullable=False)
    valor_previsto = db.Column(db.Numeric(10, 2), nullable=False)
    data_pagamento = db.Column(db.Date)
    valor_pago = db.Column(db.Numeric(10, 2))
    status_conta = db.Column(db.String(20), default='Aberta')
    nosso_numero = db.Column(db.String(20))

    def marcar_pago(self, valor):
        valor_decimal = Decimal(str(valor))
        pago_atual = Decimal(self.valor_pago or 0)
        total_pago = pago_atual + valor_decimal
        self.valor_pago = total_pago
        self.data_pagamento = date.today()
        if total_pago >= Decimal(self.valor_previsto):
            self.status_conta = 'Paga'
        else:
            self.status_conta = 'Parcial'
