ALTER TABLE pessoas
    ADD COLUMN IF NOT EXISTS responsavel_nome VARCHAR(255),
    ADD COLUMN IF NOT EXISTS responsavel_cpf VARCHAR(14),
    ADD COLUMN IF NOT EXISTS responsavel_endereco VARCHAR(255),
    ADD COLUMN IF NOT EXISTS responsavel_bairro VARCHAR(100),
    ADD COLUMN IF NOT EXISTS responsavel_cidade VARCHAR(100),
    ADD COLUMN IF NOT EXISTS responsavel_estado VARCHAR(100),
    ADD COLUMN IF NOT EXISTS responsavel_uf CHAR(2),
    ADD COLUMN IF NOT EXISTS responsavel_estado_civil VARCHAR(50);
