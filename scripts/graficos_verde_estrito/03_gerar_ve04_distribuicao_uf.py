"""Gera a distribuição acumulada do Verde estrito por Unidade da Federação.

VE04 preserva desembolsos e valor contratado como universos independentes.
Todas as 27 UFs são exibidas em ordem decrescente; o residual territorial só
aparece quando possui valor positivo, mas permanece sempre no denominador.
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
GREEN_SOURCE = BASE / "tables" / "verde_estrito" / "fonte_excel_ve01_ve03.json"
DATA_DIR = BASE / "tables" / "verde_estrito"
FIG_DIR = BASE / "figures" / "verde_estrito"
QA_DIR = BASE / "metadata" / "qa" / "verde_estrito"
GOV_DIR = BASE / "metadata" / "verde_estrito"

DATA_OUTPUT = DATA_DIR / "VE04_distribuicao_uf_verde_estrito_2002_2025.csv"
FIG_OUTPUT = FIG_DIR / "VE04_distribuicao_uf_verde_estrito_2002_2025.png"
QA_OUTPUT = QA_DIR / "validacao_ve04_distribuicao_uf.json"

PANEL_DESEMBOLSOS = "A. Desembolsos realizados"
PANEL_CONTRATADO = "B. Valor contratado"
PANELS = [PANEL_DESEMBOLSOS, PANEL_CONTRATADO]
UNIVERSE_TO_PANEL = {
    "Desembolsos": PANEL_DESEMBOLSOS,
    "Contratações": PANEL_CONTRATADO,
}
YEARS = list(range(2002, 2026))
RESIDUAL = "Sem identificação territorial"

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
IBGE_PREFIX_TO_UF = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA",
    "16": "AP", "17": "TO", "21": "MA", "22": "PI", "23": "CE",
    "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE",
    "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
    "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT",
    "52": "GO", "53": "DF",
}

SQL_UF_YEAR = f"""
WITH base AS (
    SELECT
        '{PANEL_DESEMBOLSOS}' AS painel,
        ano,
        COALESCE(CAST(uf AS VARCHAR), '') AS uf_raw,
        COALESCE(CAST(codigo_municipio AS VARCHAR), '') AS codigo_municipio_raw,
        SUM(CAST(valor_desembolso_real_jun2026 AS DECIMAL(38,6))) AS valor_real
    FROM core_bndes.fato_desembolso_mensal
    WHERE ano BETWEEN 2002 AND 2025 AND indicador_verde_estrito
    GROUP BY ano, uf, codigo_municipio

    UNION ALL

    SELECT
        '{PANEL_CONTRATADO}' AS painel,
        ano,
        COALESCE(CAST(uf AS VARCHAR), '') AS uf_raw,
        COALESCE(CAST(codigo_municipio AS VARCHAR), '') AS codigo_municipio_raw,
        SUM(CAST(valor_contratado_real_jun2026 AS DECIMAL(38,6))) AS valor_real
    FROM core_bndes.fato_operacao_automatica
    WHERE ano BETWEEN 2002 AND 2025 AND indicador_verde_estrito
    GROUP BY ano, uf, codigo_municipio

    UNION ALL

    SELECT
        '{PANEL_CONTRATADO}' AS painel,
        ano,
        COALESCE(CAST(uf AS VARCHAR), '') AS uf_raw,
        COALESCE(CAST(codigo_municipio AS VARCHAR), '') AS codigo_municipio_raw,
        SUM(CAST(valor_contratado_real_jun2026 AS DECIMAL(38,6))) AS valor_real
    FROM core_bndes.fato_subcredito_nao_automatico
    WHERE ano BETWEEN 2002 AND 2025 AND indicador_verde_estrito
    GROUP BY ano, uf, codigo_municipio
)
SELECT painel, ano, uf_raw, codigo_municipio_raw, SUM(valor_real) AS valor_real
FROM base
GROUP BY painel, ano, uf_raw, codigo_municipio_raw
ORDER BY painel, ano, uf_raw, codigo_municipio_raw
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


def load_green_reference() -> pd.DataFrame:
    records = json.loads(GREEN_SOURCE.read_text(encoding="utf-8"))
    reference = pd.DataFrame(records)
    reference["painel"] = reference["universo"].map(UNIVERSE_TO_PANEL)
    return reference[["painel", "ano", "valor_verde_real_jun2026"]].copy()


def load_and_classify() -> tuple[pd.DataFrame, pd.DataFrame]:
    with duckdb.connect(str(DB_PATH), read_only=True) as connection:
        raw = connection.execute(SQL_UF_YEAR).fetchdf()

    raw["ano"] = raw["ano"].astype(int)
    raw["valor_real"] = raw["valor_real"].map(as_decimal)
    buckets: defaultdict[tuple[str, int, str], Decimal] = defaultdict(Decimal)
    totals: defaultdict[tuple[str, int], Decimal] = defaultdict(Decimal)

    for row in raw.itertuples(index=False):
        panel = str(row.painel)
        year = int(row.ano)
        value = as_decimal(row.valor_real)
        uf_norm = normalize_uf(row.uf_raw)
        code = re.sub(r"\D", "", str(row.codigo_municipio_raw)).zfill(7)
        uf_code = IBGE_PREFIX_TO_UF.get(code[:2]) if len(code) == 7 else None
        conflict = uf_norm is not None and uf_code is not None and uf_norm != uf_code
        territory = uf_norm if uf_norm is not None and not conflict else RESIDUAL
        buckets[(panel, year, territory)] += value
        totals[(panel, year)] += value

    annual_rows: list[dict[str, object]] = []
    qa_rows: list[dict[str, object]] = []
    all_territories = sorted(VALID_UFS) + [RESIDUAL]
    reference = load_green_reference()

    for panel in PANELS:
        for year in YEARS:
            total = totals[(panel, year)]
            parts = sum(
                (buckets[(panel, year, territory)] for territory in all_territories),
                start=Decimal("0"),
            )
            if total <= 0 or parts != total:
                raise AssertionError(f"Reconciliação territorial falhou: {panel}, {year}")
            validated = float(
                reference.loc[
                    (reference["painel"] == panel) & (reference["ano"] == year),
                    "valor_verde_real_jun2026",
                ].iloc[0]
            )
            difference = abs(float(total) - validated)
            if not math.isclose(float(total), validated, rel_tol=1e-12, abs_tol=0.10):
                raise AssertionError(f"VE04 diverge da série verde: {panel}, {year}")
            qa_rows.append(
                {
                    "painel": panel,
                    "ano": year,
                    "total_real_jun2026": float(total),
                    "erro_partes_reais": float(abs(parts - total)),
                    "diferenca_serie_verde_reais": difference,
                }
            )
            for territory in all_territories:
                annual_rows.append(
                    {
                        "painel": panel,
                        "ano": year,
                        "territorio": territory,
                        "valor_real_jun2026": float(buckets[(panel, year, territory)]),
                    }
                )

    return pd.DataFrame(annual_rows), pd.DataFrame(qa_rows)


def build_distribution(annual: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for panel in PANELS:
        accumulated = (
            annual.loc[annual["painel"] == panel]
            .groupby("territorio", as_index=True)["valor_real_jun2026"]
            .sum()
        )
        total = float(accumulated.sum())
        if total <= 0:
            raise AssertionError(f"Total acumulado inválido: {panel}")
        uf_order = (
            accumulated.drop(index=RESIDUAL)
            .sort_values(ascending=False, kind="mergesort")
            .index.tolist()
        )
        display = uf_order.copy()
        if float(accumulated.loc[RESIDUAL]) > 0:
            display.append(RESIDUAL)
        for order, territory in enumerate(display, start=1):
            value = float(accumulated.loc[territory])
            rows.append(
                {
                    "painel": panel,
                    "ordem_exibicao": order,
                    "posicao_uf": order if territory != RESIDUAL else None,
                    "territorio": territory,
                    "tipo_linha": "Residual" if territory == RESIDUAL else "UF",
                    "valor_real_acumulado_jun2026": value,
                    "participacao_pct": 100 * value / total,
                }
            )
    distribution = pd.DataFrame(rows)
    sums = distribution.groupby("painel")["participacao_pct"].sum()
    if not np.allclose(sums.to_numpy(), 100.0, rtol=0, atol=1e-10):
        raise AssertionError(f"Participações não reconciliam:\n{sums}")
    return distribution


def render(distribution: pd.DataFrame) -> None:
    maximum = float(distribution["participacao_pct"].max())
    tick_step = 5.0 if maximum <= 30 else 10.0
    axis_max = max(15.0, math.ceil((maximum + 3.0) / tick_step) * tick_step)
    mpl.rcParams.update(
        {
            "font.family": FONT,
            "axes.unicode_minus": False,
            "figure.facecolor": WHITE,
            "savefig.facecolor": WHITE,
        }
    )
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 8.1), sharex=True, sharey=False)
    fig.subplots_adjust(left=0.105, right=0.985, bottom=0.075, top=0.94, wspace=0.29)
    max_rows = int(distribution.groupby("painel").size().max())

    for ax, panel in zip(axes, PANELS):
        data = distribution.loc[distribution["painel"] == panel].sort_values("ordem_exibicao")
        y = np.arange(len(data))
        residual_mask = data["tipo_linha"].eq("Residual").to_numpy()
        bars = ax.barh(
            y,
            data["participacao_pct"],
            height=0.52,
            color=np.where(residual_mask, WHITE, BLACK),
            edgecolor=BLACK,
            linewidth=0.72,
            zorder=2,
        )
        for bar, residual in zip(bars, residual_mask):
            if residual:
                bar.set_hatch("///")
        label_offset = axis_max * 0.010
        for yi, value in zip(y, data["participacao_pct"]):
            value = float(value)
            ax.text(
                max(value + label_offset, label_offset),
                yi,
                pct_br(value),
                va="center",
                ha="left",
                fontsize=6.8,
                fontweight="bold",
                color=BLACK,
                zorder=3,
            )
        labels = [
            "Sem identificação\nterritorial" if item == RESIDUAL else item
            for item in data["territorio"]
        ]
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=7.4, color=BLACK)
        ax.set_ylim(max_rows - 0.5, -0.5)
        ax.set_xlim(0, axis_max)
        ax.xaxis.set_major_locator(MultipleLocator(tick_step))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0f}%"))
        ax.tick_params(axis="x", labelsize=7.3, colors=BLACK, length=3, width=0.65, pad=5)
        ax.tick_params(axis="y", length=0, pad=5)
        ax.grid(axis="x", color=GRID, linewidth=0.55, zorder=0)
        ax.grid(axis="y", visible=False)
        for spine in ["top", "right", "left"]:
            ax.spines[spine].set_visible(False)
        ax.spines["bottom"].set_color(BLACK)
        ax.spines["bottom"].set_linewidth(0.75)
        ax.set_title(panel, loc="left", fontsize=10.5, fontweight="bold", color=BLACK, pad=12)

    FIG_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_OUTPUT, dpi=600, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)


def main() -> None:
    for directory in (DATA_DIR, FIG_DIR, QA_DIR, GOV_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    annual, qa = load_and_classify()
    distribution = build_distribution(annual)
    distribution.to_csv(DATA_OUTPUT, index=False, encoding="utf-8-sig")
    render(distribution)

    residual = distribution.loc[distribution["tipo_linha"] == "Residual", ["painel", "participacao_pct"]]
    payload = {
        "status": "aprovado_tecnicamente_para_validacao_visual",
        "periodo": "2002-2025",
        "universos": PANELS,
        "ufs_exibidas_por_painel": distribution.loc[
            distribution["tipo_linha"] == "UF"
        ].groupby("painel").size().astype(int).to_dict(),
        "residual_territorial_pct": residual.set_index("painel")["participacao_pct"].to_dict(),
        "soma_participacoes_pct": distribution.groupby("painel")["participacao_pct"].sum().to_dict(),
        "erro_partes_maximo_reais": float(qa["erro_partes_reais"].max()),
        "diferenca_maxima_serie_verde_reais": float(qa["diferenca_serie_verde_reais"].max()),
        "arquivo_png": str(FIG_OUTPUT.relative_to(ROOT)),
        "arquivo_csv": str(DATA_OUTPUT.relative_to(ROOT)),
    }
    QA_OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
