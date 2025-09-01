from flask import Blueprint, request, jsonify, render_template
from caixa_banco import db
from caixa_banco.models import ContaBanco
from .models import ContaReceber, EmpresaLicenciada, Pessoa
from .services import gerar_boletos, importar_retorno

bp = Blueprint('contas_receber', __name__)


@bp.get('/contas-receber/<int:conta_id>/boleto')
def visualizar_boleto(conta_id):
    titulo = ContaReceber.query.get_or_404(conta_id)
    empresa = EmpresaLicenciada.query.first()
    conta = ContaBanco.query.first()
    cliente = Pessoa.query.get(titulo.cliente_id)
    if not all([empresa, conta, cliente]):
        return 'Dados incompletos para gerar o boleto', 400
    return render_template(
        'financeiro/contas_a_receber/boleto.html',
        titulo=titulo,
        empresa=empresa,
        conta=conta,
        cliente=cliente,
    )


@bp.post('/contas-receber/<int:conta_id>/boleto')
def gerar_boleto(conta_id):
    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or [conta_id]
    try:
        resultado = gerar_boletos(ids)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify(resultado)


@bp.post('/contas-receber/retorno')
def importar_retorno_endpoint():
    arquivo = request.files.get('arquivo')
    if not arquivo:
        return jsonify({'error': 'arquivo obrigatório'}), 400
    conteudo = arquivo.read().decode('utf-8')
    resultado = importar_retorno(conteudo)
    return jsonify(resultado)


@bp.post('/contas-receber/<int:conta_id>/pagamento')
def registrar_pagamento(conta_id):
    data = request.get_json(silent=True) or {}
    valor = data.get('valor')
    if valor is None:
        return jsonify({'error': 'valor obrigatório'}), 400
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        return jsonify({'error': 'valor inválido'}), 400
    conta = ContaReceber.query.get_or_404(conta_id)
    conta.marcar_pago(valor)
    db.session.commit()
    return jsonify({
        'id': conta.id,
        'status': conta.status_conta,
        'valor_pago': float(conta.valor_pago or 0),
        'valor_pendente': float(conta.valor_pendente or 0),
    })