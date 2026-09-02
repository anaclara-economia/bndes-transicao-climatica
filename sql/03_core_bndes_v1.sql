-- Core dimensional BNDES v1 — contrato físico executado em DuckDB.
--
-- A materialização reproduzível é executada por:
--   .venv\Scripts\python.exe scripts\materializar_core_bndes_v1.py
--
-- O script cria as tabelas abaixo no banco data/local/
-- bndes_governanca_v1.duckdb usando as views stg_bndes já validadas.
-- Este arquivo registra o contrato SQL, os grãos e as chaves; não substitui
-- os Parquets nem autoriza joins adicionais sem teste de reconciliação.

CREATE SCHEMA IF NOT EXISTS core_bndes;
CREATE SCHEMA IF NOT EXISTS audit_bndes;

-- Dimensões
-- dim_tempo: uma linha por mês; inclui todos os meses do IPCA e marca YTD.
-- dim_ipca: um registro por mês do IPCA; mês-base fixo em 2026-06.
-- dim_politica: 242 políticas classificadas; 30 Verde estrito e 212 Demais.
-- dim_item_financeiro_observado: 485 combinações observadas; 80 identificadas
-- e 405 não identificadas, sem transformar combinação em política individual.
-- dim_setor: combinações distintas dos níveis setoriais observados.
-- dim_territorio: geografia válida e categorias sentinela, sem exclusão do fato.
-- dim_fonte_dado: linhagem da view/base de origem.
-- dim_fonte_recurso: dimensão desconectada; a posição de fonte não é ligada às fatos.

-- Fatos e respectivos grãos
-- fato_desembolso_mensal: uma linha analítica de desembolso (3.557.923).
-- fato_operacao_automatica: um registro automático (2.356.269), incluindo
-- 193.530 duplicatas exatas do snapshot.
-- A fato preserva chave_tecnica_snapshot e adiciona
-- chave_tecnica_snapshot_hash (SHA-256 derivado, não identificador oficial).
-- fato_subcredito_nao_automatico: uma linha/subcrédito (23.104), com
-- id_subcredito_derivado técnico.
-- A fato preserva o identificador técnico da fonte e adiciona
-- id_subcredito_derivado_hash (SHA-256 derivado).
-- fato_contrato_nao_automatico: um contrato (8.294), chave natural
-- numero_contrato; não contar subcréditos como contratos.

-- Consultas de aceite após a execução do script:
-- SELECT table_name FROM information_schema.tables
-- WHERE table_schema = 'core_bndes' ORDER BY table_name;
-- SELECT COUNT(*) FROM core_bndes.fato_desembolso_mensal;
-- SELECT COUNT(*) FROM core_bndes.fato_operacao_automatica;
-- SELECT COUNT(*) FROM core_bndes.fato_subcredito_nao_automatico;
-- SELECT COUNT(*) FROM core_bndes.fato_contrato_nao_automatico;
-- SELECT * FROM audit_bndes.controles_core_v1 ORDER BY controle;
