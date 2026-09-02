"""Gera VE05: Top 10 municípios do Verde estrito em quatro painéis.

Os rankings usam somente municípios válidos na Malha Municipal IBGE 2024. O
residual territorial fica fora do ranking, mas permanece no denominador.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import defaultdict
from decimal import Decimal, getcontext
from pathlib import Path

import duckdb
import geopandas as gpd
import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MultipleLocator
import numpy as np
import pandas as pd


getcontext().prec = 50

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "results"
DB_PATH = ROOT / "data" / "local" / "bndes_governanca_v1.duckdb"
GEO_PATH = ROOT / "data" / "external" / "ibge_2024" / "ibge_municipios_2024_simplificado_epsg4674.gpkg"
GREEN_SOURCE = BASE / "tables" / "verde_estrito" / "fonte_excel_ve01_ve03.json"
DATA_DIR = BASE / "tables" / "verde_estrito"
FIG_DIR = BASE / "figures" / "verde_estrito"
QA_DIR = BASE / "metadata" / "qa" / "verde_estrito"

RANKING_OUTPUT = DATA_DIR / "VE05_top10_municipios_verde_estrito_2002_2025_e_2025.csv"
COVERAGE_OUTPUT = DATA_DIR / "VE05_cobertura_municipal_verde_estrito_2002_2025_e_2025.csv"
FIG_OUTPUT = FIG_DIR / "VE05_top10_municipios_verde_estrito_2002_2025_e_2025.png"
QA_OUTPUT = QA_DIR / "validacao_ve05_top10_municipios.json"

YEARS = list(range(2002, 2026))
N_YEARS = len(YEARS)
LAST_YEAR = 2025
TOP_N = 10
PANEL_SPECS = [
    ("A. Desembolsos — média anual, 2002–2025", "Desembolsos", "media_2002_2025"),
    ("B. Desembolsos — 2025", "Desembolsos", "ano_2025"),
    ("C. Valor contratado — média anual, 2002–2025", "Contratações", "media_2002_2025"),
    ("D. Valor contratado — 2025", "Contratações", "ano_2025"),
]

INVALID_NAMES = {
    "DIVERSOS", "SEM MUNICIPIO", "NAO IDENTIFICADO",
    "TERRITORIO NAO IDENTIFICADO NO REGISTRO",
}
UF_NAME_TO_ABBREV = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM",
    "BAHIA": "BA", "CEARA": "CE", "DISTRITO FEDERAL": "DF",
    "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA",
    "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS",
    "MINAS GERAIS": "MG", "PARA": "PA", "PARAIBA": "PB",
    "PARANA": "PR", "PERNAMBUCO": "PE", "PIAUI": "PI",
    "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN",
    "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO", "RORAIMA": "RR",
    "SANTA CATARINA": "SC", "SAO PAULO": "SP", "SERGIPE": "SE",
    "TOCANTINS": "TO",
}
VALID_UFS = set(UF_NAME_TO_ABBREV.values())

SQL_MUNICIPAL_YEAR = """
WITH base AS (
    SELECT
        'Desembolsos' AS universo,
        ano,
        territorio_sk,
        SUM(CAST(valor_desembolso_real_jun2026 AS DECIMAL(38,6))) AS valor_real,
        COUNT(*)::BIGINT AS quantidade_registros
    FROM core_bndes.fato_desembolso_mensal
    WHERE ano BETWEEN 2002 AND 2025 AND indicador_verde_estrito
    GROUP BY ano, territorio_sk

    UNION ALL

    SELECT
        'Contratações' AS universo,
        ano,
        territorio_sk,
        SUM(CAST(valor_contratado_real_jun2026 AS DECIMAL(38,6))) AS valor_real,
        COUNT(*)::BIGINT AS quantidade_registros
    FROM core_bndes.fato_operacao_automatica
    WHERE ano BETWEEN 2002 AND 2025 AND indicador_verde_estrito
    GROUP BY ano, territorio_sk

    UNION ALL

    SELECT
        'Contratações' AS universo,
        ano,
        territorio_sk,
        SUM(CAST(valor_contratado_real_jun2026 AS DECIMAL(38,6))) AS valor_real,
        COUNT(*)::BIGINT AS quantidade_registros
    FROM core_bndes.fato_subcredito_nao_automatico
    WHERE ano BETWEEN 2002 AND 2025 AND indicador_verde_estrito
    GROUP BY ano, territorio_sk
)
SELECT
    b.universo,
    b.ano,
    t.codigo_municipio,
    t.nome_municipio,
    t.uf,
    t.geografia_valida,
    SUM(b.valor_real) AS valor_real,
    SUM(b.quantidade_registros)::BIGINT AS quantidade_registros
FROM base b
LEFT JOIN core_bndes.dim_territorio t USING (territorio_sk)
GROUP BY b.universo, b.ano, t.codigo_municipio, t.nome_municipio,
         t.uf, t.geografia_valida
ORDER BY b.universo, b.ano, t.codigo_municipio, t.uf, t.nome_municipio
"""

BLACK = "#000000"
GRID = "#E1E4E6"
WHITE = "#FFFFFF"
FONT = "Times New Roman"


def fold_text(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^A-Z0-9]+", " ", text.upper()).strip()


def normalize_uf(value: object) -> str | None:
    key = fold_text(value)
    if key in VALID_UFS:
        return key
    return UF_NAME_TO_ABBREV.get(key)


def as_decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def pct_br(value: float) -> str:
    return f"{value:.1f}%".replace(".", ",")


def load_geo_lookup() -> dict[str, tuple[str, str]]:
    municipalities = gpd.read_file(GEO_PATH, layer="municipios_2024", engine="pyogrio")
    municipalities["code_muni"] = municipalities["code_muni"].astype("int64").astype(str).str.zfill(7)
    municipalities["abbrev_state"] = municipalities["abbrev_state"].astype(str).str.upper()
    if municipalities["code_muni"].duplicated().any():
        raise AssertionError("A malha municipal contém códigos duplicados")
    return {
        str(row.code_muni): (str(row.name_muni), str(row.abbrev_state))
        for row in municipalities[["code_muni", "name_muni", "abbrev_state"]].itertuples(index=False)
    }


def load_green_reference() -> pd.DataFrame:
    records = json.loads(GREEN_SOURCE.read_text(encoding="utf-8"))
    reference = pd.DataFrame(records)
    return reference[["universo", "ano", "valor_verde_real_jun2026"]].copy()


def load_and_classify() -> tuple[pd.DataFrame, pd.DataFrame, float]:
    geo_lookup = load_geo_lookup()
    with duckdb.connect(str(DB_PATH), read_only=True) as connection:
        raw = connection.execute(SQL_MUNICIPAL_YEAR).fetchdf()
    raw["ano"] = raw["ano"].astype(int)
    raw["valor_real"] = raw["valor_real"].map(as_decimal)

    buckets: defaultdict[tuple[str, int, str], Decimal] = defaultdict(Decimal)
    record_buckets: defaultdict[tuple[str, int, str], int] = defaultdict(int)
    totals: defaultdict[tuple[str, int], Decimal] = defaultdict(Decimal)
    municipality_meta: dict[str, tuple[str, str]] = {}

    for row in raw.itertuples(index=False):
        universe = str(row.universo)
        year = int(row.ano)
        value = as_decimal(row.valor_real)
        code = re.sub(r"\D", "", str(row.codigo_municipio or "")).zfill(7)
        name_key = fold_text(row.nome_municipio)
        uf_norm = normalize_uf(row.uf)
        geo = geo_lookup.get(code)
        valid = (
            bool(row.geografia_valida)
            and code not in {"0000000", "9999999"}
            and name_key not in INVALID_NAMES
            and geo is not None
            and uf_norm == geo[1]
        )
        territory = code if valid else "RESIDUAL"
        if valid and geo is not None:
            municipality_meta[code] = geo
        buckets[(universe, year, territory)] += value
        record_buckets[(universe, year, territory)] += int(row.quantidade_registros)
        totals[(universe, year)] += value

    reference = load_green_reference()
    maximum_difference = 0.0
    annual_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    universes = ["Desembolsos", "Contratações"]

    for universe in universes:
        for year in YEARS:
            total = totals[(universe, year)]
            identified = sum(
                (value for (u, y, territory), value in buckets.items()
                 if u == universe and y == year and territory != "RESIDUAL"),
                start=Decimal("0"),
            )
            residual = buckets[(universe, year, "RESIDUAL")]
            if total <= 0 or identified + residual != total:
                raise AssertionError(f"Reconciliação municipal falhou: {universe}, {year}")
            validated = float(
                reference.loc[
                    (reference["universo"] == universe) & (reference["ano"] == year),
                    "valor_verde_real_jun2026",
                ].iloc[0]
            )
            difference = abs(float(total) - validated)
            maximum_difference = max(maximum_difference, difference)
            if not math.isclose(float(total), validated, rel_tol=1e-12, abs_tol=0.10):
                raise AssertionError(f"VE05 diverge da série verde: {universe}, {year}")
            coverage_rows.append(
                {
                    "universo": universe,
                    "recorte": str(year),
                    "valor_total_real_jun2026": float(total),
                    "valor_municipal_identificado_real_jun2026": float(identified),
                    "valor_sem_municipio_valido_real_jun2026": float(residual),
                    "cobertura_municipal_pct": float(identified / total * Decimal("100")),
                    "residual_municipal_pct": float(residual / total * Decimal("100")),
                }
            )

        total_period = sum((totals[(universe, year)] for year in YEARS), Decimal("0"))
        residual_period = sum((buckets[(universe, year, "RESIDUAL")] for year in YEARS), Decimal("0"))
        identified_period = total_period - residual_period
        coverage_rows.append(
            {
                "universo": universe,
                "recorte": "2002-2025",
                "valor_total_real_jun2026": float(total_period),
                "valor_municipal_identificado_real_jun2026": float(identified_period),
                "valor_sem_municipio_valido_real_jun2026": float(residual_period),
                "cobertura_municipal_pct": float(identified_period / total_period * Decimal("100")),
                "residual_municipal_pct": float(residual_period / total_period * Decimal("100")),
            }
        )

        for code, (municipality, uf) in municipality_meta.items():
            for year in YEARS:
                annual_rows.append(
                    {
                        "universo": universe,
                        "ano": year,
                        "codigo_municipio": code,
                        "municipio": municipality,
                        "uf": uf,
                        "valor_real_jun2026": float(buckets[(universe, year, code)]),
                        "quantidade_registros": record_buckets[(universe, year, code)],
                    }
                )
    return pd.DataFrame(annual_rows), pd.DataFrame(coverage_rows), maximum_difference


def build_rankings(annual: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for panel, universe, cut in PANEL_SPECS:
        if cut == "media_2002_2025":
            data = (
                annual.loc[annual["universo"] == universe]
                .groupby(["codigo_municipio", "municipio", "uf"], as_index=False)
                .agg(
                    valor_acumulado_real_jun2026=("valor_real_jun2026", "sum"),
                    quantidade_registros=("quantidade_registros", "sum"),
                )
            )
            data["valor_referencia_real_jun2026"] = data["valor_acumulado_real_jun2026"] / N_YEARS
            denominator = float(
                coverage.loc[
                    (coverage["universo"] == universe) & (coverage["recorte"] == "2002-2025"),
                    "valor_total_real_jun2026",
                ].iloc[0]
            ) / N_YEARS
        else:
            data = annual.loc[
                (annual["universo"] == universe) & (annual["ano"] == LAST_YEAR)
            ].copy()
            data = data.rename(columns={"valor_real_jun2026": "valor_referencia_real_jun2026"})
            denominator = float(
                coverage.loc[
                    (coverage["universo"] == universe) & (coverage["recorte"] == str(LAST_YEAR)),
                    "valor_total_real_jun2026",
                ].iloc[0]
            )

        data = data.sort_values(
            ["valor_referencia_real_jun2026", "quantidade_registros", "municipio", "uf"],
            ascending=[False, False, True, True],
            kind="mergesort",
        ).head(TOP_N)
        if len(data) != TOP_N or data["codigo_municipio"].nunique() != TOP_N:
            raise AssertionError(f"Top 10 inválido: {panel}")
        for rank, row in enumerate(data.itertuples(index=False), start=1):
            value = float(row.valor_referencia_real_jun2026)
            rows.append(
                {
                    "painel": panel,
                    "universo": universe,
                    "recorte": cut,
                    "posicao": rank,
                    "codigo_municipio": row.codigo_municipio,
                    "municipio": row.municipio,
                    "uf": row.uf,
                    "rotulo_municipio": f"{row.municipio} ({row.uf})",
                    "valor_referencia_real_jun2026": value,
                    "participacao_total_pct": 100 * value / denominator,
                    "quantidade_registros": int(row.quantidade_registros),
                }
            )
    ranking = pd.DataFrame(rows)
    if len(ranking) != len(PANEL_SPECS) * TOP_N:
        raise AssertionError("Quantidade inesperada de linhas no ranking")
    if not ranking["participacao_total_pct"].between(0, 100).all():
        raise AssertionError("Participação municipal fora do intervalo de 0% a 100%")
    return ranking


def render(ranking: pd.DataFrame) -> None:
    maximum = float(ranking["participacao_total_pct"].max())
    if maximum <= 5:
        tick_step = 1.0
    elif maximum <= 10:
        tick_step = 2.0
    elif maximum <= 30:
        tick_step = 5.0
    else:
        tick_step = 10.0
    axis_max = max(tick_step * 3, math.ceil((maximum + tick_step) / tick_step) * tick_step)

    mpl.rcParams.update(
        {
            "font.family": FONT,
            "axes.unicode_minus": False,
            "figure.facecolor": WHITE,
            "savefig.facecolor": WHITE,
        }
    )
    fig, axes = plt.subplots(2, 2, figsize=(9.0, 8.3), sharex=True, sharey=False)
    fig.subplots_adjust(left=0.205, right=0.985, bottom=0.075, top=0.955, wspace=0.50, hspace=0.30)

    for ax, (panel, _, _) in zip(axes.flat, PANEL_SPECS):
        data = ranking.loc[ranking["painel"] == panel].sort_values("posicao")
        y = np.arange(len(data))
        ax.barh(
            y,
            data["participacao_total_pct"],
            height=0.56,
            color=BLACK,
            edgecolor=BLACK,
            linewidth=0.7,
            zorder=2,
        )
        offset = axis_max * 0.012
        for yi, value in zip(y, data["participacao_total_pct"]):
            ax.text(
                float(value) + offset,
                yi,
                pct_br(float(value)),
                va="center",
                ha="left",
                fontsize=7.5,
                fontweight="bold",
                color=BLACK,
                zorder=3,
            )
        ax.set_yticks(y)
        ax.set_yticklabels(data["rotulo_municipio"], fontsize=7.7, color=BLACK)
        ax.set_ylim(TOP_N - 0.5, -0.5)
        ax.set_xlim(0, axis_max)
        ax.xaxis.set_major_locator(MultipleLocator(tick_step))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}%"))
        ax.tick_params(axis="x", labelsize=7.4, colors=BLACK, length=3, width=0.65, pad=5)
        ax.tick_params(axis="y", length=0, pad=5)
        ax.grid(axis="x", color=GRID, linewidth=0.55, zorder=0)
        ax.grid(axis="y", visible=False)
        for spine in ["top", "right", "left"]:
            ax.spines[spine].set_visible(False)
        ax.spines["bottom"].set_color(BLACK)
        ax.spines["bottom"].set_linewidth(0.75)
        ax.set_title(panel, loc="left", fontsize=9.4, fontweight="bold", color=BLACK, pad=10)

    FIG_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_OUTPUT, dpi=600, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)


def main() -> None:
    for directory in (DATA_DIR, FIG_DIR, QA_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    annual, coverage, maximum_difference = load_and_classify()
    ranking = build_rankings(annual, coverage)
    ranking.to_csv(RANKING_OUTPUT, index=False, encoding="utf-8-sig")
    coverage.to_csv(COVERAGE_OUTPUT, index=False, encoding="utf-8-sig")
    render(ranking)

    selected_coverage = coverage.loc[coverage["recorte"].isin(["2002-2025", str(LAST_YEAR)])].copy()
    payload = {
        "status": "aprovado_tecnicamente_para_validacao_visual",
        "periodo_media": "2002-2025",
        "divisor_media_anual": N_YEARS,
        "ano_comparacao": LAST_YEAR,
        "paineis": [panel for panel, _, _ in PANEL_SPECS],
        "linhas_ranking": len(ranking),
        "municipios_por_painel": TOP_N,
        "diferenca_maxima_serie_verde_reais": maximum_difference,
        "cobertura_municipal": selected_coverage.to_dict(orient="records"),
        "arquivo_png": str(FIG_OUTPUT.relative_to(ROOT)),
        "arquivo_ranking": str(RANKING_OUTPUT.relative_to(ROOT)),
        "arquivo_cobertura": str(COVERAGE_OUTPUT.relative_to(ROOT)),
    }
    QA_OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
