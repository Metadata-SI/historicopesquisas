-- ==============================================================================
-- Esquema PostgreSQL: Agregador de Pesquisas Eleitorais 2026
-- Para migração direta de SQLite para PostgreSQL / Supabase / RDS
-- ==============================================================================

CREATE TABLE IF NOT EXISTS instituto (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL UNIQUE,
    peso DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    vies_historico DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    criado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pesquisa (
    id SERIAL PRIMARY KEY,
    instituto_id INTEGER NOT NULL REFERENCES instituto(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    registro_tse VARCHAR(50) NOT NULL UNIQUE,
    uf VARCHAR(2) NOT NULL DEFAULT 'BR',
    cargo VARCHAR(50) NOT NULL DEFAULT 'Presidente',
    data_inicio DATE NOT NULL,
    data_fim DATE NOT NULL,
    data_divulgacao DATE,
    amostra INTEGER NOT NULL CHECK (amostra > 0),
    margem_erro DOUBLE PRECISION CHECK (margem_erro >= 0),
    metodologia TEXT,
    impugnada BOOLEAN NOT NULL DEFAULT FALSE,
    observacoes TEXT,
    criado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cenario (
    id SERIAL PRIMARY KEY,
    pesquisa_id INTEGER NOT NULL REFERENCES pesquisa(id) ON UPDATE CASCADE ON DELETE CASCADE,
    turno SMALLINT NOT NULL DEFAULT 1 CHECK (turno IN (1, 2)),
    cenario VARCHAR(100) NOT NULL,
    descricao TEXT,
    UNIQUE(pesquisa_id, turno, cenario)
);

CREATE TABLE IF NOT EXISTS resultado (
    id SERIAL PRIMARY KEY,
    cenario_id INTEGER NOT NULL REFERENCES cenario(id) ON UPDATE CASCADE ON DELETE CASCADE,
    candidato VARCHAR(100) NOT NULL,
    percentual DOUBLE PRECISION NOT NULL CHECK (percentual >= 0.0 AND percentual <= 100.0),
    UNIQUE(cenario_id, candidato)
);

CREATE TABLE IF NOT EXISTS fonte (
    id SERIAL PRIMARY KEY,
    pesquisa_id INTEGER NOT NULL REFERENCES pesquisa(id) ON UPDATE CASCADE ON DELETE CASCADE,
    url TEXT NOT NULL,
    portal VARCHAR(50) NOT NULL,
    data_coleta TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(pesquisa_id, url)
);

CREATE TABLE IF NOT EXISTS quarentena (
    id SERIAL PRIMARY KEY,
    registro_tse VARCHAR(50),
    portal VARCHAR(50),
    url TEXT,
    motivo_rejeicao TEXT NOT NULL,
    dados_brutos_json JSONB,
    data_registro TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    resolvido BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS registro_tse_oficial (
    registro_tse VARCHAR(50) PRIMARY KEY,
    protocolo_original VARCHAR(50) NOT NULL,
    uf VARCHAR(2) NOT NULL,
    cargo VARCHAR(100) NOT NULL,
    empresa_cnpj VARCHAR(20),
    empresa_nome VARCHAR(200),
    data_registro TIMESTAMPTZ,
    data_inicio DATE,
    data_fim DATE,
    data_divulgacao DATE,
    amostra INTEGER,
    valor NUMERIC(14,2),
    metodologia TEXT,
    plano_amostral TEXT,
    pesquisa_propria BOOLEAN,
    atualizado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS materia_pesquisa (
    id SERIAL PRIMARY KEY,
    registro_tse VARCHAR(50) NOT NULL,
    url TEXT NOT NULL,
    portal VARCHAR(50) NOT NULL,
    titulo TEXT,
    data_publicacao DATE,
    metodo_match VARCHAR(30) NOT NULL,
    coletado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(registro_tse, url)
);

CREATE TABLE IF NOT EXISTS url_processada (
    url TEXT PRIMARY KEY,
    portal VARCHAR(50) NOT NULL,
    processada_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pesquisa_data_fim ON pesquisa(data_fim);
CREATE INDEX IF NOT EXISTS idx_pesquisa_registro ON pesquisa(registro_tse);
CREATE INDEX IF NOT EXISTS idx_cenario_pesquisa_turno ON cenario(pesquisa_id, turno);
CREATE INDEX IF NOT EXISTS idx_resultado_cenario_candidato ON resultado(cenario_id, candidato);

CREATE OR REPLACE VIEW vw_pesquisas_completas AS
SELECT 
    r.id AS resultado_id,
    p.id AS pesquisa_id,
    c.id AS cenario_id,
    i.id AS instituto_id,
    i.nome AS instituto_nome,
    i.peso AS instituto_peso,
    i.vies_historico AS instituto_vies,
    p.registro_tse,
    p.uf,
    p.cargo,
    p.data_inicio,
    p.data_fim,
    p.data_divulgacao,
    p.amostra,
    p.margem_erro,
    p.metodologia,
    p.impugnada,
    c.turno,
    c.cenario,
    r.candidato,
    r.percentual
FROM resultado r
JOIN cenario c ON r.cenario_id = c.id
JOIN pesquisa p ON c.pesquisa_id = p.id
JOIN instituto i ON p.instituto_id = i.id;
