# app.py
# Este é o arquivo principal da sua aplicação Flask.

from flask import Flask, render_template, request, redirect, url_for, session, flash
import psycopg2
from psycopg2 import extras
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import subprocess
import json

# Importa a configuração do banco de dados e outras variáveis
from config import DATABASE_URL, SECRET_KEY, UPLOAD_FOLDER, ALLOWED_EXTENSIONS

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Cria a pasta de uploads se ela não existir
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Função para conectar ao banco de dados
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# Decorador para verificar se o usuário está logado
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Você precisa estar logado para acessar esta página.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Decorador para verificar permissões
def permission_required(module, action):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Você precisa estar logado para acessar esta página.', 'warning')
                return redirect(url_for('login'))

            user_id = session['user_id']
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Verifica se o usuário é Master (tem acesso total)
            cur.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (user_id,))
            user = cur.fetchone()
            if user and user['tipo_usuario'] == 'Master':
                cur.close()
                conn.close()
                return f(*args, **kwargs)

            # Verifica permissões específicas para o módulo e ação
            cur.execute("""
                SELECT COUNT(*) FROM permissoes
                WHERE usuario_id = %s AND modulo = %s AND acao = %s
            """, (user_id, module, action))
            has_permission = cur.fetchone()[0] > 0
            
            cur.close()
            conn.close()

            if not has_permission:
                flash(f'Você não tem permissão para realizar esta ação no módulo {module}.', 'danger')
                return redirect(url_for('dashboard')) # Ou outra página de erro/acesso negado
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Rotas de Autenticação ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT id, nome_usuario, senha_hash, status FROM usuarios WHERE nome_usuario = %s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and user['status'] == 'Ativo' and check_password_hash(user['senha_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['nome_usuario']
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Usuário ou senha inválidos, ou usuário inativo.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))

# --- Rota Principal ---
@app.route('/')
@login_required
def dashboard():
    # Aqui você pode adicionar lógica para exibir dados do dashboard
    return render_template('dashboard.html')

# --- Módulo de Cadastros Essenciais ---

# 1.1. Cadastro de Fornecedores e Clientes (Pessoas)
@app.route('/pessoas')
@login_required
@permission_required('Cadastro Fornecedores/Clientes', 'Consultar')
def pessoas_list():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    search_query = request.args.get('search', '')
    if search_query:
        cur.execute("""
            SELECT * FROM pessoas
            WHERE documento ILIKE %s OR razao_social_nome ILIKE %s OR nome_fantasia ILIKE %s
            ORDER BY data_cadastro DESC
        """, (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
    else:
        cur.execute("SELECT * FROM pessoas ORDER BY data_cadastro DESC")
    pessoas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('pessoas/list.html', pessoas=pessoas, search_query=search_query)

@app.route('/pessoas/add', methods=['GET', 'POST'])
@login_required
@permission_required('Cadastro Fornecedores/Clientes', 'Incluir')
def pessoas_add():
    if request.method == 'POST':
        try:
            documento = request.form['documento'].replace('.', '').replace('/', '').replace('-', '')
            razao_social_nome = request.form['razao_social_nome']
            nome_fantasia = request.form.get('nome_fantasia')
            endereco = request.form.get('endereco')
            bairro = request.form.get('bairro')
            cidade = request.form.get('cidade')
            estado = request.form.get('estado')
            cep = request.form.get('cep', '').replace('-', '')
            telefone = request.form.get('telefone')
            observacao = request.form.get('observacao')
            tipo = request.form['tipo']
            status = request.form['status']

            # Validação de CPF/CNPJ (simplificada, você precisaria de uma biblioteca real como 'validate-docbr')
            if len(documento) == 11 and not documento.isdigit():
                 flash('CPF inválido. Deve conter apenas números.', 'danger')
                 return render_template('pessoas/add_edit.html', pessoa={})
            elif len(documento) == 14 and not documento.isdigit():
                 flash('CNPJ inválido. Deve conter apenas números.', 'danger')
                 return render_template('pessoas/add_edit.html', pessoa={})
            elif len(documento) != 11 and len(documento) != 14:
                flash('Documento deve ser um CPF (11 dígitos) ou CNPJ (14 dígitos).', 'danger')
                return render_template('pessoas/add_edit.html', pessoa={})
            
            # Exemplo de uso de validate-docbr (necessita instalação: pip install validate-docbr)
            # from validate_docbr import CPF, CNPJ
            # if len(documento) == 11:
            #     if not CPF().validate(documento):
            #         flash('CPF inválido.', 'danger')
            #         return render_template('pessoas/add_edit.html', pessoa={})
            # elif len(documento) == 14:
            #     if not CNPJ().validate(documento):
            #         flash('CNPJ inválido.', 'danger')
            #         return render_template('pessoas/add_edit.html', pessoa={})

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO pessoas (documento, razao_social_nome, nome_fantasia, endereco, bairro, cidade, estado, cep, telefone, observacao, tipo, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (documento, razao_social_nome, nome_fantasia, endereco, bairro, cidade, estado, cep, telefone, observacao, tipo, status)
            )
            conn.commit()
            cur.close()
            conn.close()
            flash('Pessoa cadastrada com sucesso!', 'success')
            return redirect(url_for('pessoas_list'))
        except psycopg2.errors.UniqueViolation:
            flash('Erro: Documento (CPF/CNPJ) já cadastrado.', 'danger')
            conn.rollback() # Garante que a transação seja desfeita em caso de erro
            return render_template('pessoas/add_edit.html', pessoa=request.form)
        except Exception as e:
            flash(f'Erro ao cadastrar pessoa: {e}', 'danger')
            return render_template('pessoas/add_edit.html', pessoa=request.form)
    return render_template('pessoas/add_edit.html', pessoa={})

@app.route('/pessoas/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('Cadastro Fornecedores/Clientes', 'Editar')
def pessoas_edit(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == 'POST':
        try:
            documento = request.form['documento'].replace('.', '').replace('/', '').replace('-', '')
            razao_social_nome = request.form['razao_social_nome']
            nome_fantasia = request.form.get('nome_fantasia')
            endereco = request.form.get('endereco')
            bairro = request.form.get('bairro')
            cidade = request.form.get('cidade')
            estado = request.form.get('estado')
            cep = request.form.get('cep', '').replace('-', '')
            telefone = request.form.get('telefone')
            observacao = request.form.get('observacao')
            tipo = request.form['tipo']
            status = request.form['status']

            # Validação de CPF/CNPJ (simplificada)
            if len(documento) == 11 and not documento.isdigit():
                 flash('CPF inválido. Deve conter apenas números.', 'danger')
                 return render_template('pessoas/add_edit.html', pessoa=request.form)
            elif len(documento) == 14 and not documento.isdigit():
                 flash('CNPJ inválido. Deve conter apenas números.', 'danger')
                 return render_template('pessoas/add_edit.html', pessoa=request.form)
            elif len(documento) != 11 and len(documento) != 14:
                flash('Documento deve ser um CPF (11 dígitos) ou CNPJ (14 dígitos).', 'danger')
                return render_template('pessoas/add_edit.html', pessoa={})

            cur.execute(
                """
                UPDATE pessoas
                SET documento = %s, razao_social_nome = %s, nome_fantasia = %s, endereco = %s, bairro = %s, cidade = %s, estado = %s, cep = %s, telefone = %s, observacao = %s, tipo = %s, status = %s
                WHERE id = %s
                """,
                (documento, razao_social_nome, nome_fantasia, endereco, bairro, cidade, estado, cep, telefone, observacao, tipo, status, id)
            )
            conn.commit()
            flash('Pessoa atualizada com sucesso!', 'success')
            return redirect(url_for('pessoas_list'))
        except psycopg2.errors.UniqueViolation:
            flash('Erro: Documento (CPF/CNPJ) já cadastrado para outra pessoa.', 'danger')
            conn.rollback()
            # Recarrega os dados da pessoa para preencher o formulário novamente
            cur.execute("SELECT * FROM pessoas WHERE id = %s", (id,))
            pessoa = cur.fetchone()
            return render_template('pessoas/add_edit.html', pessoa=pessoa)
        except Exception as e:
            flash(f'Erro ao atualizar pessoa: {e}', 'danger')
            # Recarrega os dados da pessoa para preencher o formulário novamente
            cur.execute("SELECT * FROM pessoas WHERE id = %s", (id,))
            pessoa = cur.fetchone()
            return render_template('pessoas/add_edit.html', pessoa=pessoa)
    
    cur.execute("SELECT * FROM pessoas WHERE id = %s", (id,))
    pessoa = cur.fetchone()
    cur.close()
    conn.close()
    if pessoa is None:
        flash('Pessoa não encontrada.', 'danger')
        return redirect(url_for('pessoas_list'))
    return render_template('pessoas/add_edit.html', pessoa=pessoa)

@app.route('/pessoas/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('Cadastro Fornecedores/Clientes', 'Excluir')
def pessoas_delete(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM pessoas WHERE id = %s", (id,))
        conn.commit()
        flash('Pessoa excluída com sucesso!', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Erro ao excluir pessoa: {e}', 'danger')
    finally:
        cur.close()
        conn.close()
    return redirect(url_for('pessoas_list'))

# --- Módulo de Administração do Sistema (Exemplo de Backup) ---
@app.route('/admin/backup', methods=['GET', 'POST'])
@login_required
@permission_required('Administracao Sistema', 'Incluir') # Permissão para gerar backup
def backup_db():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    if request.method == 'POST':
        backup_filename = request.form.get('backup_filename', f"imobiliaria_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql")
        backup_path = os.path.join(app.config['UPLOAD_FOLDER'], 'backups', backup_filename)
        
        # Garante que o diretório de backups exista
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)

        try:
            # Extrai informações do DATABASE_URL para pg_dump
            # Ex: postgresql://user:password@host:port/dbname
            db_url_parts = DATABASE_URL.split('://')[1].split('@')
            user_pass = db_url_parts[0].split(':')
            host_port_db = db_url_parts[1].split('/')
            
            db_user = user_pass[0]
            db_password = user_pass[1] if len(user_pass) > 1 else ''
            db_host = host_port_db[0].split(':')[0]
            db_port = host_port_db[0].split(':')[1] if len(host_port_db[0].split(':')) > 1 else '5432'
            db_name = host_port_db[1]

            # Comando pg_dump
            # Atenção: O pg_dump precisa estar no PATH do sistema onde o Flask está rodando.
            # Em produção, considere um método mais robusto e seguro para backups.
            command = [
                'pg_dump',
                '-h', db_host,
                '-p', db_port,
                '-U', db_user,
                '-F', 'p', # Formato plain-text SQL
                '-f', backup_path,
                db_name
            ]
            
            # Define a variável de ambiente PGPASSWORD para pg_dump
            env = os.environ.copy()
            env['PGPASSWORD'] = db_password

            # Executa o comando
            result = subprocess.run(command, capture_output=True, text=True, env=env)

            if result.returncode == 0:
                status = 'Sucesso'
                message = 'Backup gerado com sucesso!'
                flash(message, 'success')
            else:
                status = 'Falha'
                message = f'Erro ao gerar backup: {result.stderr}'
                flash(message, 'danger')
            
            # Registra no histórico
            cur.execute(
                "INSERT INTO historico_backups (data_backup, nome_arquivo, caminho_arquivo, status_backup, observacao, usuario_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (datetime.now(), backup_filename, backup_path, status, message, session['user_id'])
            )
            conn.commit()

        except Exception as e:
            conn.rollback()
            status = 'Falha'
            message = f'Erro inesperado ao gerar backup: {e}'
            flash(message, 'danger')
            cur.execute(
                "INSERT INTO historico_backups (data_backup, nome_arquivo, caminho_arquivo, status_backup, observacao, usuario_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (datetime.now(), backup_filename, backup_path, status, message, session['user_id'])
            )
            conn.commit()
        
    # Carrega histórico de backups
    cur.execute("SELECT * FROM historico_backups ORDER BY data_backup DESC")
    historico = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin/backup.html', historico=historico)

@app.route('/admin/backup/restore', methods=['POST'])
@login_required
@permission_required('Administracao Sistema', 'Bloquear') # Ação de restaurar é mais restritiva
def restore_db():
    if request.method == 'POST':
        backup_id = request.form.get('backup_id')
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        cur.execute("SELECT caminho_arquivo FROM historico_backups WHERE id = %s", (backup_id,))
        backup_record = cur.fetchone()
        cur.close()
        conn.close()

        if not backup_record:
            flash('Backup não encontrado.', 'danger')
            return redirect(url_for('backup_db'))

        backup_path = backup_record['caminho_arquivo']
        
        try:
            # Extrai informações do DATABASE_URL para psql
            db_url_parts = DATABASE_URL.split('://')[1].split('@')
            user_pass = db_url_parts[0].split(':')
            host_port_db = db_url_parts[1].split('/')
            
            db_user = user_pass[0]
            db_password = user_pass[1] if len(user_pass) > 1 else ''
            db_host = host_port_db[0].split(':')[0]
            db_port = host_port_db[0].split(':')[1] if len(host_port_db[0].split(':')) > 1 else '5432'
            db_name = host_port_db[1]

            # Comando psql para restaurar
            # Atenção: Isso irá apagar e recriar o banco de dados. Tenha certeza do que está fazendo.
            # Para restaurar, o banco de dados não pode ter conexões ativas.
            # Em um cenário real, você precisaria de um script mais complexo para desconectar usuários,
            # dropar o banco, recriar e então restaurar.
            # Este é um exemplo simplificado.
            command = [
                'psql',
                '-h', db_host,
                '-p', db_port,
                '-U', db_user,
                '-d', db_name,
                '-f', backup_path
            ]

            env = os.environ.copy()
            env['PGPASSWORD'] = db_password

            result = subprocess.run(command, capture_output=True, text=True, env=env)

            if result.returncode == 0:
                flash('Banco de dados restaurado com sucesso!', 'success')
            else:
                flash(f'Erro ao restaurar banco de dados: {result.stderr}', 'danger')

        except Exception as e:
            flash(f'Erro inesperado ao restaurar banco de dados: {e}', 'danger')
    
    return redirect(url_for('backup_db'))


# --- Rotas para outros módulos (apenas placeholders) ---
@app.route('/imoveis')
@login_required
@permission_required('Cadastro Imoveis', 'Consultar')
def imoveis_list():
    # Lógica para listar imóveis
    return render_template('imoveis/list.html')

@app.route('/contratos')
@login_required
@permission_required('Gestao Contratos', 'Consultar')
def contratos_list():
    # Lógica para listar contratos
    return render_template('contratos/list.html')

@app.route('/contas-a-receber')
@login_required
@permission_required('Financeiro', 'Consultar')
def contas_a_receber_list():
    # Lógica para listar contas a receber
    return render_template('financeiro/contas_a_receber.html')

@app.route('/contas-a-pagar')
@login_required
@permission_required('Financeiro', 'Consultar')
def contas_a_pagar_list():
    # Lógica para listar contas a pagar
    return render_template('financeiro/contas_a_pagar.html')

@app.route('/usuarios')
@login_required
@permission_required('Administracao Sistema', 'Consultar')
def usuarios_list():
    # Lógica para listar usuários
    return render_template('admin/usuarios.html')

@app.route('/empresa')
@login_required
@permission_required('Administracao Sistema', 'Consultar')
def empresa_licenciada():
    # Lógica para gerenciar dados da empresa licenciada
    return render_template('admin/empresa.html')

# --- Execução da Aplicação ---
if __name__ == '__main__':
    app.run(debug=True) # Mude debug para False em produção