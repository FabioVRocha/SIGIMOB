from flask import Blueprint, request, jsonify
from datetime import date
from .models import db, ContaCaixa, ContaBanco, MovimentoFinanceiro
from .services import criar_movimento, importar_cnab, recalcular_posicoes

bp = Blueprint('caixa_banco_api', __name__)


@bp.get('/caixas')
def listar_caixas():
    contas = ContaCaixa.query.all()
    return jsonify([
        {
            'id': c.id,
            'nome': c.nome,
            'moeda': c.moeda,
            'saldo_atual': float(c.saldo_atual or 0),
            'data_saldo_inicial': c.data_saldo_inicial.isoformat() if c.data_saldo_inicial else None
        } for c in contas
    ])


@bp.post('/caixas')
def criar_caixa():
    data = request.get_json() or {}
    data_saldo_inicial = data.get('data_saldo_inicial')
    if data_saldo_inicial:
        data_saldo_inicial = date.fromisoformat(data_saldo_inicial)
    conta = ContaCaixa(
        nome=data.get('nome'),
        moeda=data.get('moeda', 'BRL'),
        saldo_inicial=data.get('saldo_inicial', 0),
        saldo_atual=data.get('saldo_inicial', 0),
        data_saldo_inicial=data_saldo_inicial
    )
    db.session.add(conta)
    db.session.commit()
    return jsonify({'id': conta.id}), 201


@bp.get('/bancos')
def listar_bancos():
    contas = ContaBanco.query.all()
    return jsonify([
        {
            'id': c.id,
            'banco': c.banco,
            'nome_banco': c.nome_banco,
            'agencia': c.agencia,
            'conta': c.conta,
            'tipo': c.tipo,
            'convenio': c.convenio,
            'carteira': c.carteira,
            'variacao': c.variacao,
            'contrato': c.contrato,
            'juros_mora': float(c.juros_mora or 0) if c.juros_mora is not None else None,
            'multa': float(c.multa or 0) if c.multa is not None else None,
            'dias_protesto': c.dias_protesto,
            'especie_documento': c.especie_documento,
            'saldo_atual': float(c.saldo_atual or 0),
            'data_saldo_inicial': c.data_saldo_inicial.isoformat() if c.data_saldo_inicial else None
        } for c in contas
    ])


@bp.post('/bancos')
def criar_banco():
    data = request.get_json() or {}
    data_saldo_inicial = data.get('data_saldo_inicial')
    if data_saldo_inicial:
        data_saldo_inicial = date.fromisoformat(data_saldo_inicial)
    conta = ContaBanco(
        banco=data.get('banco'),
        nome_banco=data.get('nome_banco'),
        agencia=data.get('agencia'),
        conta=data.get('conta'),
        tipo=data.get('tipo'),
        convenio=data.get('convenio'),
        carteira=data.get('carteira'),
        variacao=data.get('variacao'),
        contrato=data.get('contrato'),
        juros_mora=data.get('juros_mora'),
        multa=data.get('multa'),
        dias_protesto=data.get('dias_protesto'),
        especie_documento=data.get('especie_documento'),
        saldo_inicial=data.get('saldo_inicial', 0),
        saldo_atual=data.get('saldo_inicial', 0),
        data_saldo_inicial=data_saldo_inicial
    )
    db.session.add(conta)
    db.session.commit()
    return jsonify({'id': conta.id}), 201


@bp.get('/movimentos')
def listar_movimentos():
    query = MovimentoFinanceiro.query
    conta_id = request.args.get('conta_id')
    tipo = request.args.get('tipo')
    data_inicio = request.args.get('inicio')
    data_fim = request.args.get('fim')

    if conta_id:
        query = query.filter(MovimentoFinanceiro.conta_origem_id == conta_id)
    if tipo:
        query = query.filter(MovimentoFinanceiro.tipo == tipo)
    if data_inicio:
        query = query.filter(MovimentoFinanceiro.data_movimento >= data_inicio)
    if data_fim:
        query = query.filter(MovimentoFinanceiro.data_movimento <= data_fim)

    movimentos = query.order_by(MovimentoFinanceiro.data_movimento.desc()).all()
    return jsonify([
        {
            'id': m.id,
            'data_movimento': m.data_movimento.isoformat(),
            'tipo': m.tipo,
            'valor': float(m.valor),
            'categoria': m.categoria,
            'historico': m.historico,
            'conta_origem_id': m.conta_origem_id,
            'conta_origem_tipo': m.conta_origem_tipo,
            'conta_destino_id': m.conta_destino_id,
            'conta_destino_tipo': m.conta_destino_tipo
        } for m in movimentos
    ])


@bp.post('/movimentos')
def criar_movimento_endpoint():
    data = request.get_json() or {}
    movimento = criar_movimento(data)
    return jsonify({'id': movimento.id}), 201


@bp.post('/importar-cnab')
def importar_cnab_endpoint():
    conta_id = request.form.get('conta_id')
    conta_tipo = request.form.get('conta_tipo')  # 'caixa' ou 'banco'
    arquivo = request.files.get('arquivo')
    if not arquivo or not conta_id or not conta_tipo:
        return jsonify({'error': 'arquivo, conta_id e conta_tipo são obrigatórios'}), 400

    resultados = importar_cnab(arquivo, int(conta_id), conta_tipo)
    return jsonify(resultados), 201


@bp.post('/posicoes/recalcular')
def recalcular_posicoes_endpoint():
    data = request.get_json() or {}
    inicio = data.get('inicio')
    if inicio:
        inicio = date.fromisoformat(inicio)
    quantidade = recalcular_posicoes(inicio)
    return jsonify({'posicoes': quantidade}), 200