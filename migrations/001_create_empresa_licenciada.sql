CREATE TABLE IF NOT EXISTS empresa_licenciada (
    id SERIAL PRIMARY KEY,
    documento VARCHAR(20) UNIQUE NOT NULL,
    razao_social_nome VARCHAR(255) NOT NULL,
    nome_fantasia VARCHAR(255),
    endereco VARCHAR(255),
    bairro VARCHAR(100),
    cidade VARCHAR(100),
    estado CHAR(2),
    cep VARCHAR(10),
    telefone VARCHAR(20),
    observacao TEXT,
    status VARCHAR(10) NOT NULL DEFAULT 'Ativo',
    data_cadastro TIMESTAMP NOT NULL DEFAULT NOW()
);