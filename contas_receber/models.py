from datetime import date
from decimal import Decimal
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


class ReceitaCadastro(db.Model):
    """Representa as categorias de receita disponíveis para as contas."""

    __tablename__ = 'receitas_cadastro'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(255), nullable=False)
    data_cadastro = db.Column(db.DateTime, server_default=db.func.now())


class OrigemCadastro(db.Model):
    """Modela a tabela ``origens_cadastro`` utilizada como FK em contas a receber.

    A aplicação realiza operações diretas via SQL bruto para essa tabela em
    diversos pontos. Durante a inicialização em ambientes de desenvolvimento o
    módulo pode ser carregado mais de uma vez (por exemplo, pelo reloader do
    Flask), o que fazia com que o SQLAlchemy reclamasse da redefinição da
    tabela. Ao informar ``extend_existing=True`` garantimos que, se a tabela já
    estiver presente no metadata, a definição seja reutilizada em vez de
    disparar um ``InvalidRequestError``.
    """

    __tablename__ = 'origens_cadastro'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(255), nullable=False)
    data_cadastro = db.Column(db.DateTime, server_default=db.func.now())

    contas = db.relationship(
        'ContaReceber',
        backref=db.backref('origem', lazy=True),
        lazy=True,
    )


class ContaReceber(db.Model):
    __tablename__ = 'contas_a_receber'

    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos_aluguel.id'))
    receita_id = db.Column(db.Integer, db.ForeignKey(ReceitaCadastro.id), nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey('pessoas.id'), nullable=False)
    titulo = db.Column(db.String(255))
    data_vencimento = db.Column(db.Date, nullable=False)
    valor_previsto = db.Column(db.Numeric(10, 2), nullable=False)
    data_pagamento = db.Column(db.Date)
    valor_pago = db.Column(db.Numeric(10, 2))
    valor_pendente = db.Column(db.Numeric(10, 2), default=0)
    valor_desconto = db.Column(db.Numeric(10, 2), default=0)
    valor_multa = db.Column(db.Numeric(10, 2), default=0)
    valor_juros = db.Column(db.Numeric(10, 2), default=0)
    observacao = db.Column(db.Text)
    status_conta = db.Column(db.String(20), default='Aberta')
    origem_id = db.Column(db.Integer, db.ForeignKey('origens_cadastro.id'))
    nosso_numero = db.Column(db.String(20))
    data_cadastro = db.Column(db.DateTime, server_default=db.func.now())

    receita = db.relationship(
        ReceitaCadastro,
        primaryjoin=receita_id == ReceitaCadastro.id,
        backref=db.backref('contas', lazy=True),
        lazy=True,
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.valor_previsto is not None:
            pago = Decimal(self.valor_pago or 0)
            self.valor_pendente = Decimal(self.valor_previsto) - pago

    def marcar_pago(self, valor):
        valor_decimal = Decimal(str(valor))
        pago_atual = Decimal(self.valor_pago or 0)
        total_pago = pago_atual + valor_decimal
        self.valor_pago = total_pago
        self.data_pagamento = date.today()
        restante = Decimal(self.valor_previsto) - total_pago
        self.valor_pendente = restante if restante > 0 else Decimal('0')
        if restante <= 0:
            self.status_conta = 'Paga'
        else:
            self.status_conta = 'Parcial'