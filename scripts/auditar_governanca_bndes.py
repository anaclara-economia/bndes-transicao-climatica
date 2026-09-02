"""Auditoria reprodutivel de governanca das bases analiticas do BNDES.

O script nao altera as bases de origem. Ele le metadados e colunas selecionadas
dos Parquets e grava diagnosticos JSON em ``outputs/governanca_dados``.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
POWERBI_DATA = ROOT / "data" / "local" / "powerbi"
GOVERNANCE = ROOT / "docs"
OUTPUT = ROOT / "results" / "metadata" / "governanca_dados"


BASE_SPECS: dict[str, dict[str, Any]] = {
    "desembolsos_mensais": {
        "path": INTERIM / "desembolsos_mensais.parquet",
        "camada": "interim",
        "unidade_observacao": "registro mensal de desembolso por combinacao de dimensoes do BNDES",
        "period_field": "ano",
        "chave_candidata": [
            "ano",
            "mes",
            "forma_de_apoio",
            "produto",
            "instrumento_financeiro",
            "porte_de_empresa",
            "municipio_codigo",
            "setor_cnae",
            "subsetor_cnae_agrupado",
        ],
        "campos_monetarios": ["desembolsos_reais"],
        "observacao_chave": "A fonte nao fornece identificador unico de linha; a chave composta descreve o grao, mas exige teste de duplicidade.",
    },
    "operacoes_indiretas_automaticas": {
        "path": INTERIM / "operacoes_indiretas_automaticas.parquet",
        "camada": "interim",
        "unidade_observacao": "registro de operacao indireta automatica",
        "period_field": "data_da_contratacao",
        "chave_candidata": [],
        "campos_monetarios": ["valor_da_operacao_em_reais", "valor_desembolsado_reais"],
        "observacao_chave": "A fonte nao fornece numero de operacao; ha duplicatas exatas e qualquer chave de linha deve ser tecnica e derivada.",
    },
    "operacoes_nao_automaticas": {
        "path": INTERIM / "operacoes_nao_automaticas.parquet",
        "camada": "interim",
        "unidade_observacao": "subcredito de contrato nao automatico",
        "period_field": "data_da_contratacao",
        "chave_candidata": ["numero_do_contrato"],
        "campos_monetarios": ["valor_contratado_reais", "valor_desembolsado_reais"],
        "observacao_chave": "numero_do_contrato identifica o contrato, nao o subcredito; a fonte nao fornece numero_subcredito.",
    },
    "politicas_operacionais": {
        "path": INTERIM / "politicas_operacionais.parquet",
        "camada": "interim",
        "unidade_observacao": "registro de politica operacional",
        "period_field": None,
        "chave_candidata": [],
        "campos_monetarios": [],
        "observacao_chave": "A base tratada tem 242 linhas, mas nao possui identificador oficial persistente no arquivo-fonte.",
    },
    "fontes_recursos": {
        "path": INTERIM / "fontes_recursos.parquet",
        "camada": "interim",
        "unidade_observacao": "data anual x tipo de medida da estrutura de fontes",
        "period_field": "datas",
        "chave_candidata": ["datas", "tipo_medida_derivado"],
        "campos_monetarios": [
            "patrimonio_liquido",
            "tesouro_nacional",
            "fat",
            "captacoes_internas",
            "fundos",
            "operacoes_compromissadas",
            "captacoes_externas",
            "total_financeiro",
            "outros_passivos",
            "passivo_total",
        ],
        "observacao_chave": "Ha duas linhas por data (valores absolutos e participacoes), sem tipo de medida explicito.",
    },
    "mapeamento_bndes_cnae": {
        "path": INTERIM / "mapeamento_bndes_cnae.parquet",
        "camada": "interim",
        "unidade_observacao": "registro de correspondencia BNDES-CNAE",
        "period_field": None,
        "chave_candidata": [
            "setor_cnae_classificacao_bndes",
            "subsetor_cnae_agrupado_classificacao_bndes",
            "subsetor_bndes",
            "setor_bndes",
            "codigo_cnae_ibge",
            "produto_bndes",
        ],
        "campos_monetarios": [],
        "observacao_chave": "Mapeamento de referencia; a cardinalidade deve ser validada antes de qualquer join.",
    },
    "classificacao_politicas_analise": {
        "path": PROCESSED / "classificacao_politicas_analise.parquet",
        "camada": "processed",
        "unidade_observacao": "politica operacional classificada",
        "period_field": None,
        "chave_candidata": ["id_classificacao"],
        "campos_monetarios": [],
        "observacao_chave": "id_classificacao e unico; chave_politica_norm nao e unica.",
    },
    "dim_concordancia_historica": {
        "path": PROCESSED / "dim_concordancia_historica.parquet",
        "camada": "processed",
        "unidade_observacao": "combinacao observada de produto e instrumento financeiro",
        "period_field": None,
        "chave_candidata": ["id_concordancia", "chave_historica"],
        "campos_monetarios": [
            "valor_desembolsos_nominal",
            "valor_desembolsos_real_jun2026",
            "valor_contratacoes_nominal",
            "valor_contratacoes_real_jun2026",
        ],
        "observacao_chave": "Chave composta de produto normalizado e instrumento financeiro normalizado.",
    },
    "desembolsos_mensais_analitico": {
        "path": PROCESSED / "desembolsos_mensais_analitico.parquet",
        "camada": "processed",
        "unidade_observacao": "registro mensal de desembolso enriquecido",
        "period_field": "data_referencia",
        "chave_candidata": [],
        "campos_monetarios": ["valor_nominal", "valor_real_jun2026"],
        "observacao_chave": "Fato analitico de desembolsos, recortado para ano maior ou igual a 2002.",
    },
    "operacoes_bndes_analitica": {
        "path": PROCESSED / "operacoes_bndes_analitica.parquet",
        "camada": "processed",
        "unidade_observacao": "mistura de operacao automatica e subcredito nao automatico",
        "period_field": "data_referencia",
        "chave_candidata": ["base_origem", "id_registro_fonte"],
        "campos_monetarios": ["valor_nominal", "valor_real_jun2026"],
        "observacao_chave": "Base util para auditoria atual, mas deve ser separada em duas fatos no modelo SQL.",
    },
    "contratos_nao_automaticos_analitico": {
        "path": PROCESSED / "contratos_nao_automaticos_analitico.parquet",
        "camada": "processed",
        "unidade_observacao": "contrato nao automatico agregado",
        "period_field": "data_da_contratacao",
        "chave_candidata": ["numero_do_contrato"],
        "campos_monetarios": ["valor_contratado_nominal", "valor_contratado_real_jun2026"],
        "observacao_chave": "Tabela correta para contar contratos nao automaticos.",
    },
    "ipca_mensal": {
        "path": PROCESSED / "ipca_mensal.parquet",
        "camada": "processed",
        "unidade_observacao": "mes de referencia do IPCA",
        "period_field": "data_referencia",
        "chave_candidata": ["data_referencia"],
        "campos_monetarios": [],
        "observacao_chave": "Dimensao mensal sem duplicidade de data.",
    },
}


def parquet_metadata(path: Path) -> dict[str, Any]:
    parquet = pq.ParquetFile(path)
    return {
        "arquivo": str(path.relative_to(ROOT)).replace("\\", "/"),
        "linhas": parquet.metadata.num_rows,
        "colunas": parquet.metadata.num_columns,
        "campos": parquet.schema.names,
        "tamanho_bytes": path.stat().st_size,
    }


def min_max(path: Path, field: str) -> dict[str, Any]:
    array = pq.read_table(path, columns=[field])[field].combine_chunks()
    result = pc.min_max(array).as_py()
    return {
        "minimo": str(result["min"]),
        "maximo": str(result["max"]),
        "nulos": array.null_count,
    }


def sum_field(path: Path, field: str) -> dict[str, Any]:
    array = pq.read_table(path, columns=[field])[field].combine_chunks()
    return {"soma": pc.sum(array).as_py(), "nulos": array.null_count}


def value_counts(path: Path, field: str) -> dict[str, int]:
    array = pq.read_table(path, columns=[field])[field].combine_chunks()
    counts = pc.value_counts(array).to_pylist()
    return {str(item["values"]): int(item["counts"]) for item in counts}


def profile_bases() -> dict[str, Any]:
    profiles: dict[str, Any] = {}
    for name, spec in BASE_SPECS.items():
        path = spec["path"]
        profile = parquet_metadata(path)
        profile.update(
            {
                "camada": spec["camada"],
                "unidade_observacao": spec["unidade_observacao"],
                "chave_candidata": spec["chave_candidata"],
                "campos_monetarios": spec["campos_monetarios"],
                "observacao_chave": spec["observacao_chave"],
            }
        )
        if spec["period_field"]:
            profile["periodo"] = min_max(path, spec["period_field"])
        profile["totais_monetarios"] = {
            field: sum_field(path, field) for field in spec["campos_monetarios"]
        }
        profiles[name] = profile
    return profiles


def governance_checks() -> dict[str, Any]:
    classification_path = PROCESSED / "classificacao_politicas_analise.parquet"
    concordance_path = PROCESSED / "dim_concordancia_historica.parquet"
    operations_path = PROCESSED / "operacoes_bndes_analitica.parquet"
    desembolsos_path = PROCESSED / "desembolsos_mensais_analitico.parquet"
    contracts_path = PROCESSED / "contratos_nao_automaticos_analitico.parquet"
    fontes_path = INTERIM / "fontes_recursos.parquet"

    classification = pd.read_parquet(
        classification_path,
        columns=["id_classificacao", "chave_politica_norm", "classificacao_analise"],
    )
    concordance = pd.read_parquet(
        concordance_path,
        columns=[
            "id_concordancia",
            "chave_historica",
            "status_pareamento",
            "pareamento_confirmado",
            "indicador_verde_estrito",
        ],
    )
    contracts = pd.read_parquet(
        contracts_path, columns=["numero_do_contrato", "quantidade_subcreditos"]
    )
    fontes = pd.read_parquet(fontes_path)

    coverage: dict[str, Any] = {}
    for label, path in [
        ("desembolsos", desembolsos_path),
        ("contratacoes", operations_path),
    ]:
        frame = pd.read_parquet(
            path,
            columns=["valor_nominal", "pareamento_confirmado", "indicador_verde_estrito"],
        )
        total_value = float(frame["valor_nominal"].sum())
        identified_value = float(
            frame.loc[frame["pareamento_confirmado"], "valor_nominal"].sum()
        )
        coverage[label] = {
            "linhas": len(frame),
            "linhas_com_politica_identificada": int(frame["pareamento_confirmado"].sum()),
            "cobertura_linhas_pct": float(frame["pareamento_confirmado"].mean() * 100),
            "valor_nominal_total": total_value,
            "valor_nominal_com_politica_identificada": identified_value,
            "cobertura_valor_nominal_pct": float(identified_value / total_value * 100),
            "valor_nominal_verde_estrito": float(
                frame.loc[frame["indicador_verde_estrito"], "valor_nominal"].sum()
            ),
        }

    operations = pd.read_parquet(
        operations_path,
        columns=["base_origem", "duplicata_exata", "id_registro_fonte"],
    )
    powerbi_policy_rows = (
        pq.ParquetFile(POWERBI_DATA / "DimPolitica.parquet").metadata.num_rows
        if (POWERBI_DATA / "DimPolitica.parquet").exists()
        else None
    )

    return {
        "classificacao_politicas": {
            "registros": len(classification),
            "id_classificacao_nulos": int(classification["id_classificacao"].isna().sum()),
            "id_classificacao_duplicados": int(
                classification.duplicated("id_classificacao", keep=False).sum()
            ),
            "chave_politica_norm_duplicados": int(
                classification.duplicated("chave_politica_norm", keep=False).sum()
            ),
            "classificacao_analise": {
                str(key): int(value)
                for key, value in classification["classificacao_analise"]
                .value_counts(dropna=False)
                .items()
            },
        },
        "combinacoes_observadas": {
            "registros": len(concordance),
            "id_concordancia_nulos": int(concordance["id_concordancia"].isna().sum()),
            "id_concordancia_duplicados": int(
                concordance.duplicated("id_concordancia", keep=False).sum()
            ),
            "chave_historica_nulos": int(concordance["chave_historica"].isna().sum()),
            "chave_historica_duplicados": int(
                concordance.duplicated("chave_historica", keep=False).sum()
            ),
            "politica_identificada_no_registro": int(
                concordance["pareamento_confirmado"].sum()
            ),
            "politica_nao_identificada_no_registro": int(
                (~concordance["pareamento_confirmado"]).sum()
            ),
            "combinacoes_verde_estrito": int(
                concordance["indicador_verde_estrito"].sum()
            ),
            "status_auditoria": {
                str(key): int(value)
                for key, value in concordance["status_pareamento"]
                .value_counts(dropna=False)
                .items()
            },
        },
        "operacoes": {
            "linhas_por_base": {
                str(key): int(value)
                for key, value in operations["base_origem"].value_counts().items()
            },
            "duplicatas_exatas_automaticas": int(
                operations.loc[
                    operations["base_origem"].eq("operacoes_indiretas_automaticas"),
                    "duplicata_exata",
                ].sum()
            ),
            "chave_tecnica_base_id_duplicados": int(
                operations.duplicated(
                    ["base_origem", "id_registro_fonte"], keep=False
                ).sum()
            ),
        },
        "contratos_nao_automaticos": {
            "contratos": len(contracts),
            "numero_contrato_nulos": int(contracts["numero_do_contrato"].isna().sum()),
            "numero_contrato_duplicados": int(
                contracts.duplicated("numero_do_contrato", keep=False).sum()
            ),
            "subcreditos_reconciliados": int(contracts["quantidade_subcreditos"].sum()),
        },
        "fontes_recursos": {
            "linhas": len(fontes),
            "datas_distintas": int(fontes["datas"].nunique()),
            "linhas_com_data_duplicada": int(fontes.duplicated("datas", keep=False).sum()),
            "linhas_valores_absolutos_provaveis": int(fontes["passivo_total"].notna().sum()),
            "linhas_participacoes_provaveis": int(fontes["passivo_total"].isna().sum()),
            "decisao_pendente": "Confirmar unidade dos valores absolutos e formalizar tipo_medida antes do uso dimensional.",
        },
        "cobertura_identificacao_politicas": coverage,
        "modelo_powerbi_atual": {
            "linhas_dim_politica": powerbi_policy_rows,
            "linhas_combinacoes_observadas": len(concordance),
            "diferenca": (
                len(concordance) - powerbi_policy_rows
                if powerbi_policy_rows is not None
                else None
            ),
            "interpretacao": "O modelo publicado conserva apenas combinacoes observadas no recorte das fatos, enquanto a dimensao de auditoria contem 485 combinacoes.",
        },
    }


def complete_dictionary() -> list[dict[str, Any]]:
    spec_path = GOVERNANCE / "dicionario_nomenclatura.json"
    specification = json.loads(spec_path.read_text(encoding="utf-8"))
    mappings = specification["renomeacoes_por_base"]
    canonical = specification["campos_canonicos"]
    canonical_by_name = {item["nome_canonico"]: item for item in canonical}
    rows: list[dict[str, Any]] = []

    for base, spec in BASE_SPECS.items():
        schema = pq.ParquetFile(spec["path"]).schema_arrow
        base_mappings = mappings.get(base, {})
        for field in schema:
            source_name = field.name
            canonical_name = base_mappings.get(source_name, source_name)
            definition = canonical_by_name.get(canonical_name, {})
            rows.append(
                {
                    "base": base,
                    "camada_origem": spec["camada"],
                    "variavel_origem": source_name,
                    "variavel_canonica": canonical_name,
                    "rotulo_exibicao": definition.get(
                        "rotulo_exibicao", canonical_name.replace("_", " ").capitalize()
                    ),
                    "tipo_parquet": str(field.type),
                    "dominio": definition.get("dominio", "campo_preservado"),
                    "definicao": definition.get(
                        "definicao", "Campo preservado da base tratada; definicao oficial deve ser mantida na linhagem."
                    ),
                    "status_renomeacao": (
                        "renomeado" if canonical_name != source_name else "preservado"
                    ),
                }
            )
    return rows


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    diagnostic = {
        "projeto": str(ROOT),
        "gerado_em": datetime.now().astimezone().isoformat(),
        "politica_execucao": "somente leitura das bases; nenhuma classificacao ou Parquet foi alterado",
        "inventario": profile_bases(),
        "verificacoes_governanca": governance_checks(),
    }
    diagnostic_path = OUTPUT / "diagnostico_governanca.json"
    diagnostic_path.write_text(
        json.dumps(diagnostic, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    dictionary_path = OUTPUT / "dicionario_variaveis_completo.json"
    dictionary_path.write_text(
        json.dumps(complete_dictionary(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "diagnostico": str(diagnostic_path),
                "dicionario": str(dictionary_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
