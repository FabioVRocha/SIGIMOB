from pathlib import Path

path = Path("app.py")
encoding = "utf-8"
try:
    text = path.read_text(encoding=encoding)
except UnicodeDecodeError:
    encoding = "latin-1"
    text = path.read_text(encoding=encoding)

old_assign = (
    '            observacao = request.form.get("observacao")\n'
    '            tipo = request.form["tipo"]\n'
    '            status = request.form["status"]\n'
)

new_assign = (
    '            observacao = request.form.get("observacao")\n'
    '            responsavel_nome = request.form.get("responsavel_nome")\n'
    '            responsavel_cpf = request.form.get("responsavel_cpf", "").strip()\n'
    '            if responsavel_cpf:\n'
    '                responsavel_cpf = re.sub(r"\\\D", "", responsavel_cpf)\n'
    '            else:\n'
    '                responsavel_cpf = None\n'
    '            responsavel_endereco = request.form.get("responsavel_endereco")\n'
    '            responsavel_bairro = request.form.get("responsavel_bairro")\n'
    '            responsavel_cidade = request.form.get("responsavel_cidade")\n'
    '            responsavel_estado = request.form.get("responsavel_estado")\n'
    '            responsavel_uf = request.form.get("responsavel_uf")\n'
    '            if responsavel_uf:\n'
    '                responsavel_uf = responsavel_uf.upper()\n'
    '            else:\n'
    '                responsavel_uf = None\n'
    '            responsavel_estado_civil = request.form.get("responsavel_estado_civil")\n'
    '            tipo = request.form["tipo"]\n'
    '            status = request.form["status"]\n'
)

if old_assign not in text:
    raise SystemExit("Expected assignment block not found")
text = text.replace(old_assign, new_assign)

old_insert = '''            cur.execute(
                """
                INSERT INTO pessoas (documento, razao_social_nome, nome_fantasia, endereco, bairro, cidade, estado, cep, telefone, contato, nacionalidade, estado_civil, profissao, rg, observacao, tipo, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                ,
                (
                    documento,
                    razao_social_nome,
                    nome_fantasia,
                    endereco,
                    bairro,
                    cidade,
                    estado,
                    cep,
                    telefone,
                    contato,
                    nacionalidade,
                    estado_civil,
                    profissao,
                    rg,
                    observacao,
                    tipo,
                    status,
                ),
            )
'''

new_insert = '''            cur.execute(
                """
                INSERT INTO pessoas (documento, razao_social_nome, nome_fantasia, endereco, bairro, cidade, estado, cep, telefone, contato, nacionalidade, estado_civil, profissao, rg, observacao, responsavel_nome, responsavel_cpf, responsavel_endereco, responsavel_bairro, responsavel_cidade, responsavel_estado, responsavel_uf, responsavel_estado_civil, tipo, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                ,
                (
                    documento,
                    razao_social_nome,
                    nome_fantasia,
                    endereco,
                    bairro,
                    cidade,
                    estado,
                    cep,
                    telefone,
                    contato,
                    nacionalidade,
                    estado_civil,
                    profissao,
                    rg,
                    observacao,
                    responsavel_nome,
                    responsavel_cpf,
                    responsavel_endereco,
                    responsavel_bairro,
                    responsavel_cidade,
                    responsavel_estado,
                    responsavel_uf,
                    responsavel_estado_civil,
                    tipo,
                    status,
                ),
            )
'''

if old_insert not in text:
    raise SystemExit("Expected insert block not found")
text = text.replace(old_insert, new_insert, 1)

old_update = '''            cur.execute(
                """
                UPDATE pessoas
                SET documento = %s, razao_social_nome = %s, nome_fantasia = %s, endereco = %s, bairro = %s, cidade = %s, estado = %s, cep = %s, telefone = %s, contato = %s, nacionalidade = %s, estado_civil = %s, profissao = %s, rg = %s, observacao = %s, tipo = %s, status = %s
                WHERE id = %s
                """
                ,
                (
                    documento,
                    razao_social_nome,
                    nome_fantasia,
                    endereco,
                    bairro,
                    cidade,
                    estado,
                    cep,
                    telefone,
                    contato,
                    nacionalidade,
                    estado_civil,
                    profissao,
                    rg,
                    observacao,
                    tipo,
                    status,
                    id,
                ),
            )
'''

new_update = '''            cur.execute(
                """
                UPDATE pessoas
                SET documento = %s, razao_social_nome = %s, nome_fantasia = %s, endereco = %s, bairro = %s, cidade = %s, estado = %s, cep = %s, telefone = %s, contato = %s, nacionalidade = %s, estado_civil = %s, profissao = %s, rg = %s, observacao = %s, responsavel_nome = %s, responsavel_cpf = %s, responsavel_endereco = %s, responsavel_bairro = %s, responsavel_cidade = %s, responsavel_estado = %s, responsavel_uf = %s, responsavel_estado_civil = %s, tipo = %s, status = %s
                WHERE id = %s
                """
                ,
                (
                    documento,
                    razao_social_nome,
                    nome_fantasia,
                    endereco,
                    bairro,
                    cidade,
                    estado,
                    cep,
                    telefone,
                    contato,
                    nacionalidade,
                    estado_civil,
                    profissao,
                    rg,
                    observacao,
                    responsavel_nome,
                    responsavel_cpf,
                    responsavel_endereco,
                    responsavel_bairro,
                    responsavel_cidade,
                    responsavel_estado,
                    responsavel_uf,
                    responsavel_estado_civil,
                    tipo,
                    status,
                    id,
                ),
            )
'''

if old_update not in text:
    raise SystemExit("Expected update block not found")
text = text.replace(old_update, new_update, 1)

path.write_text(text, encoding=encoding)
