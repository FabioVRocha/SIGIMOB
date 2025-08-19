from datetime import datetime, date
from . import db


class ContaCaixa(db.Model):
    __tablename__ = 'conta_caixa'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    moeda = db.Column(db.String(10), default='BRL')
    saldo_inicial = db.Column(db.Numeric(12, 2), default=0)
    saldo_atual = db.Column(db.Numeric(12, 2), default=0)
    data_saldo_inicial = db.Column(db.Date, default=date.today)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.saldo_atual is None:
            self.saldo_atual = self.saldo_inicial or 0


class ContaBanco(db.Model):
    __tablename__ = 'conta_banco'

    id = db.Column(db.Integer, primary_key=True)
    banco = db.Column(db.String(10), nullable=False)  # código do banco
    nome_banco = db.Column(db.String(100))
    agencia = db.Column(db.String(50), nullable=False)
    conta = db.Column(db.String(50), nullable=False)
    tipo = db.Column(db.String(20))
    convenio = db.Column(db.String(50))
    carteira = db.Column(db.String(50))
    variacao = db.Column(db.String(50))
    contrato = db.Column(db.String(50))
    juros_mora = db.Column(db.Numeric(5, 2))
    multa = db.Column(db.Numeric(5, 2))
    dias_protesto = db.Column(db.Integer)
    especie_documento = db.Column(db.String(50))
    saldo_inicial = db.Column(db.Numeric(12, 2), default=0)
    saldo_atual = db.Column(db.Numeric(12, 2), default=0)
    data_saldo_inicial = db.Column(db.Date, default=date.today)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.saldo_atual is None:
            self.saldo_atual = self.saldo_inicial or 0


class MovimentoFinanceiro(db.Model):
    __tablename__ = 'movimento_financeiro'

    id = db.Column(db.Integer, primary_key=True)
    conta_origem_id = db.Column(db.Integer, nullable=False)
    conta_origem_tipo = db.Column(db.String(10), nullable=False)  # 'caixa' ou 'banco'
    conta_destino_id = db.Column(db.Integer)
    conta_destino_tipo = db.Column(db.String(10))
    data_movimento = db.Column(db.Date, default=date.today, nullable=False)
    tipo = db.Column(db.Enum('entrada', 'saida', 'transferencia', name='tipo_movimento'), nullable=False)
    valor = db.Column(db.Numeric(12, 2), nullable=False)
    valor_previsto = db.Column(db.Numeric(12, 2))
    valor_pago = db.Column(db.Numeric(12, 2))
    valor_desconto = db.Column(db.Numeric(12, 2))
    valor_multa = db.Column(db.Numeric(12, 2))
    valor_juros = db.Column(db.Numeric(12, 2))
    categoria = db.Column(db.String(100))
    historico = db.Column(db.Text)
    documento = db.Column(db.String(100))
    despesa_id = db.Column(db.Integer)
    receita_id = db.Column(db.Integer)


class Conciliacao(db.Model):
    __tablename__ = 'conciliacao'

    id = db.Column(db.Integer, primary_key=True)
    movimento_id = db.Column(db.Integer, db.ForeignKey('movimento_financeiro.id'), nullable=False)
    arquivo_lancamento = db.Column(db.String(255))
    status = db.Column(db.Enum('pendente', 'conciliado', 'rejeitado', name='status_conciliacao'), default='pendente', nullable=False)
    data_conciliacao = db.Column(db.DateTime)

    movimento = db.relationship('MovimentoFinanceiro', backref=db.backref('conciliacoes', lazy=True))


class PosicaoDiaria(db.Model):
    """Representa o fechamento diário de cada conta de caixa ou banco."""

    __tablename__ = 'posicao_diaria'

    id = db.Column(db.Integer, primary_key=True)
    conta_id = db.Column(db.Integer, nullable=False)
    conta_tipo = db.Column(db.String(10), nullable=False)  # 'caixa' ou 'banco'
    data = db.Column(db.Date, nullable=False)
    saldo = db.Column(db.Numeric(12, 2), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('conta_id', 'conta_tipo', 'data', name='uq_posicao_conta_data'),
    )