-- Cria tabela de modelos de contrato (templates em HTML com placeholders)
CREATE TABLE IF NOT EXISTS contrato_modelos (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(150) NOT NULL,
    conteudo_html TEXT NOT NULL,
    data_cadastro TIMESTAMP NOT NULL DEFAULT NOW(),
    data_atualizacao TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Trigger para atualizar data_atualizacao em updates (opcional)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_contrato_modelos_updated_at'
    ) THEN
        CREATE OR REPLACE FUNCTION set_contrato_modelos_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.data_atualizacao := NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_contrato_modelos_updated_at
        BEFORE UPDATE ON contrato_modelos
        FOR EACH ROW EXECUTE FUNCTION set_contrato_modelos_updated_at();
    END IF;
END $$;

