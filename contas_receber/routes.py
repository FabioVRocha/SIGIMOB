import os
from flask import Blueprint, request, jsonify, render_template, url_for, current_app
from sqlalchemy import bindparam, text
from caixa_banco import db
from .models import ContaReceber, EmpresaLicenciada, Pessoa
from .services import gerar_boletos, importar_retorno
from .pdf import render_boleto_html

bp = Blueprint('contas_receber', __name__)


def _parse_ids(raw):
    if raw is None:
        return []
    if isinstance(raw, (int, float)):
        return [int(raw)]
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        if raw.startswith('[') and raw.endswith(']'):
            raw = raw[1:-1]
        items = raw.split(',')
    elif isinstance(raw, (list, tuple, set)):
        items = raw
    else:
        raise ValueError('Formato de ids invalido')
    ids = []
    for item in items:
        texto = str(item).strip()
        if not texto:
            continue
        ids.append(int(texto))
    return ids


def _path_to_url(path):
    if not path:
        return None
    base = current_app.config.get('UPLOAD_FOLDER')
    if base:
        base = os.path.abspath(base)
        try:
            rel = os.path.relpath(path, base)
        except ValueError:
            rel = None
        else:
            if rel and not rel.startswith('..'):
                return url_for('uploaded_file', filename=rel.replace('\\', '/'))
    normalized = str(path).replace('\\', '/')
    if '/uploads/' in normalized:
        return normalized[normalized.index('/uploads/'):]
    return normalized


def _append_download_links(payload):
    pdfs = payload.get('pdfs') or []
    remessa = payload.get('remessa')
    return {
        **payload,
        'pdf_urls': [url for url in (_path_to_url(p) for p in pdfs) if url],
        'remessa_url': _path_to_url(remessa) if remessa else None,
    }


def _format_contrato_label(row):
    partes = [f"#{row['id']}"]
    nome = row.get('nome_inquilino') or ''
    if nome:
        partes.append(nome)
    inicio = row.get('data_inicio')
    fim = row.get('data_fim')
    if inicio and fim:
        partes.append(f"{inicio:%d/%m/%Y} - {fim:%d/%m/%Y}")
    status = row.get('status_contrato')
    if status:
        partes.append(status)
    return ' - '.join(partes)


@bp.get('/contas-receber/clientes/<int:cliente_id>/contratos')
def listar_contratos_cliente(cliente_id):
    stmt = text(
        """
        SELECT id, nome_inquilino, data_inicio, data_fim, status_contrato
        FROM contratos_aluguel
        WHERE cliente_id = :cliente_id
        ORDER BY data_inicio DESC
        """
    )
    resultado = db.session.execute(stmt, {'cliente_id': cliente_id}).mappings()
    contratos = [
        {
            'id': row['id'],
            'descricao': _format_contrato_label(row),
            'status': row.get('status_contrato'),
        }
        for row in resultado
    ]
    return jsonify({'contratos': contratos})


@bp.get('/contas-receber/titulos')
def listar_titulos():
    cliente_id = request.args.get('cliente_id', type=int)
    contrato_id = request.args.get('contrato_id', type=int)
    if not cliente_id:
        return jsonify({'error': 'cliente_id obrigatorio'}), 400

    query = ContaReceber.query.filter(ContaReceber.cliente_id == cliente_id)
    if contrato_id:
        query = query.filter(ContaReceber.contrato_id == contrato_id)

    status_param = request.args.get('status') or 'Aberta,Vencida,Parcial'
    status_list = [s.strip() for s in status_param.split(',') if s.strip()]
    if status_list:
        query = query.filter(ContaReceber.status_conta.in_(status_list))

    titulos = (
        query.order_by(ContaReceber.data_vencimento.asc(), ContaReceber.id.asc()).all()
    )

    cliente = Pessoa.query.get(cliente_id)
    contrato_ids = {t.contrato_id for t in titulos if t.contrato_id}
    contratos_info = {}
    if contrato_ids:
        stmt = text(
            "SELECT id, nome_inquilino FROM contratos_aluguel WHERE id IN :ids"
        ).bindparams(bindparam('ids', expanding=True))
        rows = db.session.execute(stmt, {'ids': list(contrato_ids)}).mappings()
        contratos_info = {row['id']: row.get('nome_inquilino') for row in rows}

    titulos_json = []
    for titulo in titulos:
        titulos_json.append(
            {
                'id': titulo.id,
                'titulo': titulo.titulo or f"{titulo.id:06d}",
                'data_vencimento': titulo.data_vencimento.isoformat()
                if titulo.data_vencimento
                else None,
                'valor_previsto': float(titulo.valor_previsto or 0),
                'valor_pendente': float(titulo.valor_pendente or 0),
                'status_conta': titulo.status_conta,
                'contrato_id': titulo.contrato_id,
                'contrato_label': contratos_info.get(titulo.contrato_id),
                'nosso_numero': titulo.nosso_numero,
            }
        )

    return jsonify(
        {
            'titulos': titulos_json,
            'cliente': {
                'id': cliente.id if cliente else cliente_id,
                'nome': cliente.razao_social_nome if cliente else None,
            },
        }
    )


@bp.get('/contas-receber/boleto/lote')
def visualizar_boletos_lote():
    ids_param = request.args.get('ids')
    try:
        ids = _parse_ids(ids_param)
    except ValueError:
        return 'Parametros de titulos invalidos.', 400
    if not ids:
        return 'Informe ao menos um titulo para visualizar.', 400

    titulos = (
        ContaReceber.query.filter(ContaReceber.id.in_(ids))
        .order_by(ContaReceber.data_vencimento.asc(), ContaReceber.id.asc())
        .all()
    )
    if not titulos:
        return 'Nenhum titulo encontrado para os parametros informados.', 404

    cliente_ids = {t.cliente_id for t in titulos}
    clientes = {}
    if cliente_ids:
        clientes = {
            pessoa.id: pessoa
            for pessoa in Pessoa.query.filter(Pessoa.id.in_(cliente_ids)).all()
        }

    contrato_ids = {t.contrato_id for t in titulos if t.contrato_id}
    contratos_info = {}
    if contrato_ids:
        stmt = text(
            "SELECT id, nome_inquilino FROM contratos_aluguel WHERE id IN :ids"
        ).bindparams(bindparam('ids', expanding=True))
        rows = db.session.execute(stmt, {'ids': list(contrato_ids)}).mappings()
        contratos_info = {
            row['id']: row.get('nome_inquilino') or f"Contrato {row['id']}"
            for row in rows
        }

    cliente_labels = []
    if clientes:
        for cid in sorted(cliente_ids):
            pessoa = clientes.get(cid)
            nome = getattr(pessoa, 'razao_social_nome', None) or f"Cliente {cid}"
            cliente_labels.append(nome)

    contrato_labels = []
    if contratos_info:
        for cid in sorted(contrato_ids):
            contrato_labels.append(contratos_info.get(cid) or f"Contrato {cid}")

    titulos_data = []
    for titulo in titulos:
        pessoa = clientes.get(titulo.cliente_id) if clientes else None
        cliente_nome = getattr(pessoa, 'razao_social_nome', None) if pessoa else None
        titulos_data.append(
            {
                'id': titulo.id,
                'label': titulo.titulo or f"{titulo.id:06d}",
                'cliente_nome': cliente_nome,
                'contrato_label': contratos_info.get(titulo.contrato_id),
                'valor_previsto': float(titulo.valor_previsto or 0),
                'data_vencimento': titulo.data_vencimento.isoformat() if titulo.data_vencimento else None,
                'status': titulo.status_conta,
            }
        )

    return render_template(
        'financeiro/contas_a_receber/boleto_lote.html',
        titulos=titulos,
        clientes=clientes,
        contratos=contratos_info,
        ids=ids,
        ids_param=','.join(str(i) for i in ids),
        cliente_labels=cliente_labels,
        contrato_labels=contrato_labels,
        titulos_data=titulos_data,
    )


@bp.get('/contas-receber/<int:conta_id>/boleto')
def visualizar_boleto(conta_id):
    titulo = ContaReceber.query.get_or_404(conta_id)
    try:
        return render_boleto_html(titulo)
    except ValueError as exc:
        return str(exc), 400


@bp.post('/contas-receber/<int:conta_id>/boleto')
def gerar_boleto(conta_id):
    data = request.get_json(silent=True) or {}
    try:
        ids = _parse_ids(data.get('ids'))
    except ValueError:
        return jsonify({'error': 'ids invalidos'}), 400
    if not ids:
        ids = [conta_id]
    try:
        resultado = gerar_boletos(ids)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify(_append_download_links(resultado))


@bp.post('/contas-receber/boleto/lote')
def gerar_boletos_lote():
    data = request.get_json(silent=True) or {}
    try:
        ids = _parse_ids(data.get('ids'))
    except ValueError:
        return jsonify({'error': 'ids invalidos'}), 400
    if not ids:
        return jsonify({'error': 'Informe ao menos um titulo'}), 400
    try:
        resultado = gerar_boletos(ids)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify(_append_download_links(resultado))


@bp.post('/contas-receber/retorno')
def importar_retorno_endpoint():
    arquivo = request.files.get('arquivo')
    if not arquivo:
        return jsonify({'error': 'arquivo obrigatorio'}), 400
    conteudo = arquivo.read().decode('utf-8')
    resultado = importar_retorno(conteudo)
    return jsonify(resultado)


@bp.post('/contas-receber/<int:conta_id>/pagamento')
def registrar_pagamento(conta_id):
    data = request.get_json(silent=True) or {}
    valor = data.get('valor')
    if valor is None:
        return jsonify({'error': 'valor obrigatorio'}), 400
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        return jsonify({'error': 'valor invalido'}), 400
    conta = ContaReceber.query.get_or_404(conta_id)
    conta.marcar_pago(valor)
    db.session.commit()
    return jsonify(
        {
            'id': conta.id,
            'status': conta.status_conta,
            'valor_pago': float(conta.valor_pago or 0),
            'valor_pendente': float(conta.valor_pendente or 0),
        }
    )
