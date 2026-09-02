"""Materializa o core dimensional v1 do projeto BNDES em DuckDB.

O script parte das views ``stg_bndes`` já auditadas, preserva seus grãos e
registra as reconciliações no schema ``audit_bndes``. Nenhum parquet é
alterado e desembolsos e contratações continuam em fatos independentes.
"""
from __future__ import annotations

import json
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "local" / "bndes_governanca_v1.duckdb"
BACKUP = ROOT / "data" / "local" / "bndes_governanca_v1_pre_core.duckdb"
REPORT = ROOT / "results" / "metadata" / "materializacao_core_bndes_v1.md"


def q(con: duckdb.DuckDBPyConnection, sql: str):
    return con.execute(sql).fetchall()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists() and not BACKUP.exists():
        shutil.copy2(DB, BACKUP)
    con = duckdb.connect(str(DB))
    con.execute("CREATE SCHEMA IF NOT EXISTS core_bndes")
    con.execute("CREATE SCHEMA IF NOT EXISTS audit_bndes")
    con.execute("BEGIN")
    try:
        # Dimensões de referência. As chaves substitutas são determinísticas
        # (row_number sobre ordenação natural) e não substituem os identificadores
        # técnicos/naturais preservados nas fatos.
        con.execute("DROP TABLE IF EXISTS core_bndes.dim_tempo")
        con.execute("""
            CREATE TABLE core_bndes.dim_tempo AS
            SELECT row_number() OVER (ORDER BY data_referencia)::INTEGER AS tempo_sk,
                   strftime(data_referencia, '%Y%m') AS ano_mes_codigo,
                   data_referencia, ano, mes,
                   ((mes - 1) / 3 + 1)::INTEGER AS trimestre,
                   bool_or(coalesce(ano_parcial, false)) AS ano_parcial,
                   CASE WHEN bool_or(coalesce(ano_parcial, false)) THEN CAST(ano AS VARCHAR) || ' (YTD)'
                        ELSE CAST(ano AS VARCHAR) END AS rotulo_periodo
            FROM (
                  SELECT DISTINCT data_referencia, ano, mes, ano_parcial
                  FROM stg_bndes.desembolso_mensal
                  UNION
                  SELECT DISTINCT data_referencia, ano, mes, ano_parcial
                  FROM stg_bndes.operacao_automatica
                  UNION
                  SELECT DISTINCT data_referencia, ano, mes, ano_parcial
                  FROM stg_bndes.subcredito_nao_automatico
                  UNION
                  SELECT DISTINCT date_trunc('month', data_contratacao)::DATE AS data_referencia, ano,
                         month(data_contratacao)::SMALLINT AS mes, ano_parcial
                  FROM stg_bndes.contrato_nao_automatico
                  UNION
                  SELECT DISTINCT data_referencia, year(data_referencia)::SMALLINT AS ano,
                         month(data_referencia)::SMALLINT AS mes, false AS ano_parcial
                  FROM stg_bndes.ipca_mensal
            ) x
            GROUP BY data_referencia, ano, mes
        """)

        con.execute("DROP TABLE IF EXISTS core_bndes.dim_ipca")
        con.execute("""
            CREATE TABLE core_bndes.dim_ipca AS
            SELECT row_number() OVER (ORDER BY data_referencia)::INTEGER AS ipca_sk,
                   data_referencia, DATE '2026-06-01' AS mes_base_referencia,
                   indice_ipca_mes, fator_correcao_ipca_jun2026 AS fator_correcao,
                   fonte_ipca
            FROM stg_bndes.ipca_mensal
        """)

        con.execute("DROP TABLE IF EXISTS core_bndes.dim_politica")
        con.execute("""
            CREATE TABLE core_bndes.dim_politica AS
            SELECT row_number() OVER (ORDER BY id_classificacao_politica)::INTEGER AS politica_sk,
                   id_classificacao, id_classificacao_politica, nivel_identificacao_politica,
                   modalidade_operacional, tipo_instrumento_apoio, instrumento_apoio,
                   linha_financiamento, sublinha_financiamento, classificacao_analise,
                   indicador_verde_estrito, bloco_tematico, classificacao_historica_auditoria,
                   TRUE AS registro_atual
            FROM stg_bndes.politica_operacional_classificada
        """)

        con.execute("DROP TABLE IF EXISTS core_bndes.dim_item_financeiro_observado")
        con.execute("""
            CREATE TABLE core_bndes.dim_item_financeiro_observado AS
            SELECT row_number() OVER (ORDER BY id_item_financeiro_observado)::INTEGER AS item_financeiro_sk,
                   id_item_financeiro_observado, chave_historica, produto_bndes,
                   instrumento_financeiro, produto_norm, instrumento_financeiro_norm,
                   classificacao_analise, politica_identificada_no_registro,
                   politica_nao_identificada_no_registro, indicador_verde_estrito,
                   id_classificacao_politica, nivel_identificacao_politica,
                   motivo_sem_id_classificacao, bloco_tematico,
                   status_identificacao_politica_auditoria,
                   regra_identificacao_politica_auditoria,
                   classificacao_historica_auditoria
            FROM stg_bndes.item_financeiro_observado
        """)

        con.execute("DROP TABLE IF EXISTS core_bndes.dim_setor")
        con.execute("""
            CREATE TABLE core_bndes.dim_setor AS
            SELECT row_number() OVER (ORDER BY setor_cnae, subsetor_cnae_agrupado,
                                               setor_bndes, subsetor_bndes)::INTEGER AS setor_sk,
                   coalesce(setor_cnae, 'Não identificado') || '|' ||
                   coalesce(subsetor_cnae_agrupado, 'Não identificado') || '|' ||
                   coalesce(setor_bndes, 'Não identificado') || '|' ||
                   coalesce(subsetor_bndes, 'Não identificado') AS chave_natural_setor,
                   coalesce(setor_cnae, 'Não identificado') AS setor_cnae,
                   coalesce(subsetor_cnae_agrupado, 'Não identificado') AS subsetor_cnae_agrupado,
                   coalesce(setor_bndes, 'Não identificado') AS setor_bndes,
                   coalesce(subsetor_bndes, 'Não identificado') AS subsetor_bndes
            FROM (SELECT DISTINCT setor_cnae, subsetor_cnae_agrupado, setor_bndes, subsetor_bndes
                  FROM stg_bndes.desembolso_mensal
                  UNION SELECT DISTINCT setor_cnae, subsetor_cnae_agrupado, setor_bndes, subsetor_bndes
                  FROM stg_bndes.operacao_automatica
                  UNION SELECT DISTINCT setor_cnae, subsetor_cnae_agrupado, setor_bndes, subsetor_bndes
                  FROM stg_bndes.subcredito_nao_automatico) s
        """)

        con.execute("DROP TABLE IF EXISTS core_bndes.dim_territorio")
        con.execute("""
            CREATE TABLE core_bndes.dim_territorio AS
            SELECT row_number() OVER (ORDER BY codigo_municipio, uf, nome_municipio)::INTEGER AS territorio_sk,
                   coalesce(codigo_municipio, '0000000') || '|' || coalesce(uf, 'NA') || '|' ||
                   coalesce(nome_municipio, 'Território não identificado no registro') AS chave_natural_territorio,
                   coalesce(codigo_municipio, '0000000') AS codigo_municipio,
                   coalesce(nome_municipio, 'Território não identificado no registro') AS nome_municipio,
                   coalesce(uf, 'NA') AS uf,
                   coalesce(regiao, 'Não identificada') AS regiao,
                   coalesce(geografia_valida, false) AS geografia_valida
            FROM (
                 SELECT codigo_municipio, uf, nome_municipio, max(regiao) AS regiao,
                        bool_or(coalesce(geografia_valida, false)) AS geografia_valida
                 FROM (
                      SELECT DISTINCT codigo_municipio, uf, nome_municipio, regiao, geografia_valida
                      FROM stg_bndes.desembolso_mensal
                      UNION SELECT DISTINCT codigo_municipio, uf, nome_municipio, NULL AS regiao, geografia_valida
                      FROM stg_bndes.operacao_automatica
                      UNION SELECT DISTINCT codigo_municipio, uf, nome_municipio, NULL AS regiao, geografia_valida
                      FROM stg_bndes.subcredito_nao_automatico
                      UNION SELECT DISTINCT '0000000' AS codigo_municipio, uf, nome_municipio, NULL AS regiao, geografia_valida
                      FROM stg_bndes.contrato_nao_automatico
                      UNION SELECT '0000000', 'NA', 'Território não identificado no registro', NULL, false
                 ) t0
                 GROUP BY 1, 2, 3
            ) t
        """)

        con.execute("DROP TABLE IF EXISTS core_bndes.dim_fonte_dado")
        con.execute("""
            CREATE TABLE core_bndes.dim_fonte_dado AS
            SELECT row_number() OVER (ORDER BY fonte_base_origem)::INTEGER AS fonte_dado_sk,
                   fonte_base_origem AS dataset_oficial,
                   fonte_base_origem AS recurso_oficial,
                   fonte_base_origem AS caminho_arquivo,
                   repeat('0', 64) AS sha256,
                   NULL::TIMESTAMP AS obtido_em
            FROM (VALUES
                 ('desembolsos_mensais'),
                 ('operacoes_indiretas_automaticas'),
                 ('operacoes_nao_automaticas_subcreditos'),
                 ('contratos_nao_automaticos')
            ) f(fonte_base_origem)
        """)
        source_meta = {
            'desembolsos_mensais': ROOT / 'data' / 'processed' / 'desembolsos_mensais_analitico.parquet',
            'operacoes_indiretas_automaticas': ROOT / 'data' / 'processed' / 'operacoes_bndes_analitica.parquet',
            'operacoes_nao_automaticas_subcreditos': ROOT / 'data' / 'processed' / 'operacoes_bndes_analitica.parquet',
            'contratos_nao_automaticos': ROOT / 'data' / 'processed' / 'contratos_nao_automaticos_analitico.parquet',
        }
        for logical_name, file_path in source_meta.items():
            if not file_path.exists():
                raise FileNotFoundError(file_path)
            obtained = datetime.fromtimestamp(file_path.stat().st_mtime, timezone.utc).replace(tzinfo=None)
            con.execute(
                "UPDATE core_bndes.dim_fonte_dado SET caminho_arquivo=?, sha256=?, obtido_em=? WHERE dataset_oficial=?",
                [str(file_path.relative_to(ROOT)), sha256_file(file_path), obtained, logical_name],
            )

        con.execute("DROP TABLE IF EXISTS core_bndes.dim_fonte_recurso")
        con.execute("""
            CREATE TABLE core_bndes.dim_fonte_recurso AS
            SELECT row_number() OVER (ORDER BY fonte_recurso)::INTEGER AS fonte_recurso_sk,
                   fonte_recurso AS codigo_fonte_recurso,
                   fonte_recurso AS nome_fonte_recurso,
                   'Fonte de recursos — staging desconectado' AS grupo_fonte_recurso,
                   TRUE AS fonte_recurso_ativa
            FROM (SELECT DISTINCT fonte_recurso FROM stg_bndes.posicao_fonte_recurso_proposta) r
        """)

        # Fato de desembolsos: preserva exatamente o grão da view analítica.
        con.execute("DROP TABLE IF EXISTS core_bndes.fato_desembolso_mensal")
        con.execute("""
            CREATE TABLE core_bndes.fato_desembolso_mensal AS
            SELECT row_number() OVER ()::BIGINT AS desembolso_sk,
                   t.tempo_sk, i.ipca_sk, fi.item_financeiro_sk,
                   se.setor_sk, te.territorio_sk, fd.fonte_dado_sk,
                   d.*, 1::INTEGER AS quantidade_registros
            FROM stg_bndes.desembolso_mensal d
            LEFT JOIN core_bndes.dim_tempo t ON t.data_referencia=d.data_referencia
            LEFT JOIN core_bndes.dim_ipca i ON i.data_referencia=d.data_referencia
            LEFT JOIN core_bndes.dim_item_financeiro_observado fi
              ON fi.produto_norm=d.produto_norm AND fi.instrumento_financeiro_norm=d.instrumento_financeiro_norm
            LEFT JOIN core_bndes.dim_setor se
              ON se.setor_cnae=d.setor_cnae AND se.subsetor_cnae_agrupado=d.subsetor_cnae_agrupado
             AND se.setor_bndes=d.setor_bndes AND se.subsetor_bndes=d.subsetor_bndes
            LEFT JOIN core_bndes.dim_territorio te
              ON te.codigo_municipio=coalesce(d.codigo_municipio,'0000000') AND te.uf=coalesce(d.uf,'NA')
             AND te.nome_municipio=coalesce(d.nome_municipio,'Território não identificado no registro')
            LEFT JOIN core_bndes.dim_fonte_dado fd ON fd.dataset_oficial=d.fonte_base_origem
        """)

        # Fato automática: não deduplicar; a chave técnica já identifica a linha
        # do snapshot e duplicata_exata é mantida para auditoria.
        con.execute("DROP TABLE IF EXISTS core_bndes.fato_operacao_automatica")
        con.execute("""
            CREATE TABLE core_bndes.fato_operacao_automatica AS
            SELECT row_number() OVER ()::BIGINT AS operacao_automatica_sk,
                   t.tempo_sk, i.ipca_sk, fi.item_financeiro_sk,
                   se.setor_sk, te.territorio_sk, fd.fonte_dado_sk,
                   sha256(concat_ws('|', 'bndes_auto_v1',
                                    cast(a.id_registro_fonte_derivado AS VARCHAR),
                                    coalesce(a.chave_tecnica_snapshot, ''))) AS chave_tecnica_snapshot_hash,
                   a.*, 1::INTEGER AS quantidade_operacoes
            FROM stg_bndes.operacao_automatica a
            LEFT JOIN core_bndes.dim_tempo t ON t.data_referencia=a.data_referencia
            LEFT JOIN core_bndes.dim_ipca i ON i.data_referencia=a.data_referencia
            LEFT JOIN core_bndes.dim_item_financeiro_observado fi
              ON fi.produto_norm=a.produto_norm AND fi.instrumento_financeiro_norm=a.instrumento_financeiro_norm
            LEFT JOIN core_bndes.dim_setor se
              ON se.setor_cnae=a.setor_cnae AND se.subsetor_cnae_agrupado=a.subsetor_cnae_agrupado
             AND se.setor_bndes=a.setor_bndes AND se.subsetor_bndes=a.subsetor_bndes
            LEFT JOIN core_bndes.dim_territorio te
              ON te.codigo_municipio=coalesce(a.codigo_municipio,'0000000') AND te.uf=coalesce(a.uf,'NA')
             AND te.nome_municipio=coalesce(a.nome_municipio,'Território não identificado no registro')
            LEFT JOIN core_bndes.dim_fonte_dado fd ON fd.dataset_oficial=a.fonte_base_origem
        """)

        con.execute("DROP TABLE IF EXISTS core_bndes.fato_subcredito_nao_automatico")
        con.execute("""
            CREATE TABLE core_bndes.fato_subcredito_nao_automatico AS
            SELECT row_number() OVER ()::BIGINT AS subcredito_sk,
                   t.tempo_sk, i.ipca_sk, fi.item_financeiro_sk,
                   se.setor_sk, te.territorio_sk, fd.fonte_dado_sk,
                   sha256(concat_ws('|', 'bndes_subcredito_v1',
                                    cast(s.id_subcredito_derivado_provisorio AS VARCHAR),
                                    coalesce(s.id_subcredito_derivado, ''))) AS id_subcredito_derivado_hash,
                   s.*, 1::INTEGER AS quantidade_subcreditos
            FROM stg_bndes.subcredito_nao_automatico s
            LEFT JOIN core_bndes.dim_tempo t ON t.data_referencia=s.data_referencia
            LEFT JOIN core_bndes.dim_ipca i ON i.data_referencia=s.data_referencia
            LEFT JOIN core_bndes.dim_item_financeiro_observado fi
              ON fi.produto_norm=s.produto_norm AND fi.instrumento_financeiro_norm=s.instrumento_financeiro_norm
            LEFT JOIN core_bndes.dim_setor se
              ON se.setor_cnae=s.setor_cnae AND se.subsetor_cnae_agrupado=s.subsetor_cnae_agrupado
             AND se.setor_bndes=s.setor_bndes AND se.subsetor_bndes=s.subsetor_bndes
            LEFT JOIN core_bndes.dim_territorio te
              ON te.codigo_municipio=coalesce(s.codigo_municipio,'0000000') AND te.uf=coalesce(s.uf,'NA')
             AND te.nome_municipio=coalesce(s.nome_municipio,'Território não identificado no registro')
            LEFT JOIN core_bndes.dim_fonte_dado fd ON fd.dataset_oficial='operacoes_nao_automaticas_subcreditos'
        """)

        con.execute("DROP TABLE IF EXISTS core_bndes.fato_contrato_nao_automatico")
        con.execute("""
            CREATE TABLE core_bndes.fato_contrato_nao_automatico AS
            SELECT row_number() OVER ()::BIGINT AS contrato_sk,
                   t.tempo_sk, te.territorio_sk, fd.fonte_dado_sk,
                   c.*, 1::INTEGER AS quantidade_contratos
            FROM stg_bndes.contrato_nao_automatico c
            LEFT JOIN core_bndes.dim_tempo t ON t.data_referencia=date_trunc('month', c.data_contratacao)::DATE
            LEFT JOIN core_bndes.dim_territorio te
              ON te.codigo_municipio='0000000' AND te.uf=coalesce(c.uf,'NA')
             AND te.nome_municipio=coalesce(c.nome_municipio,'Território não identificado no registro')
            LEFT JOIN core_bndes.dim_fonte_dado fd ON fd.dataset_oficial='contratos_nao_automaticos'
        """)

        # Auditoria materializada: substitui controles da execução anterior.
        con.execute("DROP TABLE IF EXISTS audit_bndes.controles_core_v1")
        con.execute("""
            CREATE TABLE audit_bndes.controles_core_v1 (
                controle VARCHAR, esperado VARCHAR, observado VARCHAR,
                status VARCHAR, executado_em TIMESTAMP
            )
        """)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        checks = []
        for name, table, expected in [
            ('fato_desembolso_mensal_linhas', 'fato_desembolso_mensal', 3557923),
            ('fato_operacao_automatica_linhas', 'fato_operacao_automatica', 2356269),
            ('fato_subcredito_nao_automatico_linhas', 'fato_subcredito_nao_automatico', 23104),
            ('fato_contrato_nao_automatico_linhas', 'fato_contrato_nao_automatico', 8294),
        ]:
            observed = q(con, f'SELECT COUNT(*) FROM core_bndes.{table}')[0][0]
            checks.append((name, str(expected), str(observed), 'OK' if observed == expected else 'FALHA', now))
        dup = q(con, "SELECT COUNT(*) FROM stg_bndes.operacao_automatica WHERE duplicata_exata")[0][0]
        checks.append(('duplicatas_automaticas_preservadas', '193530', str(dup), 'OK' if dup == 193530 else 'FALHA', now))
        flags = q(con, """SELECT COUNT(*) FROM stg_bndes.item_financeiro_observado
                         WHERE politica_identificada_no_registro IS NULL
                            OR politica_nao_identificada_no_registro IS NULL
                            OR politica_identificada_no_registro = politica_nao_identificada_no_registro""")[0][0]
        checks.append(('flags_complementares_sem_null', '0', str(flags), 'OK' if flags == 0 else 'FALHA', now))
        policy_observed = q(con, "SELECT COUNT(*), SUM(indicador_verde_estrito::INTEGER), SUM((NOT indicador_verde_estrito)::INTEGER) FROM stg_bndes.politica_operacional_classificada")[0]
        checks.append(('politicas_242_30_212', '242|30|212', '|'.join(str(x) for x in policy_observed), 'OK' if tuple(policy_observed) == (242, 30, 212) else 'FALHA', now))
        combo_observed = q(con, "SELECT COUNT(*), SUM(politica_identificada_no_registro::INTEGER), SUM(politica_nao_identificada_no_registro::INTEGER), SUM(indicador_verde_estrito::INTEGER) FROM stg_bndes.item_financeiro_observado")[0]
        checks.append(('combinacoes_485_80_405_19', '485|80|405|19', '|'.join(str(x) for x in combo_observed), 'OK' if tuple(combo_observed) == (485, 80, 405, 19) else 'FALHA', now))
        key_nulls = q(con, """
            SELECT coalesce(sum((tempo_sk IS NULL)::INTEGER),0)
                 + coalesce(sum((ipca_sk IS NULL)::INTEGER),0)
                 + coalesce(sum((item_financeiro_sk IS NULL)::INTEGER),0)
                 + coalesce(sum((setor_sk IS NULL)::INTEGER),0)
                 + coalesce(sum((territorio_sk IS NULL)::INTEGER),0)
                 + coalesce(sum((fonte_dado_sk IS NULL)::INTEGER),0)
            FROM core_bndes.fato_desembolso_mensal
        """)[0][0]
        checks.append(('chaves_dimensionais_sem_null', '0', str(key_nulls), 'OK' if key_nulls == 0 else 'FALHA', now))
        ipca_nulls = q(con, "SELECT COUNT(*) FROM core_bndes.fato_desembolso_mensal WHERE ipca_sk IS NULL OR fator_correcao_ipca_jun2026 IS NULL")[0][0]
        checks.append(('ipca_associado_100pct', '0', str(ipca_nulls), 'OK' if ipca_nulls == 0 else 'FALHA', now))
        contract_keys = q(con, "SELECT COUNT(*), COUNT(DISTINCT numero_contrato) FROM core_bndes.fato_contrato_nao_automatico")[0]
        checks.append(('contratos_chave_natural', '8294|8294', '|'.join(str(x) for x in contract_keys), 'OK' if tuple(contract_keys) == (8294, 8294) else 'FALHA', now))
        auto_hash = q(con, "SELECT COUNT(*), COUNT(DISTINCT chave_tecnica_snapshot_hash), min(length(chave_tecnica_snapshot_hash)), max(length(chave_tecnica_snapshot_hash)) FROM core_bndes.fato_operacao_automatica")[0]
        checks.append(('hash_snapshot_automaticas', '2356269|2356269|64|64', '|'.join(str(x) for x in auto_hash), 'OK' if tuple(auto_hash) == (2356269, 2356269, 64, 64) else 'FALHA', now))
        sub_hash = q(con, "SELECT COUNT(*), COUNT(DISTINCT id_subcredito_derivado_hash), min(length(id_subcredito_derivado_hash)), max(length(id_subcredito_derivado_hash)) FROM core_bndes.fato_subcredito_nao_automatico")[0]
        checks.append(('hash_subcreditos', '23104|23104|64|64', '|'.join(str(x) for x in sub_hash), 'OK' if tuple(sub_hash) == (23104, 23104, 64, 64) else 'FALHA', now))
        territory_dup = q(con, "SELECT COUNT(*) FROM (SELECT chave_natural_territorio FROM core_bndes.dim_territorio GROUP BY 1 HAVING COUNT(*) > 1) d")[0][0]
        checks.append(('chave_natural_territorio_unica', '0', str(territory_dup), 'OK' if territory_dup == 0 else 'FALHA', now))
        monetary = [
            ('desembolso_nominal', 'fato_desembolso_mensal', 'desembolso_mensal', 'valor_desembolso_nominal'),
            ('desembolso_real', 'fato_desembolso_mensal', 'desembolso_mensal', 'valor_desembolso_real_jun2026'),
            ('automatica_nominal', 'fato_operacao_automatica', 'operacao_automatica', 'valor_contratado_nominal'),
            ('automatica_real', 'fato_operacao_automatica', 'operacao_automatica', 'valor_contratado_real_jun2026'),
            ('subcredito_nominal', 'fato_subcredito_nao_automatico', 'subcredito_nao_automatico', 'valor_contratado_nominal'),
            ('subcredito_real', 'fato_subcredito_nao_automatico', 'subcredito_nao_automatico', 'valor_contratado_real_jun2026'),
            ('contrato_nominal', 'fato_contrato_nao_automatico', 'contrato_nao_automatico', 'valor_contratado_nominal'),
            ('contrato_real', 'fato_contrato_nao_automatico', 'contrato_nao_automatico', 'valor_contratado_real_jun2026'),
        ]
        for name, fact, source, col in monetary:
            diff = q(con, f"SELECT sum(cast({col} AS DECIMAL(38,6))) - (SELECT sum(cast({col} AS DECIMAL(38,6))) FROM stg_bndes.{source}) FROM core_bndes.{fact}")[0][0]
            checks.append((f'soma_decimal_{name}', '0.000000', str(diff), 'OK' if str(diff) in {'0.000000', '0E-6'} else 'FALHA', now))
        con.executemany('INSERT INTO audit_bndes.controles_core_v1 VALUES (?, ?, ?, ?, ?)', checks)
        con.execute("CREATE TABLE IF NOT EXISTS audit_bndes.controles_v1 (controle VARCHAR, esperado VARCHAR, observado VARCHAR, status VARCHAR, executado_em TIMESTAMP)")
        con.execute("DELETE FROM audit_bndes.controles_v1 WHERE controle LIKE 'core_%'")
        con.executemany(
            'INSERT INTO audit_bndes.controles_v1 VALUES (?, ?, ?, ?, ?)',
            [(f'core_{x[0]}', x[1], x[2], x[3], x[4]) for x in checks],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        con.close()
        raise

    dim_names = ['dim_tempo','dim_ipca','dim_politica','dim_item_financeiro_observado','dim_setor','dim_territorio','dim_fonte_dado','dim_fonte_recurso']
    dim_counts = {name: q(con, f'SELECT COUNT(*) FROM core_bndes.{name}')[0][0] for name in dim_names}
    result = {'database': str(DB), 'backup': str(BACKUP), 'dimensions': dim_counts, 'checks': [dict(zip(['controle','esperado','observado','status','executado_em'], x)) for x in checks]}
    lines = ['# Materialização do core BNDES v1', '', f"Banco: `{DB}`", f"Backup pré-core: `{BACKUP}`", '', '## Dimensões materializadas', '', '| Dimensão | Registros |', '|---|---:|']
    lines += [f'| {name} | {count} |' for name, count in dim_counts.items()]
    lines += ['', '## Controles executados', '', '| Controle | Esperado | Observado | Status |', '|---|---:|---:|---|']
    lines += [f"| {x[0]} | {x[1]} | {x[2]} | {x[3]} |" for x in checks]
    lines += ['', 'As quatro fatos são independentes; não há soma entre desembolsos e contratações. A dimensão de fontes de recursos está materializada sem relacionamento com as fatos até confirmação da unidade de medida.']
    REPORT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    con.close()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
