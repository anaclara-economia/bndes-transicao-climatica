"""Cria a primeira versão do banco DuckDB do projeto BNDES.

A versão v1 materializa as views de staging e as tabelas de auditoria do
contrato metodológico. As quatro fatos ainda são consultadas pelas views sobre
os Parquets preservados; a materialização física das fatos core será uma etapa
posterior, após a validação de desempenho e dos relacionamentos.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_DIR = ROOT / "data" / "local"
DB_PATH = DB_DIR / "bndes_governanca_v1.duckdb"
SQL_PATH = ROOT / "sql" / "01_views_padronizadas.sql"

def main() -> None:
    """Materializa o banco local, resolvendo caminhos a partir da raiz do repositório."""
    previous = Path.cwd()
    os.chdir(ROOT)
    try:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(DB_PATH))
        con.execute(SQL_PATH.read_text(encoding="utf-8"))
        con.execute("CREATE SCHEMA IF NOT EXISTS audit_bndes")
        con.execute("DROP TABLE IF EXISTS audit_bndes.contrato_metodologico_v1")
        con.execute("DROP TABLE IF EXISTS audit_bndes.controles_v1")
        con.execute("""
            CREATE TABLE audit_bndes.contrato_metodologico_v1 (
                versao VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                data_aprovacao DATE NOT NULL,
                identificacao_observacao VARCHAR NOT NULL,
                politica_individual_exige_id BOOLEAN NOT NULL,
                classificacao_verde VARCHAR NOT NULL,
                classificacao_complementar VARCHAR NOT NULL,
                duplicatas_automaticas_principal VARCHAR NOT NULL,
                fontes_recursos_status VARCHAR NOT NULL
            )
        """)
        con.execute("""
            INSERT INTO audit_bndes.contrato_metodologico_v1 VALUES
            ('v1', 'aprovado_para_sql_inicial', DATE '2026-07-16',
             'combinacao_produto_instrumento', TRUE, 'Verde estrito',
             'Demais operações', 'preservadas', 'staging_sem_relacionamento')
        """)
        con.execute("""
            CREATE TABLE audit_bndes.controles_v1 (
                controle VARCHAR NOT NULL,
                esperado VARCHAR NOT NULL,
                observado VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                executado_em TIMESTAMP NOT NULL
            )
        """)

        checks = [
            ("desembolsos_mensais", "3557923", str(con.execute("SELECT COUNT(*) FROM stg_bndes.desembolso_mensal").fetchone()[0])),
            ("operacoes_automaticas", "2356269", str(con.execute("SELECT COUNT(*) FROM stg_bndes.operacao_automatica").fetchone()[0])),
            ("subcreditos_nao_automaticos", "23104", str(con.execute("SELECT COUNT(*) FROM stg_bndes.subcredito_nao_automatico").fetchone()[0])),
            ("contratos_nao_automaticos", "8294", str(con.execute("SELECT COUNT(*) FROM stg_bndes.contrato_nao_automatico").fetchone()[0])),
            ("politicas_classificadas", "242", str(con.execute("SELECT COUNT(*) FROM stg_bndes.politica_operacional_classificada").fetchone()[0])),
            ("combinacoes_observadas", "485", str(con.execute("SELECT COUNT(*) FROM stg_bndes.item_financeiro_observado").fetchone()[0])),
            ("combinacoes_identificadas", "80", str(con.execute("SELECT COUNT(*) FROM stg_bndes.item_financeiro_observado WHERE politica_identificada_no_registro").fetchone()[0])),
            ("combinacoes_nao_identificadas", "405", str(con.execute("SELECT COUNT(*) FROM stg_bndes.item_financeiro_observado WHERE politica_nao_identificada_no_registro").fetchone()[0])),
            ("combinacoes_verde_estrito", "19", str(con.execute("SELECT COUNT(*) FROM stg_bndes.item_financeiro_observado WHERE indicador_verde_estrito").fetchone()[0])),
            ("flags_sem_nulos", "0", str(con.execute("SELECT COUNT(*) FROM stg_bndes.item_financeiro_observado WHERE politica_identificada_no_registro IS NULL OR politica_nao_identificada_no_registro IS NULL").fetchone()[0])),
            ("nao_identificadas_em_demais", "405", str(con.execute("SELECT COUNT(*) FROM stg_bndes.item_financeiro_observado WHERE politica_nao_identificada_no_registro AND classificacao_analise = 'Demais operações'").fetchone()[0])),
        ]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        con.executemany(
            "INSERT INTO audit_bndes.controles_v1 VALUES (?, ?, ?, ?, ?)",
            [(name, expected, observed, "OK" if expected == observed else "FALHA", now) for name, expected, observed in checks],
        )
        result = {
            "database": str(DB_PATH),
            "sql_views": str(SQL_PATH),
            "staging_views": con.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'stg_bndes'").fetchone()[0],
            "controles": [{"controle": n, "esperado": e, "observado": o, "status": "OK" if e == o else "FALHA"} for n, e, o in checks],
        }
        con.close()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        os.chdir(previous)


if __name__ == "__main__":
    main()
