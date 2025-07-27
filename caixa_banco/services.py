from datetime import datetime
from io import StringIO
from .models import db, ContaCaixa, ContaBanco, MovimentoFinanceiro, Conciliacao


def _get_conta(tipo, conta_id):
    if tipo == 'caixa':
        return ContaCaixa.query.get(conta_id)
    return ContaBanco.query.get(conta_id)


def atualizar_saldo(tipo, conta_id, valor):
    conta = _get_conta(tipo, conta_id)
    if conta:
        conta.saldo_atual = (conta.saldo_atual or 0) + valor
        db.session.commit()


def criar_movimento(data):
    movimento = MovimentoFinanceiro(**data)
    db.session.add(movimento)
    db.session.flush()  # garante id para conciliacoes

    valor = movimento.valor
    if movimento.tipo == 'entrada':
        atualizar_saldo(movimento.conta_origem_tipo, movimento.conta_origem_id, valor)
    elif movimento.tipo == 'saida':
        atualizar_saldo(movimento.conta_origem_tipo, movimento.conta_origem_id, -valor)
    elif movimento.tipo == 'transferencia':
        atualizar_saldo(movimento.conta_origem_tipo, movimento.conta_origem_id, -valor)
        if movimento.conta_destino_id:
            atualizar_saldo(movimento.conta_destino_tipo, movimento.conta_destino_id, valor)

    db.session.commit()
    return movimento


def atualizar_movimento(movimento, data):
    """Atualiza um movimento existente ajustando saldos."""
    # Reverte efeito anterior
    valor_antigo = movimento.valor
    if movimento.tipo == 'entrada':
        atualizar_saldo(movimento.conta_origem_tipo, movimento.conta_origem_id, -valor_antigo)
    elif movimento.tipo == 'saida':
        atualizar_saldo(movimento.conta_origem_tipo, movimento.conta_origem_id, valor_antigo)
    elif movimento.tipo == 'transferencia':
        atualizar_saldo(movimento.conta_origem_tipo, movimento.conta_origem_id, valor_antigo)
        if movimento.conta_destino_id:
            atualizar_saldo(movimento.conta_destino_tipo, movimento.conta_destino_id, -valor_antigo)

    for key, value in data.items():
        setattr(movimento, key, value)
    db.session.flush()

    valor_novo = movimento.valor
    if movimento.tipo == 'entrada':
        atualizar_saldo(movimento.conta_origem_tipo, movimento.conta_origem_id, valor_novo)
    elif movimento.tipo == 'saida':
        atualizar_saldo(movimento.conta_origem_tipo, movimento.conta_origem_id, -valor_novo)
    elif movimento.tipo == 'transferencia':
        atualizar_saldo(movimento.conta_origem_tipo, movimento.conta_origem_id, -valor_novo)
        if movimento.conta_destino_id:
            atualizar_saldo(movimento.conta_destino_tipo, movimento.conta_destino_id, valor_novo)

    db.session.commit()
    return movimento


def deletar_movimento(movimento):
    """Exclui um movimento ajustando os saldos."""
    valor = movimento.valor
    if movimento.tipo == 'entrada':
        atualizar_saldo(movimento.conta_origem_tipo, movimento.conta_origem_id, -valor)
    elif movimento.tipo == 'saida':
        atualizar_saldo(movimento.conta_origem_tipo, movimento.conta_origem_id, valor)
    elif movimento.tipo == 'transferencia':
        atualizar_saldo(movimento.conta_origem_tipo, movimento.conta_origem_id, valor)
        if movimento.conta_destino_id:
            atualizar_saldo(movimento.conta_destino_tipo, movimento.conta_destino_id, -valor)
    db.session.delete(movimento)
    db.session.commit()


def parse_cnab240(content):
    """Parse simplificado de CNAB240. Retorna lista de dicts com data e valor."""
    registros = []
    for line in StringIO(content).read().splitlines():
        if len(line) < 160:
            continue
        try:
            data = datetime.strptime(line[143:151], '%Y%m%d').date()
            valor = int(line[152:167]) / 100.0
            registros.append({'data_movimento': data, 'valor': valor, 'historico': line[70:90].strip()})
        except Exception:
            continue
    return registros


def importar_cnab(file_storage, conta_id, conta_tipo):
    content = file_storage.read().decode('utf-8', errors='ignore')
    registros = parse_cnab240(content)
    resultados = []
    for r in registros:
        existente = MovimentoFinanceiro.query.filter_by(
            data_movimento=r['data_movimento'], valor=r['valor']
        ).first()
        if existente:
            conciliacao = Conciliacao(movimento=existente, arquivo_lancamento=file_storage.filename, status='conciliado', data_conciliacao=datetime.utcnow())
            db.session.add(conciliacao)
            resultados.append({'movimento_id': existente.id, 'status': 'conciliado'})
        else:
            dados = {
                'conta_origem_id': conta_id,
                'conta_origem_tipo': conta_tipo,
                'data_movimento': r['data_movimento'],
                'tipo': 'entrada',
                'valor': r['valor'],
                'categoria': 'CNAB',
                'historico': r.get('historico')
            }
            movimento = criar_movimento(dados)
            conciliacao = Conciliacao(movimento=movimento, arquivo_lancamento=file_storage.filename, status='conciliado', data_conciliacao=datetime.utcnow())
            db.session.add(conciliacao)
            resultados.append({'movimento_id': movimento.id, 'status': 'conciliado'})
    db.session.commit()
    return resultados