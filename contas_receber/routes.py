from flask import Blueprint, request, jsonify
from .services import gerar_boletos, importar_retorno

bp = Blueprint('contas_receber', __name__)


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