from datetime import datetime
from . import db


class BaseModel(db.Model):
    __abstract__ = True
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Person(BaseModel):
    __tablename__ = 'persons'

    cpf_cnpj = db.Column(db.String(20), unique=True, nullable=False)
    razao_social = db.Column(db.String(100), nullable=False)
    nome_fantasia = db.Column(db.String(100))
    endereco = db.Column(db.String(200))
    bairro = db.Column(db.String(100))
    cidade = db.Column(db.String(100))
    estado = db.Column(db.String(2))
    cep = db.Column(db.String(10))
    telefone = db.Column(db.String(20))
    observacao = db.Column(db.Text)
    tipo = db.Column(db.String(20))  # fornecedor ou cliente
    status = db.Column(db.String(10), default='ativo')


class Imovel(BaseModel):
    __tablename__ = 'imoveis'

    tipo_imovel = db.Column(db.String(50))
    endereco = db.Column(db.String(200))
    registro = db.Column(db.String(100))
    livro = db.Column(db.String(50))
    folha = db.Column(db.String(50))
    matricula = db.Column(db.String(50))
    inscricao_iptu = db.Column(db.String(50))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    data_aquisicao = db.Column(db.Date)
    valor_imovel = db.Column(db.Numeric(14, 2))
    valor_aluguel = db.Column(db.Numeric(14, 2))
    destinacao = db.Column(db.String(200))
    observacao = db.Column(db.Text)


class MovimentoImovel(BaseModel):
    __tablename__ = 'movimentos_imovel'

    imovel_id = db.Column(db.Integer, db.ForeignKey('imoveis.id'))
    tipo = db.Column(db.String(20))
    data = db.Column(db.Date)
    valor = db.Column(db.Numeric(14, 2))
    observacao = db.Column(db.Text)
    imovel = db.relationship('Imovel')


class ContratoAluguel(BaseModel):
    __tablename__ = 'contratos_aluguel'

    imovel_id = db.Column(db.Integer, db.ForeignKey('imoveis.id'))
    cliente_id = db.Column(db.Integer, db.ForeignKey('persons.id'))
    inicio = db.Column(db.Date)
    fim = db.Column(db.Date)
    parcelas = db.Column(db.Integer)
    valor_parcela = db.Column(db.Numeric(14, 2))
    status = db.Column(db.String(20))
    imovel = db.relationship('Imovel')
    cliente = db.relationship('Person')


class ReajusteContrato(BaseModel):
    __tablename__ = 'reajustes_contrato'

    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos_aluguel.id'))
    data = db.Column(db.Date)
    percentual = db.Column(db.Float)
    contrato = db.relationship('ContratoAluguel')


class ContaReceber(BaseModel):
    __tablename__ = 'contas_receber'

    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos_aluguel.id'))
    cliente = db.Column(db.String(100))
    parcela = db.Column(db.Integer)
    vencimento = db.Column(db.Date)
    valor_parcela = db.Column(db.Numeric(14, 2))
    data_pagamento = db.Column(db.Date)
    valor_pago = db.Column(db.Numeric(14, 2))
    desconto = db.Column(db.Numeric(14, 2))
    multa = db.Column(db.Numeric(14, 2))
    juros = db.Column(db.Numeric(14, 2))
    observacao = db.Column(db.Text)
    origem = db.Column(db.String(100))
    contrato = db.relationship('ContratoAluguel')


class ContaPagar(BaseModel):
    __tablename__ = 'contas_pagar'

    codigo = db.Column(db.String(50))
    fornecedor = db.Column(db.String(100))
    vencimento = db.Column(db.Date)
    valor_parcela = db.Column(db.Numeric(14, 2))
    data_pagamento = db.Column(db.Date)
    valor_pago = db.Column(db.Numeric(14, 2))
    desconto = db.Column(db.Numeric(14, 2))
    multa = db.Column(db.Numeric(14, 2))
    juros = db.Column(db.Numeric(14, 2))
    observacao = db.Column(db.Text)
    centro_custo = db.Column(db.String(100))
    origem = db.Column(db.String(100))


class Usuario(BaseModel):
    __tablename__ = 'usuarios'

    nome = db.Column(db.String(100))
    senha_hash = db.Column(db.String(128))
    role = db.Column(db.String(20))  # Master ou Operador


class Empresa(BaseModel):
    __tablename__ = 'empresas'

    cpf_cnpj = db.Column(db.String(20))
    razao_social = db.Column(db.String(100))
    nome_fantasia = db.Column(db.String(100))
    endereco = db.Column(db.String(200))
    telefone = db.Column(db.String(20))
    status = db.Column(db.String(10))