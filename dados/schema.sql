-- ==============================================================================
-- Esquema do Banco de Dados: Agregador de Pesquisas Eleitorais 2026 (SQLite)
-- Compatível com migração direta para PostgreSQL (ANSI SQL compatível)
-- ==============================================================================

-- 1. Tabela de Institutos de Pesquisa
CREATE TABLE IF NOT EXISTS instituto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome VARCHAR(100) NOT NULL UNIQUE,
    peso REAL NOT NULL DEFAULT 1.0,
    vies_historico REAL NOT NULL DEFAULT 0.0,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabela de Pesquisas (Metadados do Registro no TSE e Trabalho de Campo)
-- Regra: Deduplicação por registro_tse
CREATE TABLE IF NOT EXISTS pesquisa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instituto_id INTEGER NOT NULL REFERENCES instituto(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    registro_tse VARCHAR(50) NOT NULL UNIQUE,
    uf VARCHAR(2) NOT NULL DEFAULT 'BR',
    cargo VARCHAR(50) NOT NULL DEFAULT 'Presidente',
    data_inicio DATE NOT NULL,
    data_fim DATE NOT NULL,
    data_divulgacao DATE,
    amostra INTEGER NOT NULL CHECK (amostra > 0),
    margem_erro REAL CHECK (margem_erro >= 0),
    metodologia TEXT,
    impugnada BOOLEAN NOT NULL DEFAULT 0,
    observacoes TEXT,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabela de Cenários e Turnos da Pesquisa
-- Uma pesquisa registrada pode conter múltiplos cenários de 1º turno e simulações de 2º turno
CREATE TABLE IF NOT EXISTS cenario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pesquisa_id INTEGER NOT NULL REFERENCES pesquisa(id) ON UPDATE CASCADE ON DELETE CASCADE,
    turno INTEGER NOT NULL DEFAULT 1 CHECK (turno IN (1, 2)),
    cenario VARCHAR(100) NOT NULL, -- Ex: 'Estimulada 1', 'Espontânea', '2º Turno - Lula x Tarcísio'
    descricao TEXT,
    UNIQUE(pesquisa_id, turno, cenario)
);

-- 4. Tabela de Resultados por Candidato e Categoria
-- Inclui candidatos nominais, 'Branco/Nulo', 'Indeciso/Não sabe'
CREATE TABLE IF NOT EXISTS resultado (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cenario_id INTEGER NOT NULL REFERENCES cenario(id) ON UPDATE CASCADE ON DELETE CASCADE,
    candidato VARCHAR(100) NOT NULL,
    percentual REAL NOT NULL CHECK (percentual >= 0.0 AND percentual <= 100.0),
    UNIQUE(cenario_id, candidato)
);

-- 5. Tabela de Fontes / URLs Coletadas (Deduplicação e Auditoria)
CREATE TABLE IF NOT EXISTS fonte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pesquisa_id INTEGER NOT NULL REFERENCES pesquisa(id) ON UPDATE CASCADE ON DELETE CASCADE,
    url TEXT NOT NULL,
    portal VARCHAR(50) NOT NULL,
    data_coleta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(pesquisa_id, url)
);

-- 6. Tabela de Quarentena (Dados brutos com falha de validação para revisão)
CREATE TABLE IF NOT EXISTS quarentena (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    registro_tse VARCHAR(50),
    portal VARCHAR(50),
    url TEXT,
    motivo_rejeicao TEXT NOT NULL,
    dados_brutos_json TEXT,
    data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolvido BOOLEAN NOT NULL DEFAULT 0
);

-- 7. Registros oficiais do TSE (dados abertos). Lista de referência do que é legítimo:
-- uma pesquisa só entra no modelo se o seu registro_tse existir aqui.
CREATE TABLE IF NOT EXISTS registro_tse_oficial (
    registro_tse VARCHAR(50) PRIMARY KEY, -- forma canônica UF-NNNNN/AAAA
    protocolo_original VARCHAR(50) NOT NULL,
    uf VARCHAR(2) NOT NULL,
    cargo VARCHAR(100) NOT NULL,
    empresa_cnpj VARCHAR(20),
    empresa_nome VARCHAR(200),
    data_registro TIMESTAMP,
    data_inicio DATE,
    data_fim DATE,
    data_divulgacao DATE,
    amostra INTEGER,
    valor REAL,
    metodologia TEXT,
    plano_amostral TEXT,
    pesquisa_propria BOOLEAN,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. Matérias jornalísticas associadas a um registro oficial do TSE
CREATE TABLE IF NOT EXISTS materia_pesquisa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    registro_tse VARCHAR(50) NOT NULL,
    url TEXT NOT NULL,
    portal VARCHAR(50) NOT NULL,
    titulo TEXT,
    data_publicacao DATE,
    metodo_match VARCHAR(30) NOT NULL, -- 'codigo' ou 'instituto+data'
    coletado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(registro_tse, url)
);

-- 9. URLs já analisadas (a coleta é incremental: cada matéria é baixada uma única vez)
CREATE TABLE IF NOT EXISTS url_processada (
    url TEXT PRIMARY KEY,
    portal VARCHAR(50) NOT NULL,
    processada_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices para otimização de consultas da série temporal e agregação
CREATE INDEX IF NOT EXISTS idx_pesquisa_data_fim ON pesquisa(data_fim);
CREATE INDEX IF NOT EXISTS idx_pesquisa_registro ON pesquisa(registro_tse);
CREATE INDEX IF NOT EXISTS idx_cenario_pesquisa_turno ON cenario(pesquisa_id, turno);
CREATE INDEX IF NOT EXISTS idx_resultado_cenario_candidato ON resultado(cenario_id, candidato);

-- ==============================================================================
-- Views Analíticas
-- ==============================================================================

-- Visão que compatibiliza a visão flat (pesquisa + cenário + resultado)
CREATE VIEW IF NOT EXISTS vw_pesquisas_completas AS
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

-- Visão condensada por cenário de pesquisa (sem abrir linha a linha por candidato)
CREATE VIEW IF NOT EXISTS vw_cenarios_pesquisa AS
SELECT 
    c.id AS cenario_id,
    p.id AS pesquisa_id,
    i.id AS instituto_id,
    i.nome AS instituto_nome,
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
    COUNT(r.id) AS total_respostas,
    ROUND(SUM(r.percentual), 2) AS soma_percentuais
FROM cenario c
JOIN pesquisa p ON c.pesquisa_id = p.id
JOIN instituto i ON p.instituto_id = i.id
LEFT JOIN resultado r ON r.cenario_id = c.id
GROUP BY c.id;
