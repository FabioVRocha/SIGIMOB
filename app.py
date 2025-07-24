# app.py
# Este é o arquivo principal da sua aplicação Flask.

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_from_directory,
    jsonify,
)
import psycopg2
from psycopg2 import extras
import os
import posixpath
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import subprocess
import json
from werkzeug.utils import secure_filename  # Para lidar com nomes de arquivos de upload

# Importa a configuração do banco de dados e outras variáveis
from config import DATABASE_URL, SECRET_KEY, UPLOAD_FOLDER, ALLOWED_EXTENSIONS
from caixa_banco import init_app as init_caixa_banco, db
from caixa_banco.models import ContaCaixa, ContaBanco, Conciliacao
from caixa_banco.services import criar_movimento, importar_cnab
from sqlalchemy import func

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Cria as pastas de uploads se elas não existirem
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Pastas de uploads utilizadas pelos módulos
os.makedirs(os.path.join(UPLOAD_FOLDER, "backups"), exist_ok=True)
os.makedirs(
    os.path.join(UPLOAD_FOLDER, "imoveis_anexos"), exist_ok=True
)  # Pasta para anexos de imóveis
os.makedirs(
    os.path.join(UPLOAD_FOLDER, "contratos_anexos"), exist_ok=True
)  # Pasta para anexos de contratos

# Inicializa o módulo de Caixa e Banco (SQLAlchemy e rotas REST)
init_caixa_banco(app)


# Variáveis globais para o sistema (exemplo)
SYSTEM_VERSION = "1.0"

# Módulos disponíveis no sistema para configuração de permissões
MODULES = [
    "Cadastro Fornecedores/Clientes",
    "Cadastro Imoveis",
    "Cadastro Despesas",
    "Cadastro Origens",
    "Cadastro Receitas",
    "Gestao Contratos",
    "Financeiro",
    "Administracao Sistema",
]

# Ações possíveis
ACTIONS = ["Incluir", "Editar", "Consultar", "Excluir", "Bloquear"]


# Função para conectar ao banco de dados
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn


# Função auxiliar para verificar extensões de arquivo permitidas
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    """Serve arquivos enviados pelo usuário."""
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# Decorador para verificar se o usuário está logado
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Você precisa estar logado para acessar esta página.", "info")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


@app.route("/imoveis/fotos/<int:imovel_id>")
@login_required
def imoveis_fotos(imovel_id):
    """Retorna as URLs das fotos de um imóvel em formato JSON."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(
        "SELECT nome_arquivo FROM imovel_anexos WHERE imovel_id = %s AND tipo_anexo = 'foto'",
        (imovel_id,),
    )
    fotos = [
        url_for(
            "uploaded_file",
            filename=posixpath.join("imoveis_anexos", row["nome_arquivo"]),
        )
        for row in cur.fetchall()
    ]
    cur.close()
    conn.close()
    return jsonify(fotos)


# Decorador para verificar se o usuário está logado
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Você precisa estar logado para acessar esta página.", "info")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


# Decorador para verificar permissões
def permission_required(module, action):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_id" not in session:
                flash("Você precisa estar logado para acessar esta página.", "info")
                return redirect(url_for("login"))

            user_id = session["user_id"]
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Verifica se o usuário é Master (tem acesso total)
            cur.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (user_id,))
            user = cur.fetchone()
            if user and user["tipo_usuario"] == "Master":
                cur.close()
                conn.close()
                return f(*args, **kwargs)

            # Verifica permissões específicas para o módulo e ação
            cur.execute(
                """
                SELECT COUNT(*) FROM permissoes
                WHERE usuario_id = %s AND modulo = %s AND acao = %s
            """,
                (user_id, module, action),
            )
            has_permission = cur.fetchone()[0] > 0
            
            cur.close()
            conn.close()

            if not has_permission:
                flash(
                    f"Você não tem permissão para realizar esta ação no módulo {module}.",
                    "danger",
                )
                return redirect(
                    url_for("dashboard")
                )  # Ou outra página de erro/acesso negado
            return f(*args, **kwargs)

        return decorated_function

    return decorator


# Context processor para injetar variáveis em todos os templates
@app.context_processor
def inject_global_vars():
    return {
        "system_version": SYSTEM_VERSION,
        "usuario_logado": session.get("username", "Convidado"),
    }


# --- Rotas de Autenticação ---
@app.route("/login", methods=["GET", "POST"])
def login():
    # Se o usuário já estiver logado, redireciona para o dashboard
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
    
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            "SELECT id, nome_usuario, senha_hash, status FROM usuarios WHERE nome_usuario = %s",
            (username,),
        )
        user = cur.fetchone()
        cur.close()
        conn.close()

        if (
            user
            and user["status"] == "Ativo"
            and check_password_hash(user["senha_hash"], password)
        ):
            session["user_id"] = user["id"]
            session["username"] = user["nome_usuario"]
            flash("Login realizado com sucesso!", "success")
            return redirect(
                url_for("dashboard")
            )  # Redireciona para o dashboard após o login
        else:
            flash("Usuário ou senha inválidos, ou usuário inativo.", "danger")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    # Se o usuário já estiver logado, redireciona para o dashboard
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            flash("As senhas não coincidem.", "danger")
            return render_template("register.html")

        # Hash da senha antes de armazenar
        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            # Insere o novo usuário com tipo "Operador" por padrão
            cur.execute(
                "INSERT INTO usuarios (nome_usuario, senha_hash, tipo_usuario, status) VALUES (%s, %s, %s, %s) RETURNING id",
                (username, hashed_password, "Operador", "Ativo")
            )
            new_user_id = cur.fetchone()[0]
            conn.commit()

            # Opcional: Atribuir permissões básicas para o novo usuário "Operador"
            # Isso pode ser feito de forma mais sofisticada, mas aqui é um exemplo básico.
            # Por exemplo, dar permissão de consulta para alguns módulos.
            modules_to_grant_access = [
                "Cadastro Fornecedores/Clientes",
                "Cadastro Imoveis",
                "Gestao Contratos",
                "Financeiro",
                "Cadastro Despesas",  # Nova permissão
                "Cadastro Origens",  # Nova permissão
                "Cadastro Receitas",  # Nova permissão
            ]
            for module in modules_to_grant_access:
                cur.execute(
                    "INSERT INTO permissoes (usuario_id, modulo, acao) VALUES (%s, %s, %s)",
                    (new_user_id, module, "Consultar")
                )
            conn.commit()

            flash(
                "Usuário cadastrado com sucesso! Você já pode fazer login.", "success"
            )
            return redirect(url_for("login"))
        except psycopg2.errors.UniqueViolation:
            flash("Nome de usuário já existe. Por favor, escolha outro.", "danger")
            conn.rollback()
        except Exception as e:
            flash(f"Erro ao cadastrar usuário: {e}", "danger")
            conn.rollback()
        finally:
            cur.close()
            conn.close()
    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
    session.pop("user_id", None)
    session.pop("username", None)
    flash("Você foi desconectado.", "info")
    return redirect(url_for("login"))


# --- Rota Principal (Dashboard) ---
@app.route("/") # Redireciona a raiz para o login
def index():
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    # Dados de exemplo para o dashboard
    exames_vencidos = 2
    exames_proximos = 0
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM imoveis")
    total_imoveis_ativos = cur.fetchone()[0]
    cur.close()
    conn.close()
    meses_labels = [
        "Ago",
        "Set",
        "Out",
        "Nov",
        "Dez",
        "Jan",
        "Fev",
        "Mar",
        "Abr",
        "Mai",
        "Jun",
        "Jul",
    ]
    contratacoes = [2, 3, 1, 4, 2, 3, 1, 2, 4, 3, 2, 1]
    demissoes = [1, 0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1]

    saldo_caixas = db.session.query(func.coalesce(func.sum(ContaCaixa.saldo_atual), 0)).scalar() or 0
    saldo_bancos = db.session.query(func.coalesce(func.sum(ContaBanco.saldo_atual), 0)).scalar() or 0
    saldo_total = float(saldo_caixas) + float(saldo_bancos)
    alertas_saldo_negativo = ContaCaixa.query.filter(ContaCaixa.saldo_atual < 0).count() + \
        ContaBanco.query.filter(ContaBanco.saldo_atual < 0).count()
    conciliacoes_pendentes = Conciliacao.query.filter_by(status='pendente').count()

    return render_template(
        "dashboard.html",
        exames_vencidos=exames_vencidos,
        exames_proximos=exames_proximos,
        total_imoveis_ativos=total_imoveis_ativos,
        meses_labels=meses_labels,
        contratacoes=contratacoes,
        demissoes=demissoes,
        saldo_total=saldo_total,
        alertas_saldo_negativo=alertas_saldo_negativo,
        conciliacoes_pendentes=conciliacoes_pendentes,
    )


# --- Módulo de Cadastros Essenciais ---


# 1.1. Cadastro de Fornecedores e Clientes (Pessoas)
@app.route("/pessoas")
@login_required
@permission_required("Cadastro Fornecedores/Clientes", "Consultar")
def pessoas_list():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    search_query = request.args.get("search", "")
    if search_query:
        cur.execute(
            """
            SELECT * FROM pessoas
            WHERE documento ILIKE %s OR razao_social_nome ILIKE %s OR nome_fantasia ILIKE %s
            ORDER BY data_cadastro DESC
        """,
            (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"),
        )
    else:
        cur.execute("SELECT * FROM pessoas ORDER BY data_cadastro DESC")
    pessoas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "pessoas/list.html", pessoas=pessoas, search_query=search_query
    )


@app.route("/pessoas/add", methods=["GET", "POST"])
@login_required
@permission_required("Cadastro Fornecedores/Clientes", "Incluir")
def pessoas_add():
    if request.method == "POST":
        try:
            documento = (
                request.form["documento"]
                .replace(".", "")
                .replace("/", "")
                .replace("-", "")
            )
            razao_social_nome = request.form["razao_social_nome"]
            nome_fantasia = request.form.get("nome_fantasia")
            endereco = request.form.get("endereco")
            bairro = request.form.get("bairro")
            cidade = request.form.get("cidade")
            estado = request.form.get("estado")
            cep = request.form.get("cep", "").replace("-", "")
            telefone = request.form.get("telefone")
            contato = request.form.get("contato")
            observacao = request.form.get("observacao")
            tipo = request.form["tipo"]
            status = request.form["status"]

            # Validação de CPF/CNPJ (simplificada, você precisaria de uma biblioteca real como "validate-docbr")
            if len(documento) == 11 and not documento.isdigit():
                 flash("CPF inválido. Deve conter apenas números.", "danger")
                 return render_template("pessoas/add_list.html", pessoa={})
            elif len(documento) == 14 and not documento.isdigit():
                 flash("CNPJ inválido. Deve conter apenas números.", "danger")
                 return render_template("pessoas/add_list.html", pessoa={})
            elif len(documento) != 11 and len(documento) != 14:
                flash(
                    "Documento deve ser um CPF (11 dígitos) ou CNPJ (14 dígitos).",
                    "danger",
                )
                return render_template("pessoas/add_list.html", pessoa={})
            
            # Exemplo de uso de validate-docbr (necessita instalação: pip install validate-docbr)
            # from validate_docbr import CPF, CNPJ
            # if len(documento) == 11:
            #     if not CPF().validate(documento):
            #         flash("CPF inválido.", "danger")
            #         return render_template("pessoas/add_list.html", pessoa={})
            # elif len(documento) == 14:
            #     if not CNPJ().validate(documento):
            #         flash("CNPJ inválido.", "danger")
            #         return render_template("pessoas/add_list.html", pessoa={})

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO pessoas (documento, razao_social_nome, nome_fantasia, endereco, bairro, cidade, estado, cep, telefone, contato, observacao, tipo, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
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
                    observacao,
                    tipo,
                    status,
                ),
            )
            conn.commit()
            cur.close()
            conn.close()
            flash("Pessoa cadastrada com sucesso!", "success")
            return redirect(url_for("pessoas_list"))
        except psycopg2.errors.UniqueViolation:
            flash("Erro: Documento (CPF/CNPJ) já cadastrado.", "danger")
            conn.rollback()  # Garante que a transação seja desfeita em caso de erro
            return render_template("pessoas/add_list.html", pessoa=request.form)
        except Exception as e:
            flash(f"Erro ao cadastrar pessoa: {e}", "danger")
            return render_template("pessoas/add_list.html", pessoa=request.form)
    return render_template("pessoas/add_list.html", pessoa={})


@app.route("/pessoas/edit/<int:id>", methods=["GET", "POST"])
@login_required
@permission_required("Cadastro Fornecedores/Clientes", "Editar")
def pessoas_edit(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == "POST":
        try:
            documento = (
                request.form["documento"]
                .replace(".", "")
                .replace("/", "")
                .replace("-", "")
            )
            razao_social_nome = request.form["razao_social_nome"]
            nome_fantasia = request.form.get("nome_fantasia")
            endereco = request.form.get("endereco")
            bairro = request.form.get("bairro")
            cidade = request.form.get("cidade")
            estado = request.form.get("estado")
            cep = request.form.get("cep", "").replace("-", "")
            telefone = request.form.get("telefone")
            contato = request.form.get("contato")
            observacao = request.form.get("observacao")
            tipo = request.form["tipo"]
            status = request.form["status"]

            # Validação de CPF/CNPJ (simplificada)
            if len(documento) == 11 and not documento.isdigit():
                 flash("CPF inválido. Deve conter apenas números.", "danger")
                 return render_template("pessoas/add_list.html", pessoa=request.form)
            elif len(documento) == 14 and not documento.isdigit():
                 flash("CNPJ inválido. Deve conter apenas números.", "danger")
                 return render_template("pessoas/add_list.html", pessoa={})
            elif len(documento) != 11 and len(documento) != 14:
                flash(
                    "Documento deve ser um CPF (11 dígitos) ou CNPJ (14 dígitos).",
                    "danger",
                )
                return render_template("pessoas/add_list.html", pessoa={})

            cur.execute(
                """
                UPDATE pessoas
                SET documento = %s, razao_social_nome = %s, nome_fantasia = %s, endereco = %s, bairro = %s, cidade = %s, estado = %s, cep = %s, telefone = %s, contato = %s, observacao = %s, tipo = %s, status = %s
                WHERE id = %s
                """,
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
                    observacao,
                    tipo,
                    status,
                    id,
                ),
            )
            conn.commit()
            flash("Pessoa atualizada com sucesso!", "success")
            return redirect(url_for("pessoas_list"))
        except psycopg2.errors.UniqueViolation:
            flash(
                "Erro: Documento (CPF/CNPJ) já cadastrado para outra pessoa.", "danger"
            )
            conn.rollback()
            # Recarrega os dados da pessoa para preencher o formulário novamente
            cur.execute("SELECT * FROM pessoas WHERE id = %s", (id,))
            pessoa = cur.fetchone()
            return render_template("pessoas/add_list.html", pessoa=pessoa)
        except Exception as e:
            flash(f"Erro ao atualizar pessoa: {e}", "danger")
            # Recarrega os dados da pessoa para preencher o formulário novamente
            cur.execute("SELECT * FROM pessoas WHERE id = %s", (id,))
            pessoa = cur.fetchone()
            return render_template("pessoas/add_list.html", pessoa=pessoa)

    cur.execute("SELECT * FROM pessoas WHERE id = %s", (id,))
    pessoa = cur.fetchone()
    cur.close()
    conn.close()
    if pessoa is None:
        flash("Pessoa não encontrada.", "danger")
        return redirect(url_for("pessoas_list"))
    return render_template("pessoas/add_list.html", pessoa=pessoa)


@app.route("/pessoas/delete/<int:id>", methods=["POST"])
@login_required
@permission_required("Cadastro Fornecedores/Clientes", "Excluir")
def pessoas_delete(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM pessoas WHERE id = %s", (id,))
        conn.commit()
        flash("Pessoa excluída com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir pessoa: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("pessoas_list"))


# --- Módulo de Gestão de Imóveis e Aluguéis ---


# 1.2. Cadastro de Imóveis
@app.route("/imoveis")
@login_required
@permission_required("Cadastro Imoveis", "Consultar")
def imoveis_list():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    search_query = request.args.get("search", "")
    if search_query:
        cur.execute(
            """
            SELECT * FROM imoveis
            WHERE endereco ILIKE %s OR bairro ILIKE %s OR cidade ILIKE %s OR inscricao_iptu ILIKE %s
            ORDER BY data_cadastro DESC
        """,
            (
                f"%{search_query}%",
                f"%{search_query}%",
                f"%{search_query}%",
                f"%{search_query}%",
            ),
        )
    else:
        cur.execute("SELECT * FROM imoveis ORDER BY data_cadastro DESC")
    imoveis = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "imoveis/list.html", imoveis=imoveis, search_query=search_query
    )


@app.route("/imoveis/mapa")
@login_required
@permission_required("Cadastro Imoveis", "Consultar")
def imoveis_mapa():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(
        """
        SELECT
            i.id,
            i.matricula,
            i.endereco,
            i.bairro,
            i.cidade,
            i.estado,
            i.inscricao_iptu,
            i.latitude,
            i.longitude,
            (c.id IS NOT NULL) AS contrato_ativo,
            p.razao_social_nome AS cliente_nome
        FROM imoveis i
        LEFT JOIN contratos_aluguel c
            ON c.imovel_id = i.id AND c.status_contrato = 'Ativo'
        LEFT JOIN pessoas p ON c.cliente_id = p.id
        WHERE i.latitude IS NOT NULL AND i.longitude IS NOT NULL
        """
    )
    imoveis = cur.fetchall()
    # Converte coordenadas DECIMAL do banco para float para uso no JavaScript
    imoveis = [
        {
            **dict(row),
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
        }
        for row in imoveis
    ]
    cur.close()
    conn.close()
    return render_template("imoveis/mapa.html", imoveis=imoveis)


@app.route("/imoveis/add", methods=["GET", "POST"])
@login_required
@permission_required("Cadastro Imoveis", "Incluir")
def imoveis_add():
    if request.method == "POST":
        try:
            tipo_imovel = request.form.get("tipo_imovel")
            endereco = request.form["endereco"]
            bairro = request.form.get("bairro")
            cidade = request.form.get("cidade")
            estado = request.form.get("estado")
            cep = request.form.get("cep")
            registro = request.form.get("registro")
            livro = request.form.get("livro")
            folha = request.form.get("folha")
            matricula = request.form.get("matricula")
            inscricao_iptu = request.form.get("inscricao_iptu")
            latitude = request.form.get("latitude")
            longitude = request.form.get("longitude")
            data_aquisicao_str = request.form.get("data_aquisicao")
            valor_imovel = request.form.get("valor_imovel")
            valor_previsto_aluguel = request.form.get("valor_previsto_aluguel")
            destinacao = request.form.get("destinacao")
            observacao = request.form.get("observacao")

            data_aquisicao = (
                datetime.strptime(data_aquisicao_str, "%Y-%m-%d").date()
                if data_aquisicao_str
                else None
            )

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO imoveis (tipo_imovel, endereco, bairro, cidade, estado, cep,
                                     registro, livro, folha, matricula, inscricao_iptu,
                                     latitude, longitude, data_aquisicao, valor_imovel,
                                     valor_previsto_aluguel, destinacao, observacao)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    tipo_imovel,
                    endereco,
                    bairro,
                    cidade,
                    estado,
                    cep,
                    registro,
                    livro,
                    folha,
                    matricula,
                    inscricao_iptu,
                    latitude,
                    longitude,
                    data_aquisicao,
                    valor_imovel,
                    valor_previsto_aluguel,
                    destinacao,
                    observacao,
                ),
            )
            imovel_id = cur.fetchone()[0]

            # Lidar com uploads de documentos
            if "anexos" in request.files:
                files = request.files.getlist("anexos")
                for file in files:
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        filepath = os.path.join(
                            app.config["UPLOAD_FOLDER"], "imoveis_anexos", filename
                        )
                        file.save(filepath)
                        cur.execute(
                            "INSERT INTO imovel_anexos (imovel_id, nome_arquivo, caminho_arquivo, tipo_anexo) VALUES (%s, %s, %s, %s)",
                            (
                                imovel_id,
                                filename,
                                filepath,
                                "documento",
                            ),
                        )

            # Upload de fotos (limite de 4)
            if "fotos" in request.files:
                fotos = request.files.getlist("fotos")[:4]
                for file in fotos:
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        filepath = os.path.join(
                            app.config["UPLOAD_FOLDER"], "imoveis_anexos", filename
                        )
                        file.save(filepath)
                        cur.execute(
                            "INSERT INTO imovel_anexos (imovel_id, nome_arquivo, caminho_arquivo, tipo_anexo) VALUES (%s, %s, %s, %s)",
                            (
                                imovel_id,
                                filename,
                                filepath,
                                "foto",
                            ),
                        )
            
            conn.commit()
            cur.close()
            conn.close()
            flash("Imóvel cadastrado com sucesso!", "success")
            return redirect(url_for("imoveis_list"))
        except psycopg2.errors.UniqueViolation:
            flash("Erro: Inscrição IPTU já cadastrada.", "danger")
            conn.rollback()
            return render_template("imoveis/add_list.html", imovel=request.form)
        except Exception as e:
            flash(f"Erro ao cadastrar imóvel: {e}", "danger")
            return render_template("imoveis/add_list.html", imovel=request.form)
    return render_template("imoveis/add_list.html", imovel={})


@app.route("/imoveis/edit/<int:id>", methods=["GET", "POST"])
@login_required
@permission_required("Cadastro Imoveis", "Editar")
def imoveis_edit(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    if request.method == "POST":
        try:
            tipo_imovel = request.form.get("tipo_imovel")
            endereco = request.form["endereco"]
            bairro = request.form.get("bairro")
            cidade = request.form.get("cidade")
            estado = request.form.get("estado")
            cep = request.form.get("cep")
            registro = request.form.get("registro")
            livro = request.form.get("livro")
            folha = request.form.get("folha")
            matricula = request.form.get("matricula")
            inscricao_iptu = request.form.get("inscricao_iptu")
            latitude = request.form.get("latitude")
            longitude = request.form.get("longitude")
            data_aquisicao_str = request.form.get("data_aquisicao")
            valor_imovel = request.form.get("valor_imovel")
            valor_previsto_aluguel = request.form.get("valor_previsto_aluguel")
            destinacao = request.form.get("destinacao")
            observacao = request.form.get("observacao")

            data_aquisicao = (
                datetime.strptime(data_aquisicao_str, "%Y-%m-%d").date()
                if data_aquisicao_str
                else None
            )

            cur.execute(
                """
                UPDATE imoveis
                SET tipo_imovel = %s, endereco = %s, bairro = %s, cidade = %s, estado = %s, cep = %s,
                    registro = %s, livro = %s, folha = %s, matricula = %s, inscricao_iptu = %s,
                    latitude = %s, longitude = %s, data_aquisicao = %s, valor_imovel = %s,
                    valor_previsto_aluguel = %s, destinacao = %s, observacao = %s
                WHERE id = %s
                """,
                (
                    tipo_imovel,
                    endereco,
                    bairro,
                    cidade,
                    estado,
                    cep,
                    registro,
                    livro,
                    folha,
                    matricula,
                    inscricao_iptu,
                    latitude,
                    longitude,
                    data_aquisicao,
                    valor_imovel,
                    valor_previsto_aluguel,
                    destinacao,
                    observacao,
                    id,
                ),
            )

            # Lidar com novos uploads de documentos
            if "anexos" in request.files:
                files = request.files.getlist("anexos")
                for file in files:
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        filepath = os.path.join(
                            app.config["UPLOAD_FOLDER"], "imoveis_anexos", filename
                        )
                        file.save(filepath)
                        cur.execute(
                            "INSERT INTO imovel_anexos (imovel_id, nome_arquivo, caminho_arquivo, tipo_anexo) VALUES (%s, %s, %s, %s)",
                            (id, filename, filepath, "documento"),
                        )

            # Upload de novas fotos (limite de 4 por envio)
            if "fotos" in request.files:
                fotos = request.files.getlist("fotos")[:4]
                for file in fotos:
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        filepath = os.path.join(
                            app.config["UPLOAD_FOLDER"], "imoveis_anexos", filename
                        )
                        file.save(filepath)
                        cur.execute(
                            "INSERT INTO imovel_anexos (imovel_id, nome_arquivo, caminho_arquivo, tipo_anexo) VALUES (%s, %s, %s, %s)",
                            (id, filename, filepath, "foto"),
                        )
            
            conn.commit()
            flash("Imóvel atualizado com sucesso!", "success")
            return redirect(url_for("imoveis_list"))
        except psycopg2.errors.UniqueViolation:
            flash("Erro: Inscrição IPTU já cadastrada para outro imóvel.", "danger")
            conn.rollback()
            # Recarrega os dados do imóvel para preencher o formulário novamente
            cur.execute("SELECT * FROM imoveis WHERE id = %s", (id,))
            imovel = cur.fetchone()
            cur.execute("SELECT * FROM imovel_anexos WHERE imovel_id = %s", (id,))
            anexos = cur.fetchall()
            return render_template(
                "imoveis/add_list.html", imovel=imovel, anexos=anexos
            )
        except Exception as e:
            flash(f"Erro ao atualizar imóvel: {e}", "danger")
            # Recarrega os dados do imóvel para preencher o formulário novamente
            cur.execute("SELECT * FROM imoveis WHERE id = %s", (id,))
            imovel = cur.fetchone()
            cur.execute("SELECT * FROM imovel_anexos WHERE imovel_id = %s", (id,))
            anexos = cur.fetchall()
            return render_template(
                "imoveis/add_list.html", imovel=imovel, anexos=anexos
            )

    cur.execute("SELECT * FROM imoveis WHERE id = %s", (id,))
    imovel = cur.fetchone()
    cur.execute("SELECT * FROM imovel_anexos WHERE imovel_id = %s", (id,))
    anexos = cur.fetchall()
    cur.close()
    conn.close()
    if imovel is None:
        flash("Imóvel não encontrado.", "danger")
        return redirect(url_for("imoveis_list"))
    return render_template("imoveis/add_list.html", imovel=imovel, anexos=anexos)


@app.route("/imoveis/delete/<int:id>", methods=["POST"])
@login_required
@permission_required("Cadastro Imoveis", "Excluir")
def imoveis_delete(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Primeiro, exclua os anexos relacionados para evitar violação de chave estrangeira
        cur.execute("DELETE FROM imovel_anexos WHERE imovel_id = %s", (id,))
        cur.execute("DELETE FROM imoveis WHERE id = %s", (id,))
        conn.commit()
        flash("Imóvel excluído com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir imóvel: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("imoveis_list"))


@app.route("/imoveis/anexo/delete/<int:anexo_id>", methods=["POST"])
@login_required
@permission_required(
    "Cadastro Imoveis", "Editar"
)  # Permissão para editar imóvel inclui exclusão de anexos
def imovel_anexo_delete(anexo_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cur.execute(
            "SELECT caminho_arquivo, imovel_id FROM imovel_anexos WHERE id = %s",
            (anexo_id,),
        )
        anexo = cur.fetchone()
        
        if anexo:
            # Tenta remover o arquivo físico
            if os.path.exists(anexo["caminho_arquivo"]):
                os.remove(anexo["caminho_arquivo"])

            cur.execute("DELETE FROM imovel_anexos WHERE id = %s", (anexo_id,))
            conn.commit()
            flash("Anexo removido com sucesso!", "success")
            return redirect(url_for("imoveis_edit", id=anexo["imovel_id"]))
        else:
            flash("Anexo não encontrado.", "danger")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao remover anexo: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(
        url_for("imoveis_list")
    )  # Redireciona para a lista caso não encontre o anexo ou erro


# --- Avaliações de Imóveis ---
@app.route("/avaliacoes-imovel")
@login_required
@permission_required("Cadastro Imoveis", "Consultar")
def avaliacoes_imovel_list():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    search_query = request.args.get("search", "")
    if search_query:
        cur.execute(
            """
            SELECT a.*, i.endereco || ', ' || i.bairro AS endereco_imovel
            FROM avaliacoes_imovel a
            JOIN imoveis i ON a.imovel_id = i.id
            WHERE i.endereco ILIKE %s
            ORDER BY a.data_avaliacao DESC
            """,
            (f"%{search_query}%",),
        )
    else:
        cur.execute(
            """
            SELECT a.*, i.endereco || ', ' || i.bairro AS endereco_imovel
            FROM avaliacoes_imovel a
            JOIN imoveis i ON a.imovel_id = i.id
            ORDER BY a.data_avaliacao DESC
            """
        )
    avaliacoes = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "avaliacoes_imovel/list.html", avaliacoes=avaliacoes, search_query=search_query
    )


@app.route("/avaliacoes-imovel/add", methods=["GET", "POST"])
@login_required
@permission_required("Cadastro Imoveis", "Incluir")
def avaliacoes_imovel_add():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == "POST":
        try:
            imovel_id = request.form["imovel_id"]
            data_str = request.form["data_avaliacao"]
            data_avaliacao = datetime.strptime(data_str + "-01", "%Y-%m-%d").date()
            valor_avaliacao = request.form["valor_avaliacao"]
            cur.execute(
                """
                INSERT INTO avaliacoes_imovel (imovel_id, data_avaliacao, valor_avaliacao)
                VALUES (%s, %s, %s)
                """,
                (imovel_id, data_avaliacao, valor_avaliacao),
            )
            conn.commit()
            flash("Avaliação cadastrada com sucesso!", "success")
            return redirect(url_for("avaliacoes_imovel_list"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar avaliação: {e}", "danger")
    cur.execute("SELECT id, endereco, bairro FROM imoveis ORDER BY endereco")
    imoveis = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("avaliacoes_imovel/add_list.html", avaliacao={}, imoveis=imoveis)


@app.route("/avaliacoes-imovel/edit/<int:id>", methods=["GET", "POST"])
@login_required
@permission_required("Cadastro Imoveis", "Editar")
def avaliacoes_imovel_edit(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == "POST":
        try:
            imovel_id = request.form["imovel_id"]
            data_str = request.form["data_avaliacao"]
            data_avaliacao = datetime.strptime(data_str + "-01", "%Y-%m-%d").date()
            valor_avaliacao = request.form["valor_avaliacao"]
            cur.execute(
                """
                UPDATE avaliacoes_imovel
                SET imovel_id = %s, data_avaliacao = %s, valor_avaliacao = %s
                WHERE id = %s
                """,
                (imovel_id, data_avaliacao, valor_avaliacao, id),
            )
            conn.commit()
            flash("Avaliação atualizada com sucesso!", "success")
            return redirect(url_for("avaliacoes_imovel_list"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao atualizar avaliação: {e}", "danger")
    cur.execute(
        """
        SELECT a.*, i.endereco || ', ' || i.bairro AS endereco_imovel
        FROM avaliacoes_imovel a
        JOIN imoveis i ON a.imovel_id = i.id
        WHERE a.id = %s
        """,
        (id,),
    )
    avaliacao = cur.fetchone()
    cur.execute("SELECT id, endereco, bairro FROM imoveis ORDER BY endereco")
    imoveis = cur.fetchall()
    cur.close()
    conn.close()
    if avaliacao is None:
        flash("Avaliação não encontrada.", "danger")
        return redirect(url_for("avaliacoes_imovel_list"))
    return render_template(
        "avaliacoes_imovel/add_list.html", avaliacao=avaliacao, imoveis=imoveis
    )


@app.route("/avaliacoes-imovel/delete/<int:id>", methods=["POST"])
@login_required
@permission_required("Cadastro Imoveis", "Excluir")
def avaliacoes_imovel_delete(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM avaliacoes_imovel WHERE id = %s", (id,))
        conn.commit()
        flash("Avaliação excluída com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir avaliação: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("avaliacoes_imovel_list"))


# --- 1.3. Cadastro de Despesas ---
@app.route("/despesas")
@login_required
@permission_required("Cadastro Despesas", "Consultar")
def despesas_list():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    search_query = request.args.get("search", "")
    if search_query:
        cur.execute(
            """
            SELECT * FROM despesas_cadastro
            WHERE descricao ILIKE %s
            ORDER BY data_cadastro DESC
        """,
            (f"%{search_query}%",),
        )
    else:
        cur.execute("SELECT * FROM despesas_cadastro ORDER BY data_cadastro DESC")
    despesas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "despesas/list.html", despesas=despesas, search_query=search_query
    )


@app.route("/despesas/add", methods=["GET", "POST"])
@login_required
@permission_required("Cadastro Despesas", "Incluir")
def despesas_add():
    if request.method == "POST":
        descricao = request.form["descricao"]
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO despesas_cadastro (descricao) VALUES (%s)", (descricao,)
            )
            conn.commit()
            flash("Despesa cadastrada com sucesso!", "success")
            return redirect(url_for("despesas_list"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar despesa: {e}", "danger")
            return render_template("despesas/add_list.html", despesa=request.form)
        finally:
            cur.close()
            conn.close()
    return render_template("despesas/add_list.html", despesa={})


@app.route("/despesas/edit/<int:id>", methods=["GET", "POST"])
@login_required
@permission_required("Cadastro Despesas", "Editar")
def despesas_edit(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == "POST":
        descricao = request.form["descricao"]
        try:
            cur.execute(
                "UPDATE despesas_cadastro SET descricao = %s WHERE id = %s",
                (descricao, id),
            )
            conn.commit()
            flash("Despesa atualizada com sucesso!", "success")
            return redirect(url_for("despesas_list"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao atualizar despesa: {e}", "danger")
            cur.execute("SELECT * FROM despesas_cadastro WHERE id = %s", (id,))
            despesa = cur.fetchone()
            return render_template("despesas/add_list.html", despesa=despesa)
    cur.execute("SELECT * FROM despesas_cadastro WHERE id = %s", (id,))
    despesa = cur.fetchone()
    cur.close()
    conn.close()
    if despesa is None:
        flash("Despesa não encontrada.", "danger")
        return redirect(url_for("despesas_list"))
    return render_template("despesas/add_list.html", despesa=despesa)


@app.route("/despesas/delete/<int:id>", methods=["POST"])
@login_required
@permission_required("Cadastro Despesas", "Excluir")
def despesas_delete(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM despesas_cadastro WHERE id = %s", (id,))
        conn.commit()
        flash("Despesa excluída com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir despesa: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("despesas_list"))


# --- 1.4. Cadastro de Origens ---
@app.route("/origens")
@login_required
@permission_required("Cadastro Origens", "Consultar")
def origens_list():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    search_query = request.args.get("search", "")
    if search_query:
        cur.execute(
            """
            SELECT * FROM origens_cadastro
            WHERE descricao ILIKE %s
            ORDER BY data_cadastro DESC
        """,
            (f"%{search_query}%",),
        )
    else:
        cur.execute("SELECT * FROM origens_cadastro ORDER BY data_cadastro DESC")
    origens = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "origens/list.html", origens=origens, search_query=search_query
    )


@app.route("/origens/add", methods=["GET", "POST"])
@login_required
@permission_required("Cadastro Origens", "Incluir")
def origens_add():
    if request.method == "POST":
        descricao = request.form["descricao"]
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO origens_cadastro (descricao) VALUES (%s)", (descricao,)
            )
            conn.commit()
            flash("Origem cadastrada com sucesso!", "success")
            return redirect(url_for("origens_list"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar origem: {e}", "danger")
            return render_template("origens/add_list.html", origem=request.form)
        finally:
            cur.close()
            conn.close()
    return render_template("origens/add_list.html", origem={})


@app.route("/origens/edit/<int:id>", methods=["GET", "POST"])
@login_required
@permission_required("Cadastro Origens", "Editar")
def origens_edit(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == "POST":
        descricao = request.form["descricao"]
        try:
            cur.execute(
                "UPDATE origens_cadastro SET descricao = %s WHERE id = %s",
                (descricao, id),
            )
            conn.commit()
            flash("Origem atualizada com sucesso!", "success")
            return redirect(url_for("origens_list"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao atualizar origem: {e}", "danger")
            cur.execute("SELECT * FROM origens_cadastro WHERE id = %s", (id,))
            origem = cur.fetchone()
            return render_template("origens/add_list.html", origem=origem)
    cur.execute("SELECT * FROM origens_cadastro WHERE id = %s", (id,))
    origem = cur.fetchone()
    cur.close()
    conn.close()
    if origem is None:
        flash("Origem não encontrada.", "danger")
        return redirect(url_for("origens_list"))
    return render_template("origens/add_list.html", origem=origem)


@app.route("/origens/delete/<int:id>", methods=["POST"])
@login_required
@permission_required("Cadastro Origens", "Excluir")
def origens_delete(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM origens_cadastro WHERE id = %s", (id,))
        conn.commit()
        flash("Origem excluída com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir origem: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("origens_list"))


# --- 1.5. Cadastro de Receitas ---
@app.route("/receitas")
@login_required
@permission_required("Cadastro Receitas", "Consultar")
def receitas_list():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    search_query = request.args.get("search", "")
    if search_query:
        cur.execute(
            """
            SELECT * FROM receitas_cadastro
            WHERE descricao ILIKE %s
            ORDER BY data_cadastro DESC
        """,
            (f"%{search_query}%",),
        )
    else:
        cur.execute("SELECT * FROM receitas_cadastro ORDER BY data_cadastro DESC")
    receitas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "receitaas/list.html", receitas=receitas, search_query=search_query
    )


@app.route("/receitas/add", methods=["GET", "POST"])
@login_required
@permission_required("Cadastro Receitas", "Incluir")
def receitas_add():
    if request.method == "POST":
        descricao = request.form["descricao"]
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO receitas_cadastro (descricao) VALUES (%s)", (descricao,)
            )
            conn.commit()
            flash("Receita cadastrada com sucesso!", "success")
            return redirect(url_for("receitas_list"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar receita: {e}", "danger")
            return render_template("receitaas/add_list.html", receita=request.form)
        finally:
            cur.close()
            conn.close()
    return render_template("receitaas/add_list.html", receita={})


@app.route("/receitas/edit/<int:id>", methods=["GET", "POST"])
@login_required
@permission_required("Cadastro Receitas", "Editar")
def receitas_edit(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == "POST":
        descricao = request.form["descricao"]
        try:
            cur.execute(
                "UPDATE receitas_cadastro SET descricao = %s WHERE id = %s",
                (descricao, id),
            )
            conn.commit()
            flash("Receita atualizada com sucesso!", "success")
            return redirect(url_for("receitas_list"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao atualizar receita: {e}", "danger")
            cur.execute("SELECT * FROM receitas_cadastro WHERE id = %s", (id,))
            receita = cur.fetchone()
            return render_template("receitaas/add_list.html", receita=receita)
    cur.execute("SELECT * FROM receitas_cadastro WHERE id = %s", (id,))
    receita = cur.fetchone()
    cur.close()
    conn.close()
    if receita is None:
        flash("Receita não encontrada.", "danger")
        return redirect(url_for("receitas_list"))
    return render_template("receitaas/add_list.html", receita=receita)


@app.route("/receitas/delete/<int:id>", methods=["POST"])
@login_required
@permission_required("Cadastro Receitas", "Excluir")
def receitas_delete(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM receitas_cadastro WHERE id = %s", (id,))
        conn.commit()
        flash("Receita excluída com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir receita: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("receitas_list"))


# --- Rotas para outros módulos (placeholders existentes) ---
@app.route("/contratos")
@login_required
@permission_required("Gestao Contratos", "Consultar")
def contratos_list():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    search_query = request.args.get("search", "")
    if search_query:
        cur.execute(
            """
            SELECT c.*, i.endereco || ', ' || i.bairro AS endereco_imovel
            FROM contratos_aluguel c
            JOIN imoveis i ON c.imovel_id = i.id
            WHERE c.nome_inquilino ILIKE %s OR i.endereco ILIKE %s
            ORDER BY c.data_cadastro DESC
        """,
            (f"%{search_query}%", f"%{search_query}%"),
        )
    else:
        cur.execute(
            """
            SELECT c.*, i.endereco || ', ' || i.bairro AS endereco_imovel
            FROM contratos_aluguel c
            JOIN imoveis i ON c.imovel_id = i.id
            ORDER BY c.data_cadastro DESC
        """
        )
    contratos = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "contratos/list.html", contratos=contratos, search_query=search_query
    )


@app.route("/contratos/add", methods=["GET", "POST"])
@login_required
@permission_required("Gestao Contratos", "Incluir")
def contratos_add():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == "POST":
        try:
            imovel_id = request.form["imovel_id"]
            cliente_id = request.form["cliente_id"]
            data_inicio = datetime.strptime(request.form["data_inicio"], "%Y-%m-%d").date()
            data_fim = datetime.strptime(request.form["data_fim"], "%Y-%m-%d").date()
            quantidade_parcelas = request.form["quantidade_parcelas"]
            valor_parcela = request.form["valor_parcela"]
            status_contrato = request.form["status_contrato"]
            observacao = request.form.get("observacao")

            cur.execute(
                "SELECT razao_social_nome, endereco, bairro, cidade, estado, cep, telefone FROM pessoas WHERE id = %s",
                (cliente_id,),
            )
            cli = cur.fetchone()
            nome_inquilino = cli["razao_social_nome"] if cli else ""
            endereco_inquilino = cli["endereco"] if cli else ""
            bairro_inquilino = cli["bairro"] if cli else ""
            cidade_inquilino = cli["cidade"] if cli else ""
            estado_inquilino = cli["estado"] if cli else ""
            cep_inquilino = cli["cep"] if cli else ""
            telefone_inquilino = cli["telefone"] if cli else ""

            cur.execute(
                """
                INSERT INTO contratos_aluguel (
                    imovel_id, cliente_id, nome_inquilino, endereco_inquilino,
                    bairro_inquilino, cidade_inquilino, estado_inquilino,
                    cep_inquilino, telefone_inquilino, data_inicio, data_fim,
                    quantidade_parcelas, valor_parcela, status_contrato, observacao
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    imovel_id,
                    cliente_id,
                    nome_inquilino,
                    endereco_inquilino,
                    bairro_inquilino,
                    cidade_inquilino,
                    estado_inquilino,
                    cep_inquilino,
                    telefone_inquilino,
                    data_inicio,
                    data_fim,
                    quantidade_parcelas,
                    valor_parcela,
                    status_contrato,
                    observacao,
                ),
            )
            contrato_id = cur.fetchone()[0]

            if "anexos" in request.files:
                files = request.files.getlist("anexos")
                for file in files:
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        filepath = os.path.join(
                            app.config["UPLOAD_FOLDER"],
                            "contratos_anexos",
                            filename,
                        )
                        file.save(filepath)
                        cur.execute(
                            "INSERT INTO contrato_anexos (contrato_id, nome_arquivo, caminho_arquivo, tipo_anexo) VALUES (%s, %s, %s, %s)",
                            (contrato_id, filename, filepath, "documento"),
                        )

            conn.commit()
            flash("Contrato cadastrado com sucesso!", "success")
            return redirect(url_for("contratos_list"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar contrato: {e}", "danger")
            cur.execute("SELECT id, endereco FROM imoveis ORDER BY endereco")
            imoveis = cur.fetchall()
            cur.execute(
                "SELECT * FROM pessoas WHERE tipo = 'Cliente' ORDER BY razao_social_nome"
            )
            clientes = cur.fetchall()
            return render_template(
                "contratos/add_list.html",
                contrato=request.form,
                imoveis=imoveis,
                clientes=clientes,
                anexos=[],
            )

    cur.execute("SELECT id, endereco FROM imoveis ORDER BY endereco")
    imoveis = cur.fetchall()
    cur.execute(
        "SELECT * FROM pessoas WHERE tipo = 'Cliente' ORDER BY razao_social_nome"
    )
    clientes = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "contratos/add_list.html", contrato={}, imoveis=imoveis, clientes=clientes, anexos=[]
    )


@app.route("/contratos/edit/<int:id>", methods=["GET", "POST"])
@login_required
@permission_required("Gestao Contratos", "Editar")
def contratos_edit(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == "POST":
        try:
            imovel_id = request.form["imovel_id"]
            cliente_id = request.form["cliente_id"]
            data_inicio = datetime.strptime(request.form["data_inicio"], "%Y-%m-%d").date()
            data_fim = datetime.strptime(request.form["data_fim"], "%Y-%m-%d").date()
            quantidade_parcelas = request.form["quantidade_parcelas"]
            valor_parcela = request.form["valor_parcela"]
            status_contrato = request.form["status_contrato"]
            observacao = request.form.get("observacao")

            cur.execute(
                "SELECT razao_social_nome, endereco, bairro, cidade, estado, cep, telefone FROM pessoas WHERE id = %s",
                (cliente_id,),
            )
            cli = cur.fetchone()
            nome_inquilino = cli["razao_social_nome"] if cli else ""
            endereco_inquilino = cli["endereco"] if cli else ""
            bairro_inquilino = cli["bairro"] if cli else ""
            cidade_inquilino = cli["cidade"] if cli else ""
            estado_inquilino = cli["estado"] if cli else ""
            cep_inquilino = cli["cep"] if cli else ""
            telefone_inquilino = cli["telefone"] if cli else ""

            cur.execute(
                """
                UPDATE contratos_aluguel
                SET imovel_id = %s, cliente_id = %s, nome_inquilino = %s,
                    endereco_inquilino = %s, bairro_inquilino = %s,
                    cidade_inquilino = %s, estado_inquilino = %s,
                    cep_inquilino = %s, telefone_inquilino = %s,
                    data_inicio = %s, data_fim = %s,
                    quantidade_parcelas = %s, valor_parcela = %s,
                    status_contrato = %s, observacao = %s
                WHERE id = %s
                """,
                (
                    imovel_id,
                    cliente_id,
                    nome_inquilino,
                    endereco_inquilino,
                    bairro_inquilino,
                    cidade_inquilino,
                    estado_inquilino,
                    cep_inquilino,
                    telefone_inquilino,
                    data_inicio,
                    data_fim,
                    quantidade_parcelas,
                    valor_parcela,
                    status_contrato,
                    observacao,
                    id,
                ),
            )

            if "anexos" in request.files:
                files = request.files.getlist("anexos")
                for file in files:
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        filepath = os.path.join(
                            app.config["UPLOAD_FOLDER"],
                            "contratos_anexos",
                            filename,
                        )
                        file.save(filepath)
                        cur.execute(
                            "INSERT INTO contrato_anexos (contrato_id, nome_arquivo, caminho_arquivo, tipo_anexo) VALUES (%s, %s, %s, %s)",
                            (id, filename, filepath, "documento"),
                        )

            conn.commit()
            flash("Contrato atualizado com sucesso!", "success")
            return redirect(url_for("contratos_list"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao atualizar contrato: {e}", "danger")

    cur.execute("SELECT * FROM contratos_aluguel WHERE id = %s", (id,))
    contrato = cur.fetchone()
    cur.execute("SELECT * FROM contrato_anexos WHERE contrato_id = %s", (id,))
    anexos = cur.fetchall()
    cur.execute("SELECT id, endereco FROM imoveis ORDER BY endereco")
    imoveis = cur.fetchall()
    cur.execute(
        "SELECT * FROM pessoas WHERE tipo = 'Cliente' ORDER BY razao_social_nome"
    )
    clientes = cur.fetchall()
    cur.close()
    conn.close()
    if contrato is None:
        flash("Contrato não encontrado.", "danger")
        return redirect(url_for("contratos_list"))
    return render_template(
        "contratos/add_list.html",
        contrato=contrato,
        imoveis=imoveis,
        clientes=clientes,
        anexos=anexos,
    )


@app.route("/contratos/delete/<int:id>", methods=["POST"])
@login_required
@permission_required("Gestao Contratos", "Excluir")
def contratos_delete(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cur.execute(
            "SELECT id, caminho_arquivo FROM contrato_anexos WHERE contrato_id = %s",
            (id,),
        )
        anexos = cur.fetchall()
        for anexo in anexos:
            if os.path.exists(anexo["caminho_arquivo"]):
                os.remove(anexo["caminho_arquivo"])
        cur.execute("DELETE FROM contrato_anexos WHERE contrato_id = %s", (id,))
        cur.execute("DELETE FROM contratos_aluguel WHERE id = %s", (id,))
        conn.commit()
        flash("Contrato excluído com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir contrato: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("contratos_list"))


@app.route("/contratos/anexo/delete/<int:anexo_id>", methods=["POST"])
@login_required
@permission_required("Gestao Contratos", "Editar")
def contrato_anexo_delete(anexo_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cur.execute(
            "SELECT caminho_arquivo, contrato_id FROM contrato_anexos WHERE id = %s",
            (anexo_id,),
        )
        anexo = cur.fetchone()
        if anexo:
            if os.path.exists(anexo["caminho_arquivo"]):
                os.remove(anexo["caminho_arquivo"])
            cur.execute("DELETE FROM contrato_anexos WHERE id = %s", (anexo_id,))
            conn.commit()
            flash("Anexo removido com sucesso!", "success")
            return redirect(url_for("contratos_edit", id=anexo["contrato_id"]))
        else:
            flash("Anexo não encontrado.", "danger")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao remover anexo: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("contratos_list"))


# --- Reajustes de Contrato ---
@app.route("/reajustes", methods=["GET"])
@login_required
@permission_required("Gestao Contratos", "Consultar")
def reajustes_list():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    search_query = request.args.get("search", "")
    if search_query:
        cur.execute(
            """
            SELECT r.*, c.nome_inquilino, c.valor_parcela
            FROM reajustes_contrato r
            JOIN contratos_aluguel c ON r.contrato_id = c.id
            WHERE CAST(r.contrato_id AS TEXT) ILIKE %s OR c.nome_inquilino ILIKE %s
            ORDER BY r.data_alteracao DESC
            """,
            (f"%{search_query}%", f"%{search_query}%"),
        )
    else:
        cur.execute(
            """
            SELECT r.*, c.nome_inquilino, c.valor_parcela
            FROM reajustes_contrato r
            JOIN contratos_aluguel c ON r.contrato_id = c.id
            ORDER BY r.data_alteracao DESC
            """
        )
    reajustes = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "reajustes_contrato/list.html", reajustes=reajustes, search_query=search_query
    )


@app.route("/reajustes/add", methods=["GET", "POST"])
@login_required
@permission_required("Gestao Contratos", "Incluir")
def reajustes_add():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == "POST":
        try:
            contrato_id = request.form["contrato_id"]
            data_alteracao = datetime.strptime(request.form["data_alteracao"], "%Y-%m-%d").date()
            percentual_reajuste = float(request.form["percentual_reajuste"])
            cur.execute(
                "SELECT valor_parcela FROM contratos_aluguel WHERE id = %s",
                (contrato_id,),
            )
            contrato = cur.fetchone()
            if not contrato:
                flash("Contrato não encontrado.", "danger")
                return render_template("reajustes_contrato/add_list.html", reajuste=request.form)
            valor_atual = float(contrato["valor_parcela"])
            novo_valor = round(valor_atual * (1 + percentual_reajuste / 100), 2)
            observacao = request.form.get("observacao")
            cur.execute(
                """
                INSERT INTO reajustes_contrato (contrato_id, data_alteracao, percentual_reajuste, novo_valor_parcela, observacao)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (contrato_id, data_alteracao, percentual_reajuste, novo_valor, observacao),
            )
            cur.execute(
                "UPDATE contratos_aluguel SET valor_parcela = %s WHERE id = %s",
                (novo_valor, contrato_id),
            )
            conn.commit()
            flash("Reajuste cadastrado com sucesso!", "success")
            return redirect(url_for("reajustes_list"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar reajuste: {e}", "danger")
            return render_template("reajustes_contrato/add_list.html", reajuste=request.form)
        finally:
            cur.close()
            conn.close()
    return render_template("reajustes_contrato/add_list.html", reajuste={})


@app.route("/reajustes/edit/<int:id>", methods=["GET", "POST"])
@login_required
@permission_required("Gestao Contratos", "Editar")
def reajustes_edit(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == "POST":
        try:
            contrato_id = request.form["contrato_id"]
            data_alteracao = datetime.strptime(request.form["data_alteracao"], "%Y-%m-%d").date()
            percentual_reajuste = float(request.form["percentual_reajuste"])
            cur.execute(
                "SELECT valor_parcela FROM contratos_aluguel WHERE id = %s",
                (contrato_id,),
            )
            contrato = cur.fetchone()
            if not contrato:
                flash("Contrato não encontrado.", "danger")
                return render_template("reajustes_contrato/add_list.html", reajuste=request.form)
            valor_atual = float(contrato["valor_parcela"])
            novo_valor = round(valor_atual * (1 + percentual_reajuste / 100), 2)
            observacao = request.form.get("observacao")
            cur.execute(
                """
                UPDATE reajustes_contrato
                SET contrato_id = %s, data_alteracao = %s, percentual_reajuste = %s, novo_valor_parcela = %s, observacao = %s
                WHERE id = %s
                """,
                (contrato_id, data_alteracao, percentual_reajuste, novo_valor, observacao, id),
            )
            cur.execute(
                "UPDATE contratos_aluguel SET valor_parcela = %s WHERE id = %s",
                (novo_valor, contrato_id),
            )
            conn.commit()
            flash("Reajuste atualizado com sucesso!", "success")
            return redirect(url_for("reajustes_list"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao atualizar reajuste: {e}", "danger")
    cur.execute(
        "SELECT * FROM reajustes_contrato WHERE id = %s",
        (id,),
    )
    reajuste = cur.fetchone()
    cur.close()
    conn.close()
    if reajuste is None:
        flash("Reajuste não encontrado.", "danger")
        return redirect(url_for("reajustes_list"))
    return render_template("reajustes_contrato/add_list.html", reajuste=reajuste)


@app.route("/reajustes/delete/<int:id>", methods=["POST"])
@login_required
@permission_required("Gestao Contratos", "Excluir")
def reajustes_delete(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM reajustes_contrato WHERE id = %s", (id,))
        conn.commit()
        flash("Reajuste excluído com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir reajuste: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("reajustes_list"))


@app.route("/reajustes/contrato/<int:contrato_id>")
@login_required
def contrato_info(contrato_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(
        "SELECT id, nome_inquilino, valor_parcela FROM contratos_aluguel WHERE id = %s",
        (contrato_id,),
    )
    contrato = cur.fetchone()
    cur.close()
    conn.close()
    if contrato:
        return {
            "id": contrato["id"],
            "nome_inquilino": contrato["nome_inquilino"],
            "valor_parcela": float(contrato["valor_parcela"]),
        }
    return {}, 404


# --- Módulo Financeiro ---
@app.route("/contas-a-receber")
@login_required
@permission_required("Financeiro", "Consultar")
def contas_a_receber_list():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    search_query = request.args.get("search", "")
    if search_query:
        cur.execute(
            """
            SELECT cr.*, p.razao_social_nome AS cliente, r.descricao AS receita
            FROM contas_a_receber cr
            JOIN pessoas p ON cr.cliente_id = p.id
            JOIN receitas_cadastro r ON cr.receita_id = r.id
            WHERE p.razao_social_nome ILIKE %s OR r.descricao ILIKE %s
            ORDER BY cr.data_vencimento DESC
            """,
            (f"%{search_query}%", f"%{search_query}%"),
        )
    else:
        cur.execute(
            """
            SELECT cr.*, p.razao_social_nome AS cliente, r.descricao AS receita
            FROM contas_a_receber cr
            JOIN pessoas p ON cr.cliente_id = p.id
            JOIN receitas_cadastro r ON cr.receita_id = r.id
            ORDER BY cr.data_vencimento DESC
            """
        )
    contas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "financeiro/contas_a_receber/list.html",
        contas=contas,
        search_query=search_query,
    )


@app.route("/contas-a-receber/add", methods=["GET", "POST"])
@login_required
@permission_required("Financeiro", "Incluir")
def contas_a_receber_add():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == "POST":
        try:
            contrato_id = request.form.get("contrato_id") or None
            receita_id = request.form["receita_id"]
            cliente_id = request.form["cliente_id"]
            parcela_numero = request.form.get("parcela_numero") or None
            data_vencimento = request.form["data_vencimento"]
            valor_previsto = request.form["valor_previsto"]
            data_pagamento = request.form.get("data_pagamento") or None
            valor_pago = request.form.get("valor_pago") or None
            valor_desconto = request.form.get("valor_desconto") or 0
            valor_multa = request.form.get("valor_multa") or 0
            valor_juros = request.form.get("valor_juros") or 0
            observacao = request.form.get("observacao")
            status_conta = request.form.get("status_conta")
            origem_id = request.form.get("origem_id") or None

            cur.execute(
                """
                INSERT INTO contas_a_receber (
                    contrato_id, receita_id, cliente_id, parcela_numero,
                    data_vencimento, valor_previsto, data_pagamento, valor_pago,
                    valor_desconto, valor_multa, valor_juros, observacao,
                    status_conta, origem_id
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    contrato_id,
                    receita_id,
                    cliente_id,
                    parcela_numero,
                    data_vencimento,
                    valor_previsto,
                    data_pagamento,
                    valor_pago,
                    valor_desconto,
                    valor_multa,
                    valor_juros,
                    observacao,
                    status_conta,
                    origem_id,
                ),
            )
            conn.commit()
            flash("Conta a receber cadastrada com sucesso!", "success")
            return redirect(url_for("contas_a_receber_list"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar conta: {e}", "danger")
    cur.execute("SELECT id, descricao FROM receitas_cadastro ORDER BY descricao")
    receitas = cur.fetchall()
    cur.execute(
        "SELECT id, razao_social_nome FROM pessoas WHERE tipo = 'Cliente' ORDER BY razao_social_nome"
    )
    clientes = cur.fetchall()
    cur.execute("SELECT id, descricao FROM origens_cadastro ORDER BY descricao")
    origens = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "financeiro/contas_a_receber/add_list.html",
        conta=request.form,
        receitas=receitas,
        clientes=clientes,
        origens=origens,
    )


@app.route("/contas-a-receber/edit/<int:id>", methods=["GET", "POST"])
@login_required
@permission_required("Financeiro", "Editar")
def contas_a_receber_edit(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == "POST":
        try:
            contrato_id = request.form.get("contrato_id") or None
            receita_id = request.form["receita_id"]
            cliente_id = request.form["cliente_id"]
            parcela_numero = request.form.get("parcela_numero") or None
            data_vencimento = request.form["data_vencimento"]
            valor_previsto = request.form["valor_previsto"]
            data_pagamento = request.form.get("data_pagamento") or None
            valor_pago = request.form.get("valor_pago") or None
            valor_desconto = request.form.get("valor_desconto") or 0
            valor_multa = request.form.get("valor_multa") or 0
            valor_juros = request.form.get("valor_juros") or 0
            observacao = request.form.get("observacao")
            status_conta = request.form.get("status_conta")
            origem_id = request.form.get("origem_id") or None

            cur.execute(
                """
                UPDATE contas_a_receber
                SET contrato_id=%s, receita_id=%s, cliente_id=%s, parcela_numero=%s,
                    data_vencimento=%s, valor_previsto=%s, data_pagamento=%s,
                    valor_pago=%s, valor_desconto=%s, valor_multa=%s, valor_juros=%s,
                    observacao=%s, status_conta=%s, origem_id=%s
                WHERE id=%s
                """,
                (
                    contrato_id,
                    receita_id,
                    cliente_id,
                    parcela_numero,
                    data_vencimento,
                    valor_previsto,
                    data_pagamento,
                    valor_pago,
                    valor_desconto,
                    valor_multa,
                    valor_juros,
                    observacao,
                    status_conta,
                    origem_id,
                    id,
                ),
            )
            conn.commit()
            flash("Conta a receber atualizada com sucesso!", "success")
            return redirect(url_for("contas_a_receber_list"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao atualizar conta: {e}", "danger")
    cur.execute("SELECT * FROM contas_a_receber WHERE id = %s", (id,))
    conta = cur.fetchone()
    cur.execute("SELECT id, descricao FROM receitas_cadastro ORDER BY descricao")
    receitas = cur.fetchall()
    cur.execute(
        "SELECT id, razao_social_nome FROM pessoas WHERE tipo = 'Cliente' ORDER BY razao_social_nome"
    )
    clientes = cur.fetchall()
    cur.execute("SELECT id, descricao FROM origens_cadastro ORDER BY descricao")
    origens = cur.fetchall()
    cur.close()
    conn.close()
    if conta is None:
        flash("Conta não encontrada.", "danger")
        return redirect(url_for("contas_a_receber_list"))
    return render_template(
        "financeiro/contas_a_receber/add_list.html",
        conta=conta,
        receitas=receitas,
        clientes=clientes,
        origens=origens,
    )


@app.route("/contas-a-receber/delete/<int:id>", methods=["POST"])
@login_required
@permission_required("Financeiro", "Excluir")
def contas_a_receber_delete(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM contas_a_receber WHERE id = %s", (id,))
        conn.commit()
        flash("Conta excluída com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir conta: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("contas_a_receber_list"))


@app.route("/contas-a-pagar")
@login_required
@permission_required("Financeiro", "Consultar")
def contas_a_pagar_list():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    search_query = request.args.get("search", "")
    if search_query:
        cur.execute(
            """
            SELECT cp.*, p.razao_social_nome AS fornecedor, d.descricao AS despesa
            FROM contas_a_pagar cp
            JOIN pessoas p ON cp.fornecedor_id = p.id
            JOIN despesas_cadastro d ON cp.despesa_id = d.id
            WHERE p.razao_social_nome ILIKE %s OR d.descricao ILIKE %s
            ORDER BY cp.data_vencimento DESC
            """,
            (f"%{search_query}%", f"%{search_query}%"),
        )
    else:
        cur.execute(
            """
            SELECT cp.*, p.razao_social_nome AS fornecedor, d.descricao AS despesa
            FROM contas_a_pagar cp
            JOIN pessoas p ON cp.fornecedor_id = p.id
            JOIN despesas_cadastro d ON cp.despesa_id = d.id
            ORDER BY cp.data_vencimento DESC
            """
        )
    contas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "financeiro/contas_a_pagar/list.html",
        contas=contas,
        search_query=search_query,
    )


@app.route("/contas-a-pagar/add", methods=["GET", "POST"])
@login_required
@permission_required("Financeiro", "Incluir")
def contas_a_pagar_add():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == "POST":
        try:
            despesa_id = request.form["despesa_id"]
            fornecedor_id = request.form["fornecedor_id"]
            titulo = request.form["titulo"]
            data_vencimento = request.form["data_vencimento"]
            valor_previsto = request.form["valor_previsto"]
            data_pagamento = request.form.get("data_pagamento") or None
            valor_pago = request.form.get("valor_pago") or None
            valor_desconto = request.form.get("valor_desconto") or 0
            valor_multa = request.form.get("valor_multa") or 0
            valor_juros = request.form.get("valor_juros") or 0
            observacao = request.form.get("observacao")
            centro_custo = request.form.get("centro_custo")
            status_conta = request.form.get("status_conta")
            origem_id = request.form.get("origem_id") or None

            cur.execute(
                """
                INSERT INTO contas_a_pagar (
                    despesa_id, fornecedor_id, titulo, data_vencimento,
                    valor_previsto, data_pagamento, valor_pago, valor_desconto,
                    valor_multa, valor_juros, observacao, centro_custo,
                    status_conta, origem_id
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    despesa_id,
                    fornecedor_id,
                    titulo,
                    data_vencimento,
                    valor_previsto,
                    data_pagamento,
                    valor_pago,
                    valor_desconto,
                    valor_multa,
                    valor_juros,
                    observacao,
                    centro_custo,
                    status_conta,
                    origem_id,
                ),
            )
            conn.commit()
            flash("Conta a pagar cadastrada com sucesso!", "success")
            return redirect(url_for("contas_a_pagar_list"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar conta: {e}", "danger")
    cur.execute("SELECT id, descricao FROM despesas_cadastro ORDER BY descricao")
    despesas = cur.fetchall()
    cur.execute(
        "SELECT id, razao_social_nome FROM pessoas WHERE tipo = 'Fornecedor' ORDER BY razao_social_nome"
    )
    fornecedores = cur.fetchall()
    cur.execute("SELECT id, descricao FROM origens_cadastro ORDER BY descricao")
    origens = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "financeiro/contas_a_pagar/add_list.html",
        conta=request.form,
        despesas=despesas,
        fornecedores=fornecedores,
        origens=origens,
    )


@app.route("/contas-a-pagar/edit/<int:id>", methods=["GET", "POST"])
@login_required
@permission_required("Financeiro", "Editar")
def contas_a_pagar_edit(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == "POST":
        try:
            despesa_id = request.form["despesa_id"]
            fornecedor_id = request.form["fornecedor_id"]
            titulo = request.form["titulo"]
            data_vencimento = request.form["data_vencimento"]
            valor_previsto = request.form["valor_previsto"]
            data_pagamento = request.form.get("data_pagamento") or None
            valor_pago = request.form.get("valor_pago") or None
            valor_desconto = request.form.get("valor_desconto") or 0
            valor_multa = request.form.get("valor_multa") or 0
            valor_juros = request.form.get("valor_juros") or 0
            observacao = request.form.get("observacao")
            centro_custo = request.form.get("centro_custo")
            status_conta = request.form.get("status_conta")
            origem_id = request.form.get("origem_id") or None

            cur.execute(
                """
                UPDATE contas_a_pagar
                SET despesa_id=%s, fornecedor_id=%s, titulo=%s, data_vencimento=%s,
                    valor_previsto=%s, data_pagamento=%s, valor_pago=%s,
                    valor_desconto=%s, valor_multa=%s, valor_juros=%s,
                    observacao=%s, centro_custo=%s, status_conta=%s, origem_id=%s
                WHERE id=%s
                """,
                (
                    despesa_id,
                    fornecedor_id,
                    titulo,
                    data_vencimento,
                    valor_previsto,
                    data_pagamento,
                    valor_pago,
                    valor_desconto,
                    valor_multa,
                    valor_juros,
                    observacao,
                    centro_custo,
                    status_conta,
                    origem_id,
                    id,
                ),
            )
            conn.commit()
            flash("Conta a pagar atualizada com sucesso!", "success")
            return redirect(url_for("contas_a_pagar_list"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao atualizar conta: {e}", "danger")
    cur.execute("SELECT * FROM contas_a_pagar WHERE id = %s", (id,))
    conta = cur.fetchone()
    cur.execute("SELECT id, descricao FROM despesas_cadastro ORDER BY descricao")
    despesas = cur.fetchall()
    cur.execute(
        "SELECT id, razao_social_nome FROM pessoas WHERE tipo = 'Fornecedor' ORDER BY razao_social_nome"
    )
    fornecedores = cur.fetchall()
    cur.execute("SELECT id, descricao FROM origens_cadastro ORDER BY descricao")
    origens = cur.fetchall()
    cur.close()
    conn.close()
    if conta is None:
        flash("Conta não encontrada.", "danger")
        return redirect(url_for("contas_a_pagar_list"))
    return render_template(
        "financeiro/contas_a_pagar/add_list.html",
        conta=conta,
        despesas=despesas,
        fornecedores=fornecedores,
        origens=origens,
    )


@app.route("/contas-a-pagar/delete/<int:id>", methods=["POST"])
@login_required
@permission_required("Financeiro", "Excluir")
def contas_a_pagar_delete(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM contas_a_pagar WHERE id = %s", (id,))
        conn.commit()
        flash("Conta excluída com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir conta: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("contas_a_pagar_list"))


# --- Módulo Caixa e Banco ---

@app.route("/caixas")
@login_required
@permission_required("Financeiro", "Consultar")
def caixas_list():
    contas = ContaCaixa.query.all()
    return render_template("financeiro/caixas/list.html", contas=contas)


@app.route("/caixas/add", methods=["GET", "POST"])
@login_required
@permission_required("Financeiro", "Incluir")
def caixas_add():
    if request.method == "POST":
        nome = request.form["nome"]
        moeda = request.form.get("moeda", "BRL")
        saldo_inicial = request.form.get("saldo_inicial") or 0
        conta = ContaCaixa(
            nome=nome,
            moeda=moeda,
            saldo_inicial=saldo_inicial,
            saldo_atual=saldo_inicial,
        )
        db.session.add(conta)
        db.session.commit()
        flash("Caixa cadastrado com sucesso!", "success")
        return redirect(url_for("caixas_list"))
    return render_template(
        "financeiro/caixas/add_list.html",
        conta=request.form,
        action_url=url_for("caixas_add"),
    )


@app.route("/caixas/edit/<int:id>", methods=["GET", "POST"])
@login_required
@permission_required("Financeiro", "Editar")
def caixas_edit(id):
    conta = ContaCaixa.query.get_or_404(id)
    if request.method == "POST":
        conta.nome = request.form["nome"]
        conta.moeda = request.form.get("moeda", "BRL")
        conta.saldo_inicial = request.form.get("saldo_inicial") or 0
        db.session.commit()
        flash("Conta de caixa atualizada com sucesso!", "success")
        return redirect(url_for("caixas_list"))
    return render_template(
        "financeiro/caixas/add_list.html",
        conta=conta,
        action_url=url_for("caixas_edit", id=id),
    )


@app.route("/bancos")
@login_required
@permission_required("Financeiro", "Consultar")
def bancos_list():
    contas = ContaBanco.query.all()
    return render_template("financeiro/bancos/list.html", contas=contas)


@app.route("/bancos/add", methods=["GET", "POST"])
@login_required
@permission_required("Financeiro", "Incluir")
def bancos_add():
    if request.method == "POST":
        conta = ContaBanco(
            banco=request.form["banco"],
            nome_banco=request.form.get("nome_banco"),
            agencia=request.form["agencia"],
            conta=request.form["conta"],
            tipo=request.form.get("tipo"),
            convenio=request.form.get("convenio"),
            carteira=request.form.get("carteira"),
            variacao=request.form.get("variacao"),
            saldo_inicial=request.form.get("saldo_inicial") or 0,
            saldo_atual=request.form.get("saldo_inicial") or 0,
        )
        db.session.add(conta)
        db.session.commit()
        flash("Conta bancária cadastrada com sucesso!", "success")
        return redirect(url_for("bancos_list"))
    return render_template(
        "financeiro/bancos/add_list.html",
        conta=request.form,
        action_url=url_for("bancos_add"),
    )


@app.route("/bancos/edit/<int:id>", methods=["GET", "POST"])
@login_required
@permission_required("Financeiro", "Editar")
def bancos_edit(id):
    conta = ContaBanco.query.get_or_404(id)
    if request.method == "POST":
        conta.banco = request.form["banco"]
        conta.nome_banco = request.form.get("nome_banco")
        conta.agencia = request.form["agencia"]
        conta.conta = request.form["conta"]
        conta.tipo = request.form.get("tipo")
        conta.convenio = request.form.get("convenio")
        conta.carteira = request.form.get("carteira")
        conta.variacao = request.form.get("variacao")
        conta.saldo_inicial = request.form.get("saldo_inicial") or 0
        db.session.commit()
        flash("Conta bancária atualizada com sucesso!", "success")
        return redirect(url_for("bancos_list"))
    return render_template(
        "financeiro/bancos/add_list.html",
        conta=conta,
        action_url=url_for("bancos_edit", id=id),
    )


@app.route("/movimento/<tipo>/<int:conta_id>", methods=["GET", "POST"])
@login_required
@permission_required("Financeiro", "Incluir")
def movimento_novo(tipo, conta_id):
    conta = ContaCaixa.query.get(conta_id) if tipo == "caixa" else ContaBanco.query.get(conta_id)
    if not conta:
        flash("Conta não encontrada.", "danger")
        return redirect(url_for("caixas_list" if tipo == "caixa" else "bancos_list"))
    if request.method == "POST":
        data = {
            "conta_origem_id": conta_id,
            "conta_origem_tipo": tipo,
            "tipo": request.form["tipo"],
            "valor": request.form["valor"],
            "categoria": request.form.get("categoria"),
            "historico": request.form.get("historico"),
            "data_movimento": request.form.get("data_movimento") or datetime.today().date(),
        }
        if data["tipo"] == "saida":
            data["despesa_id"] = request.form.get("despesa_id") or None
        elif data["tipo"] == "entrada":
            data["receita_id"] = request.form.get("receita_id") or None
        criar_movimento(data)
        flash("Movimento registrado com sucesso!", "success")
        return redirect(url_for("caixas_list" if tipo == "caixa" else "bancos_list"))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT id, descricao FROM despesas_cadastro ORDER BY descricao")
    despesas = cur.fetchall()
    cur.execute("SELECT id, descricao FROM receitas_cadastro ORDER BY descricao")
    receitas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "financeiro/caixas/lancamento.html",
        conta=conta,
        tipo=tipo,
        despesas=despesas,
        receitas=receitas,
        date_today=datetime.today().date().isoformat(),
    )

@app.route("/lancamentos/novo", methods=["GET", "POST"])
@login_required
@permission_required("Financeiro", "Incluir")
def lancamentos_novo():
    contas_caixa = ContaCaixa.query.all()
    contas_banco = ContaBanco.query.all()
    if request.method == "POST":
        conta_tipo = request.form["conta_tipo"]
        conta_id = int(request.form["conta_id"])
        data = {
            "conta_origem_id": conta_id,
            "conta_origem_tipo": conta_tipo,
            "tipo": request.form["tipo"],
            "valor": request.form["valor"],
            "categoria": request.form.get("categoria"),
            "historico": request.form.get("historico"),
            "data_movimento": request.form.get("data_movimento") or datetime.today().date(),
        }
        if data["tipo"] == "saida":
            data["despesa_id"] = request.form.get("despesa_id") or None
        elif data["tipo"] == "entrada":
            data["receita_id"] = request.form.get("receita_id") or None
        criar_movimento(data)
        flash("Movimento registrado com sucesso!", "success")
        return redirect(url_for("lancamentos_novo"))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT id, descricao FROM despesas_cadastro ORDER BY descricao")
    despesas = cur.fetchall()
    cur.execute("SELECT id, descricao FROM receitas_cadastro ORDER BY descricao")
    receitas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "financeiro/lancamentos/add.html",
        contas_caixa=contas_caixa,
        contas_banco=contas_banco,
        despesas=despesas,
        receitas=receitas,
        date_today=datetime.today().date().isoformat(),
    )


@app.route("/bancos/importar/<int:conta_id>", methods=["POST"])
@login_required
@permission_required("Financeiro", "Incluir")
def banco_importar_cnab(conta_id):
    conta = ContaBanco.query.get(conta_id)
    if not conta:
        flash("Conta bancária não encontrada.", "danger")
        return redirect(url_for("bancos_list"))
    arquivo = request.files.get("arquivo")
    if not arquivo:
        flash("Selecione um arquivo CNAB.", "danger")
    else:
        resultados = importar_cnab(arquivo, conta_id, "banco")
        flash(f"{len(resultados)} lançamentos importados.", "success")
    return redirect(url_for("bancos_list"))


# --- Módulo de Administração do Sistema ---
@app.route("/admin/backup", methods=["GET", "POST"])
@login_required
@permission_required("Administracao Sistema", "Incluir") # Permissão para gerar backup
def backup_db():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    if request.method == "POST":
        backup_filename = request.form.get(
            "backup_filename",
            f"imobiliaria_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql",
        )
        backup_path = os.path.join(
            app.config["UPLOAD_FOLDER"], "backups", backup_filename
        )
        
        # Garante que o diretório de backups exista
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)

        try:
            # Extrai informações do DATABASE_URL para pg_dump
            # Ex: postgresql://user:password@host:port/dbname
            db_url_parts = DATABASE_URL.split("://")[1].split("@")
            user_pass = db_url_parts[0].split(":")
            host_port_db = db_url_parts[1].split("/")
            
            db_user = user_pass[0]
            db_password = user_pass[1] if len(user_pass) > 1 else ""
            db_host = host_port_db[0].split(":")[0]
            db_port = (
                host_port_db[0].split(":")[1]
                if len(host_port_db[0].split(":")) > 1
                else "5433"
            )
            db_name = host_port_db[1]

            # Comando pg_dump
            # Atenção: O pg_dump precisa estar no PATH do sistema onde o Flask está rodando.
            # Em produção, considere um método mais robusto e seguro para backups.
            command = [
                "pg_dump",
                "-h",
                db_host,
                "-p",
                db_port,
                "-U",
                db_user,
                "-F",
                "p",  # Formato plain-text SQL
                "-f",
                backup_path,
                db_name,
            ]
            
            # Define a variável de ambiente PGPASSWORD para pg_dump
            env = os.environ.copy()
            env["PGPASSWORD"] = db_password

            # Executa o comando
            result = subprocess.run(command, capture_output=True, text=True, env=env)

            if result.returncode == 0:
                status = "Sucesso"
                message = "Backup gerado com sucesso!"
                flash(message, "success")
            else:
                status = "Falha"
                message = f"Erro ao gerar backup: {result.stderr}"
                flash(message, "danger")
            
            # Registra no histórico
            cur.execute(
                "INSERT INTO historico_backups (data_backup, nome_arquivo, caminho_arquivo, status_backup, observacao, usuario_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    datetime.now(),
                    backup_filename,
                    backup_path,
                    status,
                    message,
                    session["user_id"],
                ),
            )
            conn.commit()

        except Exception as e:
            conn.rollback()
            status = "Falha"
            message = f"Erro inesperado ao gerar backup: {e}"
            flash(message, "danger")
            cur.execute(
                "INSERT INTO historico_backups (data_backup, nome_arquivo, caminho_arquivo, status_backup, observacao, usuario_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    datetime.now(),
                    backup_filename,
                    backup_path,
                    status,
                    message,
                    session["user_id"],
                ),
            )
            conn.commit()
        
    # Carrega histórico de backups
    cur.execute("SELECT * FROM historico_backups ORDER BY data_backup DESC")
    historico = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("admin/backup.html", historico=historico)


@app.route("/admin/backup/restore", methods=["POST"])
@login_required
@permission_required(
    "Administracao Sistema", "Bloquear"
)  # Ação de restaurar é mais restritiva
def restore_db():
    if request.method == "POST":
        backup_id = request.form.get("backup_id")
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        cur.execute(
            "SELECT caminho_arquivo FROM historico_backups WHERE id = %s", (backup_id,)
        )
        backup_record = cur.fetchone()
        cur.close()
        conn.close()

        if not backup_record:
            flash("Backup não encontrado.", "danger")
            return redirect(url_for("backup_db"))

        backup_path = backup_record["caminho_arquivo"]

        try:
            # Extrai informações do DATABASE_URL para psql
            db_url_parts = DATABASE_URL.split("://")[1].split("@")
            user_pass = db_url_parts[0].split(":")
            host_port_db = db_url_parts[1].split("/")
            
            db_user = user_pass[0]
            db_password = user_pass[1] if len(user_pass) > 1 else ""
            db_host = host_port_db[0].split(":")[0]
            db_port = (
                host_port_db[0].split(":")[1]
                if len(host_port_db[0].split(":")) > 1
                else "5433"
            )
            db_name = host_port_db[1]

            # Comando psql para restaurar
            # Atenção: Isso irá apagar e recriar o banco de dados. Tenha certeza do que está fazendo.
            # Para restaurar, o banco de dados não pode ter conexões ativas.
            # Em um cenário real, você precisaria de um script mais complexo para desconectar usuários,
            # dropar o banco, recriar e então restaurar.
            # Este é um exemplo simplificado.
            command = [
                "psql",
                "-h",
                db_host,
                "-p",
                db_port,
                "-U",
                db_user,
                "-d",
                db_name,
                "-f",
                backup_path,
            ]

            env = os.environ.copy()
            env["PGPASSWORD"] = db_password

            result = subprocess.run(command, capture_output=True, text=True, env=env)

            if result.returncode == 0:
                flash("Banco de dados restaurado com sucesso!", "success")
            else:
                flash(f"Erro ao restaurar banco de dados: {result.stderr}", "danger")

        except Exception as e:
            flash(f"Erro inesperado ao restaurar banco de dados: {e}", "danger")
    
    return redirect(url_for("backup_db"))


@app.route("/usuarios")
@login_required
@permission_required("Administracao Sistema", "Consultar")
def usuarios_list():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM usuarios ORDER BY id")
    usuarios = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("admin/usuarios/list.html", usuarios=usuarios)


@app.route("/usuarios/add", methods=["GET", "POST"])
@login_required
@permission_required("Administracao Sistema", "Incluir")
def usuarios_add():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        tipo = request.form.get("tipo_usuario", "Operador")
        status = request.form.get("status", "Ativo")

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO usuarios (nome_usuario, senha_hash, tipo_usuario, status) VALUES (%s, %s, %s, %s)",
                (username, hashed_password, tipo, status),
            )
            conn.commit()
            flash("Usuário cadastrado com sucesso!", "success")
            return redirect(url_for("usuarios_list"))
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            flash("Nome de usuário já existe.", "danger")
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar usuário: {e}", "danger")
        finally:
            cur.close()
            conn.close()
    return render_template("admin/usuarios/add_list.html", usuario={})


@app.route("/usuarios/edit/<int:id>", methods=["GET", "POST"])
@login_required
@permission_required("Administracao Sistema", "Editar")
def usuarios_edit(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == "POST":
        username = request.form["username"]
        password = request.form.get("password")
        tipo = request.form.get("tipo_usuario")
        status = request.form.get("status")
        try:
            if password:
                hashed_password = generate_password_hash(password)
                cur.execute(
                    "UPDATE usuarios SET nome_usuario = %s, senha_hash = %s, tipo_usuario = %s, status = %s WHERE id = %s",
                    (username, hashed_password, tipo, status, id),
                )
            else:
                cur.execute(
                    "UPDATE usuarios SET nome_usuario = %s, tipo_usuario = %s, status = %s WHERE id = %s",
                    (username, tipo, status, id),
                )
            conn.commit()
            flash("Usuário atualizado com sucesso!", "success")
            return redirect(url_for("usuarios_list"))
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            flash("Nome de usuário já existe.", "danger")
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao atualizar usuário: {e}", "danger")
    cur.execute("SELECT * FROM usuarios WHERE id = %s", (id,))
    usuario = cur.fetchone()
    cur.close()
    conn.close()
    if usuario is None:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for("usuarios_list"))
    return render_template("admin/usuarios/add_list.html", usuario=usuario)


@app.route("/usuarios/delete/<int:id>", methods=["POST"])
@login_required
@permission_required("Administracao Sistema", "Excluir")
def usuarios_delete(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM usuarios WHERE id = %s", (id,))
        conn.commit()
        flash("Usuário excluído com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir usuário: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("usuarios_list"))


@app.route("/usuarios/permissoes/<int:id>", methods=["GET", "POST"])
@login_required
@permission_required("Administracao Sistema", "Editar")
def usuarios_permissoes(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == "POST":
        cur.execute("DELETE FROM permissoes WHERE usuario_id = %s", (id,))
        for module in MODULES:
            for action in ACTIONS:
                field = f"{module}:{action}"
                if request.form.get(field):
                    cur.execute(
                        "INSERT INTO permissoes (usuario_id, modulo, acao) VALUES (%s, %s, %s)",
                        (id, module, action),
                    )
        conn.commit()
        flash("Permissões atualizadas com sucesso!", "success")

    cur.execute("SELECT modulo, acao FROM permissoes WHERE usuario_id = %s", (id,))
    existing = {(row["modulo"], row["acao"]) for row in cur.fetchall()}
    cur.execute("SELECT * FROM usuarios WHERE id = %s", (id,))
    usuario = cur.fetchone()
    cur.close()
    conn.close()
    if usuario is None:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for("usuarios_list"))
    return render_template(
        "admin/usuarios/permissoes.html",
        usuario=usuario,
        existing=existing,
        modules=MODULES,
        actions=ACTIONS,
    )


@app.route("/empresa")
@login_required
@permission_required("Administracao Sistema", "Consultar")
def empresa_list():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    search_query = request.args.get("search", "")
    if search_query:
        cur.execute(
            """
            SELECT * FROM empresa_licenciada
            WHERE documento ILIKE %s OR razao_social_nome ILIKE %s OR nome_fantasia ILIKE %s
            ORDER BY data_cadastro DESC
        """,
            (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"),
        )
    else:
        cur.execute("SELECT * FROM empresa_licenciada ORDER BY data_cadastro DESC")
    empresas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "admin/empresa/list.html", empresas=empresas, search_query=search_query
    )


@app.route("/empresa/add", methods=["GET", "POST"])
@login_required
@permission_required("Administracao Sistema", "Incluir")
def empresa_add():
    if request.method == "POST":
        try:
            documento = (
                request.form["documento"].replace(".", "").replace("/", "").replace("-", "")
            )
            razao_social_nome = request.form["razao_social_nome"]
            nome_fantasia = request.form.get("nome_fantasia")
            endereco = request.form.get("endereco")
            bairro = request.form.get("bairro")
            cidade = request.form.get("cidade")
            estado = request.form.get("estado")
            cep = request.form.get("cep", "").replace("-", "")
            telefone = request.form.get("telefone")
            observacao = request.form.get("observacao")
            status = request.form["status"]

            if len(documento) == 11 and not documento.isdigit():
                flash("CPF inválido. Deve conter apenas números.", "danger")
                return render_template("admin/empresa/add_list.html", empresa=request.form)
            elif len(documento) == 14 and not documento.isdigit():
                flash("CNPJ inválido. Deve conter apenas números.", "danger")
                return render_template("admin/empresa/add_list.html", empresa=request.form)
            elif len(documento) != 11 and len(documento) != 14:
                flash(
                    "Documento deve ser um CPF (11 dígitos) ou CNPJ (14 dígitos).",
                    "danger",
                )
                return render_template("admin/empresa/add_list.html", empresa=request.form)

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO empresa_licenciada (documento, razao_social_nome, nome_fantasia, endereco, bairro, cidade, estado, cep, telefone, observacao, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
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
                    observacao,
                    status,
                ),
            )
            conn.commit()
            cur.close()
            conn.close()
            flash("Empresa cadastrada com sucesso!", "success")
            return redirect(url_for("empresa_list"))
        except psycopg2.errors.UniqueViolation:
            flash("Erro: Documento (CNPJ/CPF) já cadastrado.", "danger")
            conn.rollback()
            return render_template("admin/empresa/add_list.html", empresa=request.form)
        except Exception as e:
            flash(f"Erro ao cadastrar empresa: {e}", "danger")
            return render_template("admin/empresa/add_list.html", empresa=request.form)
    return render_template("admin/empresa/add_list.html", empresa={})


@app.route("/empresa/edit/<int:id>", methods=["GET", "POST"])
@login_required
@permission_required("Administracao Sistema", "Editar")
def empresa_edit(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == "POST":
        try:
            documento = (
                request.form["documento"].replace(".", "").replace("/", "").replace("-", "")
            )
            razao_social_nome = request.form["razao_social_nome"]
            nome_fantasia = request.form.get("nome_fantasia")
            endereco = request.form.get("endereco")
            bairro = request.form.get("bairro")
            cidade = request.form.get("cidade")
            estado = request.form.get("estado")
            cep = request.form.get("cep", "").replace("-", "")
            telefone = request.form.get("telefone")
            observacao = request.form.get("observacao")
            status = request.form["status"]

            if len(documento) == 11 and not documento.isdigit():
                flash("CPF inválido. Deve conter apenas números.", "danger")
                cur.execute("SELECT * FROM empresa_licenciada WHERE id = %s", (id,))
                empresa = cur.fetchone()
                return render_template("admin/empresa/add_list.html", empresa=empresa)
            elif len(documento) == 14 and not documento.isdigit():
                flash("CNPJ inválido. Deve conter apenas números.", "danger")
                cur.execute("SELECT * FROM empresa_licenciada WHERE id = %s", (id,))
                empresa = cur.fetchone()
                return render_template("admin/empresa/add_list.html", empresa=empresa)
            elif len(documento) != 11 and len(documento) != 14:
                flash(
                    "Documento deve ser um CPF (11 dígitos) ou CNPJ (14 dígitos).",
                    "danger",
                )
                cur.execute("SELECT * FROM empresa_licenciada WHERE id = %s", (id,))
                empresa = cur.fetchone()
                return render_template("admin/empresa/add_list.html", empresa=empresa)

            cur.execute(
                """
                UPDATE empresa_licenciada
                SET documento = %s, razao_social_nome = %s, nome_fantasia = %s, endereco = %s, bairro = %s, cidade = %s, estado = %s, cep = %s, telefone = %s, observacao = %s, status = %s
                WHERE id = %s
                """,
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
                    observacao,
                    status,
                    id,
                ),
            )
            conn.commit()
            flash("Empresa atualizada com sucesso!", "success")
            return redirect(url_for("empresa_list"))
        except psycopg2.errors.UniqueViolation:
            flash("Erro: Documento (CNPJ/CPF) já cadastrado para outra empresa.", "danger")
            conn.rollback()
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao atualizar empresa: {e}", "danger")
        cur.execute("SELECT * FROM empresa_licenciada WHERE id = %s", (id,))
        empresa = cur.fetchone()
        cur.close()
        conn.close()
        if empresa is None:
            flash("Empresa não encontrada.", "danger")
            return redirect(url_for("empresa_list"))
        return render_template("admin/empresa/add_list.html", empresa=empresa)

    cur.execute("SELECT * FROM empresa_licenciada WHERE id = %s", (id,))
    empresa = cur.fetchone()
    cur.close()
    conn.close()
    if empresa is None:
        flash("Empresa não encontrada.", "danger")
        return redirect(url_for("empresa_list"))
    return render_template("admin/empresa/add_list.html", empresa=empresa)


@app.route("/empresa/delete/<int:id>", methods=["POST"])
@login_required
@permission_required("Administracao Sistema", "Excluir")
def empresa_delete(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM empresa_licenciada WHERE id = %s", (id,))
        conn.commit()
        flash("Empresa excluída com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir empresa: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("empresa_list"))

# --- Execução da Aplicação ---
if __name__ == "__main__":
    app.run(debug=True) # Mude debug para False em produção