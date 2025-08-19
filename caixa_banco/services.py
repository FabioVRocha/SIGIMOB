from datetime import datetime, date, timedelta
from decimal import Decimal
from io import StringIO
from sqlalchemy import text
from .models import db, ContaCaixa, ContaBanco, MovimentoFinanceiro, Conciliacao, PosicaoDiaria


def _get_conta(tipo, conta_id):
    if tipo == 'caixa':
        return ContaCaixa.query.get(conta_id)
    return ContaBanco.query.get(conta_id)


def atualizar_saldo(tipo, conta_id, valor):
    conta = _get_conta(tipo, conta_id)
    if conta:
        conta.saldo_atual = (conta.saldo_atual or Decimal('0')) + Decimal(valor)
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
    # Recalcula posições a partir da data do movimento
    recalcular_posicoes(movimento.data_movimento)
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
    # Recalcula posições a partir da menor data envolvida
    data_ref = min(movimento.data_movimento, data.get('data_movimento', movimento.data_movimento))
    recalcular_posicoes(data_ref)
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
    # Se o movimento estiver vinculado a uma conta a receber, desfaz o pagamento
    if movimento.documento and movimento.documento.startswith('CR-'):
        try:
            conta_id = int(movimento.documento.split('CR-')[1])
        except ValueError:
            conta_id = None
        if conta_id:
            db.session.execute(
                text(
                    """
                    UPDATE contas_a_receber
                       SET data_pagamento = NULL,
                           valor_pago = NULL,
                           valor_desconto = 0,
                           valor_multa = 0,
                           valor_juros = 0,
                           valor_pendente = valor_previsto,
                           status_conta = 'Aberta'
                     WHERE id = :conta_id
                    """
                ),
                {"conta_id": conta_id},
            )
    # Se o movimento estiver vinculado a uma conta a pagar, desfaz o pagamento
    if movimento.documento and movimento.documento.startswith('CP-'):
        try:
            conta_id = int(movimento.documento.split('CP-')[1])
        except ValueError:
            conta_id = None
        if conta_id:
            db.session.execute(
                text(
                    """
                    UPDATE contas_a_pagar
                       SET data_pagamento = NULL,
                           valor_pago = NULL,
                           valor_desconto = 0,
                           valor_multa = 0,
                           valor_juros = 0,
                           status_conta = 'Aberta'
                     WHERE id = :conta_id
                    """
                ),
                {"conta_id": conta_id},
            )
    data_ref = movimento.data_movimento
    db.session.delete(movimento)
    db.session.commit()
    # Recalcula posições após exclusão
    recalcular_posicoes(data_ref)


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


def recalcular_posicoes(data_inicio=None):
    """Recalcula as posições diárias a partir de uma data."""
    if data_inicio is None:
        data_inicio = date.today()
    data_fim = date.today()

    contas = [("caixa", c) for c in ContaCaixa.query.all()] + [
        ("banco", b) for b in ContaBanco.query.all()
    ]

    total = 0
    for tipo, conta in contas:
        base = conta.data_saldo_inicial or data_inicio
        inicio = min(data_inicio, base)
        # Remove posições existentes a partir da data de início
        PosicaoDiaria.query.filter_by(conta_id=conta.id, conta_tipo=tipo).filter(PosicaoDiaria.data >= inicio).delete()
        db.session.flush()

        # Busca última posição antes do início para obter saldo inicial
        pos_anterior = (
            PosicaoDiaria.query.filter_by(conta_id=conta.id, conta_tipo=tipo)
            .filter(PosicaoDiaria.data < inicio)
            .order_by(PosicaoDiaria.data.desc())
            .first()
        )
        if pos_anterior:
            saldo = float(pos_anterior.saldo)
            current = pos_anterior.data + timedelta(days=1)
        else:
            saldo = float(conta.saldo_inicial or 0)
            current = base

        if current < inicio:
            current = inicio

        while current <= data_fim:
            # Movimentos na origem
            movs_origem = MovimentoFinanceiro.query.filter_by(
                conta_origem_id=conta.id,
                conta_origem_tipo=tipo,
                data_movimento=current,
            ).all()
            for m in movs_origem:
                if m.tipo == "entrada":
                    saldo += float(m.valor)
                elif m.tipo == "saida":
                    saldo -= float(m.valor)
                elif m.tipo == "transferencia":
                    saldo -= float(m.valor)

            # Movimentos na conta destino (transferências)
            movs_destino = MovimentoFinanceiro.query.filter_by(
                conta_destino_id=conta.id,
                conta_destino_tipo=tipo,
                data_movimento=current,
            ).all()
            for m in movs_destino:
                if m.tipo == "transferencia":
                    saldo += float(m.valor)

            db.session.add(
                PosicaoDiaria(
                    conta_id=conta.id,
                    conta_tipo=tipo,
                    data=current,
                    saldo=saldo,
                )
            )
            total += 1
            current += timedelta(days=1)

    db.session.commit()
    return total