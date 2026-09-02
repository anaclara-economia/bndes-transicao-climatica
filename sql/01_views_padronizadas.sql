-- Proposta de views DuckDB para padronizacao nao destrutiva.
-- O arquivo nao foi executado. Os Parquets permanecem imutaveis.

CREATE SCHEMA IF NOT EXISTS stg_bndes;

CREATE OR REPLACE VIEW stg_bndes.desembolso_mensal AS
SELECT
    CAST(data_referencia AS DATE) AS data_referencia,
    CAST(ano AS SMALLINT) AS ano,
    CAST(mes AS SMALLINT) AS mes,
    forma_de_apoio AS forma_apoio,
    produto AS produto_bndes,
    instrumento_financeiro,
    inovacao,
    porte_de_empresa,
    regiao,
    uf,
    municipio AS nome_municipio,
    CAST(municipio_codigo AS VARCHAR) AS codigo_municipio,
    setor_cnae,
    subsetor_cnae_agrupado,
    setor_bndes,
    subsetor_bndes,
    CAST(valor_nominal AS DOUBLE) AS valor_desembolso_nominal,
    CAST(valor_real_jun2026 AS DOUBLE) AS valor_desembolso_real_jun2026,
    CAST(ipca_mes AS DOUBLE) AS indice_ipca_mes,
    CAST(fator_ipca_jun2026 AS DOUBLE) AS fator_correcao_ipca_jun2026,
    produto_norm,
    instrumento_financeiro_norm,
    classificacao_analise AS classificacao_analise_origem_auditoria,
    CASE
        WHEN pareamento_confirmado AND indicador_verde_estrito THEN 'Verde estrito'
        ELSE 'Demais operações'
    END AS classificacao_analise,
    CAST(pareamento_confirmado AS BOOLEAN) AS politica_identificada_no_registro,
    CAST(NOT pareamento_confirmado AS BOOLEAN) AS politica_nao_identificada_no_registro,
    CAST(pareamento_confirmado AND indicador_verde_estrito AS BOOLEAN) AS indicador_verde_estrito,
    CAST(NULL AS INTEGER) AS id_classificacao_politica,
    CASE WHEN pareamento_confirmado THEN 'combinacao_produto_instrumento_confirmada' ELSE 'nao_identificada' END AS nivel_identificacao_politica,
    CASE WHEN pareamento_confirmado THEN 'vinculo_individual_nao_preservado' WHEN status_pareamento = 'Candidato para revisão' OR regra_pareamento LIKE 'Palavra-chave%' THEN 'candidata_sem_confirmacao' ELSE 'sem_correspondencia_confirmada' END AS motivo_sem_id_classificacao,
    COALESCE(bloco_tematico, 'Não classificado') AS bloco_tematico,
    status_pareamento AS status_identificacao_politica_auditoria,
    regra_pareamento AS regra_identificacao_politica_auditoria,
    classificacao_original AS classificacao_historica_auditoria,
    base_origem AS fonte_base_origem,
    unidade_analise AS unidade_observacao,
    CAST(ano_parcial AS BOOLEAN) AS ano_parcial,
    CAST(geografia_valida AS BOOLEAN) AS geografia_valida
FROM read_parquet('data/processed/desembolsos_mensais_analitico.parquet');

CREATE OR REPLACE VIEW stg_bndes.operacao_automatica AS
SELECT
    id_registro_fonte AS id_registro_fonte_derivado,
    CAST(id_registro_fonte AS VARCHAR) AS chave_tecnica_snapshot,
    CAST(data_da_contratacao AS DATE) AS data_contratacao,
    CAST(data_referencia AS DATE) AS data_referencia,
    CAST(ano AS SMALLINT) AS ano,
    CAST(mes AS SMALLINT) AS mes,
    CAST(valor_nominal AS DOUBLE) AS valor_contratado_nominal,
    CAST(valor_real_jun2026 AS DOUBLE) AS valor_contratado_real_jun2026,
    CAST(valor_desembolsado_reais AS DOUBLE) AS valor_desembolsado_nominal,
    fonte_de_recurso_desembolsos,
    modalidade_de_apoio AS modalidade_apoio,
    forma_de_apoio AS forma_apoio,
    produto AS produto_bndes,
    instrumento_financeiro,
    area_operacional,
    setor_cnae,
    subsetor_cnae_agrupado,
    setor_bndes,
    subsetor_bndes,
    uf,
    municipio AS nome_municipio,
    CAST(municipio_codigo AS VARCHAR) AS codigo_municipio,
    porte_do_cliente,
    natureza_do_cliente,
    produto_norm,
    instrumento_financeiro_norm,
    CASE
        WHEN pareamento_confirmado AND indicador_verde_estrito THEN 'Verde estrito'
        ELSE 'Demais operações'
    END AS classificacao_analise,
    CAST(pareamento_confirmado AS BOOLEAN) AS politica_identificada_no_registro,
    CAST(NOT pareamento_confirmado AS BOOLEAN) AS politica_nao_identificada_no_registro,
    CAST(pareamento_confirmado AND indicador_verde_estrito AS BOOLEAN) AS indicador_verde_estrito,
    CAST(NULL AS INTEGER) AS id_classificacao_politica,
    CASE WHEN pareamento_confirmado THEN 'combinacao_produto_instrumento_confirmada' ELSE 'nao_identificada' END AS nivel_identificacao_politica,
    CASE WHEN pareamento_confirmado THEN 'vinculo_individual_nao_preservado' WHEN status_pareamento = 'Candidato para revisão' OR regra_pareamento LIKE 'Palavra-chave%' THEN 'candidata_sem_confirmacao' ELSE 'sem_correspondencia_confirmada' END AS motivo_sem_id_classificacao,
    COALESCE(bloco_tematico, 'Não classificado') AS bloco_tematico,
    status_pareamento AS status_identificacao_politica_auditoria,
    regra_pareamento AS regra_identificacao_politica_auditoria,
    classificacao_original AS classificacao_historica_auditoria,
    CAST(duplicata_exata AS BOOLEAN) AS duplicata_exata,
    base_origem AS fonte_base_origem,
    unidade_analise AS unidade_observacao,
    CAST(ano_parcial AS BOOLEAN) AS ano_parcial,
    CAST(geografia_valida AS BOOLEAN) AS geografia_valida
FROM read_parquet('data/processed/operacoes_bndes_analitica.parquet')
WHERE base_origem = 'operacoes_indiretas_automaticas';

CREATE OR REPLACE VIEW stg_bndes.subcredito_nao_automatico AS
SELECT
    id_registro_fonte AS id_subcredito_derivado_provisorio,
    CAST(numero_do_contrato AS VARCHAR) AS numero_contrato,
    CAST(id_registro_fonte AS VARCHAR) AS id_subcredito_derivado,
    CAST(data_da_contratacao AS DATE) AS data_contratacao,
    CAST(data_referencia AS DATE) AS data_referencia,
    CAST(ano AS SMALLINT) AS ano,
    CAST(mes AS SMALLINT) AS mes,
    CAST(valor_nominal AS DOUBLE) AS valor_contratado_nominal,
    CAST(valor_real_jun2026 AS DOUBLE) AS valor_contratado_real_jun2026,
    CAST(valor_desembolsado_reais AS DOUBLE) AS valor_desembolsado_nominal,
    fonte_de_recurso_desembolsos,
    modalidade_de_apoio AS modalidade_apoio,
    forma_de_apoio AS forma_apoio,
    produto AS produto_bndes,
    instrumento_financeiro,
    area_operacional,
    setor_cnae,
    subsetor_cnae_agrupado,
    setor_bndes,
    subsetor_bndes,
    uf,
    municipio AS nome_municipio,
    CAST(municipio_codigo AS VARCHAR) AS codigo_municipio,
    porte_do_cliente,
    natureza_do_cliente,
    produto_norm,
    instrumento_financeiro_norm,
    CASE
        WHEN pareamento_confirmado AND indicador_verde_estrito THEN 'Verde estrito'
        ELSE 'Demais operações'
    END AS classificacao_analise,
    CAST(pareamento_confirmado AS BOOLEAN) AS politica_identificada_no_registro,
    CAST(NOT pareamento_confirmado AS BOOLEAN) AS politica_nao_identificada_no_registro,
    CAST(pareamento_confirmado AND indicador_verde_estrito AS BOOLEAN) AS indicador_verde_estrito,
    CAST(NULL AS INTEGER) AS id_classificacao_politica,
    CASE WHEN pareamento_confirmado THEN 'combinacao_produto_instrumento_confirmada' ELSE 'nao_identificada' END AS nivel_identificacao_politica,
    CASE WHEN pareamento_confirmado THEN 'vinculo_individual_nao_preservado' WHEN status_pareamento = 'Candidato para revisão' OR regra_pareamento LIKE 'Palavra-chave%' THEN 'candidata_sem_confirmacao' ELSE 'sem_correspondencia_confirmada' END AS motivo_sem_id_classificacao,
    COALESCE(bloco_tematico, 'Não classificado') AS bloco_tematico,
    status_pareamento AS status_identificacao_politica_auditoria,
    regra_pareamento AS regra_identificacao_politica_auditoria,
    classificacao_original AS classificacao_historica_auditoria,
    base_origem AS fonte_base_origem,
    unidade_analise AS unidade_observacao,
    CAST(ano_parcial AS BOOLEAN) AS ano_parcial,
    CAST(geografia_valida AS BOOLEAN) AS geografia_valida
FROM read_parquet('data/processed/operacoes_bndes_analitica.parquet')
WHERE base_origem = 'operacoes_nao_automaticas';

CREATE OR REPLACE VIEW stg_bndes.contrato_nao_automatico AS
SELECT
    CAST(numero_do_contrato AS VARCHAR) AS numero_contrato,
    CAST(data_da_contratacao AS DATE) AS data_contratacao,
    CAST(ano AS SMALLINT) AS ano,
    uf,
    municipio AS nome_municipio,
    CAST(quantidade_subcreditos AS INTEGER) AS quantidade_subcreditos,
    CAST(valor_contratado_nominal AS DOUBLE) AS valor_contratado_nominal,
    CAST(valor_contratado_real_jun2026 AS DOUBLE) AS valor_contratado_real_jun2026,
    CAST(todos_subcreditos_verdes AS BOOLEAN) AS todos_subcreditos_verdes,
    CAST(algum_subcredito_verde AS BOOLEAN) AS algum_subcredito_verde,
    CAST(geografia_valida AS BOOLEAN) AS geografia_valida,
    CAST(ano_parcial AS BOOLEAN) AS ano_parcial
FROM read_parquet('data/processed/contratos_nao_automaticos_analitico.parquet');

CREATE OR REPLACE VIEW stg_bndes.politica_operacional_classificada AS
SELECT
    CAST(id_classificacao AS INTEGER) AS id_classificacao,
    CAST(id_classificacao AS INTEGER) AS id_classificacao_politica,
    'politica_individual_identificada' AS nivel_identificacao_politica,
    modalidade AS modalidade_operacional,
    tipo_de_apoio AS tipo_instrumento_apoio,
    instrumento_de_apoio AS instrumento_apoio,
    linha AS linha_financiamento,
    sublinha AS sublinha_financiamento,
    classificacao_analise,
    CAST(indicador_verde_estrito AS BOOLEAN) AS indicador_verde_estrito,
    COALESCE(bloco_tematico, 'Não classificado') AS bloco_tematico,
    classificacao_original AS classificacao_historica_auditoria,
    chave_politica,
    chave_politica_norm
FROM read_parquet('data/processed/classificacao_politicas_analise.parquet');

CREATE OR REPLACE VIEW stg_bndes.item_financeiro_observado AS
SELECT
    CAST(id_concordancia AS INTEGER) AS id_item_financeiro_observado,
    chave_historica,
    produto AS produto_bndes,
    instrumento_financeiro,
    produto_norm,
    instrumento_financeiro_norm,
    CASE
        WHEN pareamento_confirmado AND indicador_verde_estrito THEN 'Verde estrito'
        ELSE 'Demais operações'
    END AS classificacao_analise,
    CAST(pareamento_confirmado AS BOOLEAN) AS politica_identificada_no_registro,
    CAST(NOT pareamento_confirmado AS BOOLEAN) AS politica_nao_identificada_no_registro,
    CAST(pareamento_confirmado AND indicador_verde_estrito AS BOOLEAN) AS indicador_verde_estrito,
    CAST(NULL AS INTEGER) AS id_classificacao_politica,
    CASE WHEN pareamento_confirmado THEN 'combinacao_produto_instrumento_confirmada' ELSE 'nao_identificada' END AS nivel_identificacao_politica,
    CASE WHEN pareamento_confirmado THEN 'vinculo_individual_nao_preservado' WHEN status_pareamento = 'Candidato para revisão' OR regra_pareamento LIKE 'Palavra-chave%' THEN 'candidata_sem_confirmacao' ELSE 'sem_correspondencia_confirmada' END AS motivo_sem_id_classificacao,
    COALESCE(bloco_tematico, 'Não classificado') AS bloco_tematico,
    status_pareamento AS status_identificacao_politica_auditoria,
    regra_pareamento AS regra_identificacao_politica_auditoria,
    classificacao_original AS classificacao_historica_auditoria,
    registros_desembolsos,
    valor_desembolsos_nominal,
    registros_contratacoes,
    valor_contratacoes_nominal
FROM read_parquet('data/processed/dim_concordancia_historica.parquet');

CREATE OR REPLACE VIEW stg_bndes.ipca_mensal AS
SELECT
    CAST(data_referencia AS DATE) AS data_referencia,
    ano_mes_codigo,
    mes_nome,
    CAST(ipca_mes AS DOUBLE) AS indice_ipca_mes,
    CAST(fator_ipca_jun2026 AS DOUBLE) AS fator_correcao_ipca_jun2026,
    fonte_ipca
FROM read_parquet('data/processed/ipca_mensal.parquet');

-- A regra abaixo identifica provisoriamente as duas linhas anuais.
-- Nao materializar antes de confirmar unidade e tipo de medida com a pesquisadora.
CREATE OR REPLACE VIEW stg_bndes.posicao_fonte_recurso_proposta AS
SELECT
    CAST(f.datas AS DATE) AS data_posicao_fontes_recursos,
    CASE
        WHEN f.passivo_total IS NULL THEN 'participacao'
        ELSE 'valor_absoluto_unidade_pendente'
    END AS tipo_medida_fonte_recurso,
    v.fonte_recurso,
    CAST(v.valor AS DOUBLE) AS valor_fonte_recurso,
    CAST(f.total_financeiro AS DOUBLE) AS total_financeiro_auditoria,
    CAST(f.passivo_total AS DOUBLE) AS passivo_total_auditoria
FROM read_parquet('data/interim/fontes_recursos.parquet') AS f
CROSS JOIN LATERAL (
    VALUES
        ('Patrimônio líquido', f.patrimonio_liquido),
        ('Tesouro Nacional', f.tesouro_nacional),
        ('FAT', f.fat),
        ('Captações internas', f.captacoes_internas),
        ('Fundos', f.fundos),
        ('Operações compromissadas', f.operacoes_compromissadas),
        ('Captações externas', f.captacoes_externas),
        ('Outros passivos', f.outros_passivos)
) AS v(fonte_recurso, valor);

-- Controles minimos esperados ao executar as views:
-- SELECT COUNT(*) FROM stg_bndes.desembolso_mensal;             -- 3.557.923
-- SELECT COUNT(*) FROM stg_bndes.operacao_automatica;           -- 2.356.269
-- SELECT COUNT(*) FROM stg_bndes.subcredito_nao_automatico;     -- 23.104
-- SELECT COUNT(*) FROM stg_bndes.contrato_nao_automatico;       -- 8.294
-- SELECT COUNT(*) FROM stg_bndes.item_financeiro_observado;     -- 485
-- SELECT COUNT(*) FROM stg_bndes.politica_operacional_classificada; -- 242
