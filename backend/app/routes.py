import os
from flask import Blueprint, jsonify, request, send_from_directory
from flask_jwt_extended import create_access_token, jwt_required

from .models import db, Person, Imovel, Usuario
from .utils import validate_cpf_cnpj, hash_password, check_password

bp = Blueprint('api', __name__)
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'frontend'))


@bp.get('/')
def index():
    """Serve the login page."""
    return send_from_directory(FRONTEND_DIR, 'index.html')


@bp.get('/home')
def home_page():
    """Serve the home page."""
    return send_from_directory(FRONTEND_DIR, 'home.html')


@bp.post('/login')
def login():
    data = request.json
    user = Usuario.query.filter_by(nome=data.get('username')).first()
    if user and check_password(data.get('password'), user.senha_hash):
        token = create_access_token(identity={'id': user.id, 'role': user.role})
        return jsonify(access_token=token)
    return jsonify({'msg': 'Bad credentials'}), 401


@bp.post('/persons')
@jwt_required()
def create_person():
    data = request.json
    if not validate_cpf_cnpj(data['cpf_cnpj']):
        return jsonify({'msg': 'CPF/CNPJ inválido'}), 400
    person = Person(**data)
    db.session.add(person)
    db.session.commit()
    return jsonify({'id': person.id})


@bp.get('/imoveis')
@jwt_required()
def list_imoveis():
    imoveis = Imovel.query.all()
    return jsonify([{'id': i.id, 'endereco': i.endereco} for i in imoveis])