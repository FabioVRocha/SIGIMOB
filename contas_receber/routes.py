from flask import Blueprint, request, jsonify, render_template
from caixa_banco import db
from caixa_banco.models import ContaBanco
from .models import ContaReceber, EmpresaLicenciada, Pessoa
from .services import gerar_boletos, importar_retorno
import re


def _num(x: str) -> str:
    """Extrai apenas dígitos de uma string."""
    return re.sub(r"\D", "", x or "")


def _barcode_html(numero: str) -> str:
    """Gera um código de barras Interleaved 2 of 5 em HTML.

    A implementação a seguir converte a ``numero`` (string numérica) no
    padrão *Interleaved 2 of 5*, gerando uma sequência de ``<span>`` que
    alternam barras pretas e espaços em branco com larguras finas (``n``)
    e largas (``w``). Esse formato é compatível com leitores de código de
    barras utilizados em boletos bancários.

    O algoritmo baseia‑se nos pares de dígitos: cada par é transformado
    em cinco barras e cinco espaços intercalados, conforme a tabela do
    padrão ITF. Começa‑se com o padrão de guarda ``nnnn`` e termina com
    ``wnn``. Também são acrescentadas as *quiet zones* (10 módulos em
    branco) no início e no fim, essenciais para que leitores óticos
    consigam detectar o código corretamente.
    """

    # Tabela de padrões (fino = n, largo = w)
    padroes = {
        "0": "nnwwn",
        "1": "wnnnw",
        "2": "nwnnw",
        "3": "wwnnn",
        "4": "nnwnw",
        "5": "wnwnn",
        "6": "nwwnn",
        "7": "nnnww",
        "8": "wnnwn",
        "9": "nwnwn",
    }

    # O ITF exige quantidade par de dígitos; caso contrário prefixamos 0
    numero = _num(numero)
    if len(numero) % 2:
        numero = "0" + numero

    def span_bar(largura: str, espaco: bool = False) -> str:
        classe = largura
        if espaco:
            classe += " s"
        return f"<span class='{classe}'></span>"

    partes = []
    # Área de silêncio inicial (10 módulos)
    for _ in range(10):
        partes.append(span_bar("n", espaco=True))

    # Padrão inicial: barra e espaço finos alternados
    for i, ch in enumerate("nnnn"):
        partes.append(span_bar(ch, espaco=bool(i % 2)))

    # Converte cada par de dígitos
    for i in range(0, len(numero), 2):
        barras = padroes[numero[i]]
        espacos = padroes[numero[i + 1]]
        for b, e in zip(barras, espacos):
            partes.append(span_bar(b))
            partes.append(span_bar(e, espaco=True))

    # Padrão final
    for i, ch in enumerate("wnn"):
        partes.append(span_bar(ch, espaco=bool(i % 2)))

    # Área de silêncio final (10 módulos)
    for _ in range(10):
        partes.append(span_bar("n", espaco=True))

    return "".join(partes)

bp = Blueprint('contas_receber', __name__)


@bp.get('/contas-receber/<int:conta_id>/boleto')
def visualizar_boleto(conta_id):
    titulo = ContaReceber.query.get_or_404(conta_id)
    empresa = EmpresaLicenciada.query.first()
    conta = ContaBanco.query.first()
    cliente = Pessoa.query.get(titulo.cliente_id)
    if not all([empresa, conta, cliente]):
        return 'Dados incompletos para gerar o boleto', 400
    valor_str = _num(str(titulo.valor_previsto))
    barcode_num = (_num(conta.banco) + _num(titulo.nosso_numero or str(titulo.id)) + valor_str)[:44].ljust(44, "0")
    barcode = _barcode_html(barcode_num)
    return render_template(
        'financeiro/contas_a_receber/boleto.html',
        titulo=titulo,
        empresa=empresa,
        conta=conta,
        cliente=cliente,
        barcode=barcode,
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