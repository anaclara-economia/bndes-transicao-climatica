-- DDL de referencia para PostgreSQL/DuckDB adaptavel.
-- PROPOSTA NAO EXECUTADA. Tipos e constraints devem ser aprovados antes da carga.

CREATE SCHEMA IF NOT EXISTS core_bndes;
CREATE SCHEMA IF NOT EXISTS audit_bndes;

CREATE TABLE core_bndes.dim_tempo (
    tempo_sk INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ano_mes_codigo CHAR(6) NOT NULL UNIQUE,
    data_referencia DATE NOT NULL UNIQUE,
    ano SMALLINT NOT NULL,
    mes SMALLINT NOT NULL CHECK (mes BETWEEN 1 AND 12),
    trimestre SMALLINT NOT NULL CHECK (trimestre BETWEEN 1 AND 4),
    ano_parcial BOOLEAN NOT NULL,
    rotulo_periodo VARCHAR(80) NOT NULL
);

CREATE TABLE core_bndes.dim_ipca (
    ipca_sk INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    data_referencia DATE NOT NULL,
    mes_base_referencia DATE NOT NULL,
    indice_ipca_mes NUMERIC(18, 8) NOT NULL CHECK (indice_ipca_mes > 0),
    fator_correcao NUMERIC(18, 10) NOT NULL CHECK (fator_correcao > 0),
    fonte_ipca TEXT NOT NULL,
    UNIQUE (data_referencia, mes_base_referencia, fonte_ipca)
);

CREATE TABLE core_bndes.dim_politica (
    politica_sk INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_classificacao INTEGER NOT NULL UNIQUE,
    modalidade_operacional VARCHAR(40) NOT NULL,
    tipo_instrumento_apoio VARCHAR(40) NOT NULL,
    instrumento_apoio TEXT NOT NULL,
    linha_financiamento TEXT NOT NULL,
    sublinha_financiamento TEXT NOT NULL,
    classificacao_analise VARCHAR(30) NOT NULL
        CHECK (classificacao_analise IN ('Verde estrito', 'Demais operações')),
    indicador_verde_estrito BOOLEAN NOT NULL,
    bloco_tematico VARCHAR(120) NOT NULL,
    classificacao_historica_auditoria TEXT,
    registro_atual BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE core_bndes.dim_item_financeiro_observado (
    item_financeiro_sk INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chave_historica TEXT NOT NULL UNIQUE,
    produto_bndes TEXT NOT NULL,
    instrumento_financeiro TEXT NOT NULL,
    produto_norm TEXT NOT NULL,
    instrumento_financeiro_norm TEXT NOT NULL,
    classificacao_analise VARCHAR(30) NOT NULL
        CHECK (classificacao_analise IN ('Verde estrito', 'Demais operações')),
    politica_identificada_no_registro BOOLEAN NOT NULL,
    politica_nao_identificada_no_registro BOOLEAN NOT NULL,
    indicador_verde_estrito BOOLEAN NOT NULL,
    bloco_tematico VARCHAR(120) NOT NULL,
    status_identificacao_politica_auditoria TEXT NOT NULL,
    regra_identificacao_politica_auditoria TEXT NOT NULL,
    classificacao_historica_auditoria TEXT,
    CHECK (politica_identificada_no_registro <> politica_nao_identificada_no_registro),
    CHECK (NOT indicador_verde_estrito OR politica_identificada_no_registro),
    CHECK (politica_identificada_no_registro OR classificacao_analise = 'Demais operações')
);

CREATE TABLE core_bndes.ponte_item_financeiro_politica (
    item_financeiro_sk INTEGER NOT NULL REFERENCES core_bndes.dim_item_financeiro_observado,
    politica_sk INTEGER NOT NULL REFERENCES core_bndes.dim_politica,
    tipo_evidencia VARCHAR(80) NOT NULL,
    fonte_evidencia TEXT NOT NULL,
    aprovado_por TEXT NOT NULL,
    aprovado_em TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (item_financeiro_sk, politica_sk)
);

CREATE TABLE core_bndes.dim_setor (
    setor_sk INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chave_natural_setor TEXT NOT NULL UNIQUE,
    setor_cnae TEXT NOT NULL,
    subsetor_cnae_agrupado TEXT NOT NULL,
    setor_bndes TEXT NOT NULL,
    subsetor_bndes TEXT NOT NULL
);

CREATE TABLE core_bndes.dim_territorio (
    territorio_sk INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chave_natural_territorio TEXT NOT NULL UNIQUE,
    codigo_municipio VARCHAR(7) NOT NULL,
    nome_municipio TEXT NOT NULL,
    uf VARCHAR(2) NOT NULL,
    regiao VARCHAR(30) NOT NULL,
    geografia_valida BOOLEAN NOT NULL
);

CREATE TABLE core_bndes.dim_fonte_recurso (
    fonte_recurso_sk INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo_fonte_recurso VARCHAR(80) NOT NULL UNIQUE,
    nome_fonte_recurso TEXT NOT NULL,
    grupo_fonte_recurso TEXT NOT NULL,
    fonte_recurso_ativa BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE core_bndes.dim_fonte_dado (
    fonte_dado_sk INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_oficial TEXT NOT NULL,
    recurso_oficial TEXT NOT NULL,
    caminho_arquivo TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    obtido_em TIMESTAMP WITH TIME ZONE,
    UNIQUE (caminho_arquivo, sha256)
);

CREATE TABLE core_bndes.fato_desembolso_mensal (
    desembolso_sk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tempo_sk INTEGER NOT NULL REFERENCES core_bndes.dim_tempo,
    ipca_sk INTEGER NOT NULL REFERENCES core_bndes.dim_ipca,
    item_financeiro_sk INTEGER NOT NULL REFERENCES core_bndes.dim_item_financeiro_observado,
    setor_sk INTEGER NOT NULL REFERENCES core_bndes.dim_setor,
    territorio_sk INTEGER NOT NULL REFERENCES core_bndes.dim_territorio,
    fonte_dado_sk INTEGER NOT NULL REFERENCES core_bndes.dim_fonte_dado,
    valor_desembolso_nominal NUMERIC(20, 2) NOT NULL CHECK (valor_desembolso_nominal >= 0),
    valor_desembolso_real_jun2026 NUMERIC(20, 2) NOT NULL CHECK (valor_desembolso_real_jun2026 >= 0),
    quantidade_registros INTEGER NOT NULL DEFAULT 1 CHECK (quantidade_registros = 1)
);

CREATE TABLE core_bndes.fato_operacao_automatica (
    operacao_automatica_sk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chave_registro_origem TEXT NOT NULL UNIQUE,
    tempo_sk INTEGER NOT NULL REFERENCES core_bndes.dim_tempo,
    ipca_sk INTEGER NOT NULL REFERENCES core_bndes.dim_ipca,
    item_financeiro_sk INTEGER NOT NULL REFERENCES core_bndes.dim_item_financeiro_observado,
    setor_sk INTEGER NOT NULL REFERENCES core_bndes.dim_setor,
    territorio_sk INTEGER NOT NULL REFERENCES core_bndes.dim_territorio,
    fonte_dado_sk INTEGER NOT NULL REFERENCES core_bndes.dim_fonte_dado,
    valor_contratado_nominal NUMERIC(20, 2) NOT NULL CHECK (valor_contratado_nominal >= 0),
    valor_contratado_real_jun2026 NUMERIC(20, 2) NOT NULL CHECK (valor_contratado_real_jun2026 >= 0),
    valor_desembolsado_nominal NUMERIC(20, 2),
    duplicata_exata BOOLEAN NOT NULL,
    quantidade_operacoes INTEGER NOT NULL DEFAULT 1 CHECK (quantidade_operacoes = 1)
);

CREATE TABLE core_bndes.fato_subcredito_nao_automatico (
    subcredito_sk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_subcredito_derivado TEXT NOT NULL UNIQUE,
    numero_contrato TEXT NOT NULL,
    tempo_sk INTEGER NOT NULL REFERENCES core_bndes.dim_tempo,
    ipca_sk INTEGER NOT NULL REFERENCES core_bndes.dim_ipca,
    item_financeiro_sk INTEGER NOT NULL REFERENCES core_bndes.dim_item_financeiro_observado,
    setor_sk INTEGER NOT NULL REFERENCES core_bndes.dim_setor,
    territorio_sk INTEGER NOT NULL REFERENCES core_bndes.dim_territorio,
    fonte_dado_sk INTEGER NOT NULL REFERENCES core_bndes.dim_fonte_dado,
    valor_contratado_nominal NUMERIC(20, 2) NOT NULL CHECK (valor_contratado_nominal >= 0),
    valor_contratado_real_jun2026 NUMERIC(20, 2) NOT NULL CHECK (valor_contratado_real_jun2026 >= 0),
    valor_desembolsado_nominal NUMERIC(20, 2),
    quantidade_subcreditos INTEGER NOT NULL DEFAULT 1 CHECK (quantidade_subcreditos = 1)
);

CREATE TABLE core_bndes.fato_contrato_nao_automatico (
    contrato_sk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    numero_contrato TEXT NOT NULL UNIQUE,
    tempo_sk INTEGER NOT NULL REFERENCES core_bndes.dim_tempo,
    territorio_sk INTEGER NOT NULL REFERENCES core_bndes.dim_territorio,
    fonte_dado_sk INTEGER NOT NULL REFERENCES core_bndes.dim_fonte_dado,
    quantidade_subcreditos INTEGER NOT NULL CHECK (quantidade_subcreditos >= 1),
    valor_contratado_nominal NUMERIC(20, 2) NOT NULL CHECK (valor_contratado_nominal >= 0),
    valor_contratado_real_jun2026 NUMERIC(20, 2) NOT NULL CHECK (valor_contratado_real_jun2026 >= 0),
    todos_subcreditos_verdes BOOLEAN NOT NULL,
    algum_subcredito_verde BOOLEAN NOT NULL,
    quantidade_contratos INTEGER NOT NULL DEFAULT 1 CHECK (quantidade_contratos = 1)
);

CREATE TABLE core_bndes.fato_posicao_fonte_recurso (
    posicao_fonte_recurso_sk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    data_posicao DATE NOT NULL,
    fonte_recurso_sk INTEGER NOT NULL REFERENCES core_bndes.dim_fonte_recurso,
    fonte_dado_sk INTEGER NOT NULL REFERENCES core_bndes.dim_fonte_dado,
    tipo_medida_fonte_recurso VARCHAR(40) NOT NULL,
    valor_fonte_recurso NUMERIC(20, 6) NOT NULL,
    UNIQUE (data_posicao, fonte_recurso_sk, tipo_medida_fonte_recurso, fonte_dado_sk)
);

CREATE TABLE audit_bndes.execucao_pipeline (
    execucao_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    iniciado_em TIMESTAMP WITH TIME ZONE NOT NULL,
    finalizado_em TIMESTAMP WITH TIME ZONE,
    versao_codigo TEXT NOT NULL,
    contrato_metodologico TEXT NOT NULL,
    status VARCHAR(30) NOT NULL,
    mensagem TEXT
);

CREATE TABLE audit_bndes.resultado_teste_qualidade (
    resultado_teste_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    execucao_id BIGINT NOT NULL REFERENCES audit_bndes.execucao_pipeline,
    codigo_teste VARCHAR(20) NOT NULL,
    tabela_avaliada TEXT NOT NULL,
    severidade VARCHAR(20) NOT NULL,
    aprovado BOOLEAN NOT NULL,
    valor_observado TEXT,
    valor_esperado TEXT,
    evidencia TEXT
);

-- A carga deve criar membros sentinela explicitos antes das fatos, por exemplo:
-- territorio_sk = 0: Territorio nao identificado no registro.
-- setor_sk = 0: Setor nao identificado no registro.
-- item_financeiro_sk = 0: Item financeiro nao identificado no registro.
-- A existencia de sentinelas nao autoriza remover as 405 combinacoes conhecidas.
