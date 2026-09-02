"""Gera VE09: composição acumulada do Verde estrito por bloco temático.

O gráfico apresenta desembolsos e valor contratado em painéis independentes.
As barras codificam valores reais acumulados e os rótulos mostram, também, a
participação de cada bloco no total do Verde estrito do respectivo fluxo.
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
from matplotlib.ticker import MultipleLocator
import numpy as np
import pandas as pd


getcontext().prec = 50

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "results"
DB_PATH = ROOT / "data" / "local" / "bndes_governanca_v1.duckdb"
VE02_DATA = (
    BASE
    / "01_dados_analiticos"
    / "verde_estrito"
    / "VE02_valor_real_anual_verde_estrito_2002_2025.csv"
)
DATA_DIR = BASE / "tables" / "verde_estrito"
FIG_DIR = BASE / "figures" / "verde_estrito"
QA_DIR = BASE / "metadata" / "qa" / "verde_estrito"

DATA_OUTPUT = (
    DATA_DIR / "VE09_composicao_verde_estrito_por_bloco_tematico_2002_2025.csv"
)
FIG_OUTPUT = (
    FIG_DIR / "VE09_composicao_verde_estrito_por_bloco_tematico_2002_2025.png"
)
QA_OUTPUT = QA_DIR / "validacao_ve09_blocos_tematicos.json"

UNIVERSES = ["Desembolsos", "Contratações"]
PANELS = {
    "Desembolsos": "A. Desembolsos realizados",
    "Contratações": "B. Valor contratado",
}
BLOCKS = [
    "Biocombustíveis",
    "Clima e descarbonização",
    "Energia e eficiência",
    "Florestas e bioeconomia",
    "Meio ambiente",
    "Saneamento",
]

SQL = """
WITH base AS (
    SELECT
        'Desembolsos' AS universo,
        bloco_tematico AS bloco_raw,
        SUM(CAST(valor_desembolso_real_jun2026 AS DECIMAL(38,6))) AS valor_real
    FROM core_bndes.fato_desembolso_mensal
    WHERE ano BETWEEN 2002 AND 2025
      AND indicador_verde_estrito
    GROUP BY bloco_tematico

    UNION ALL

    SELECT
        'Contratações' AS universo,
        bloco_tematico AS bloco_raw,
        SUM(CAST(valor_contratado_real_jun2026 AS DECIMAL(38,6))) AS valor_real
    FROM core_bndes.fato_operacao_automatica
    WHERE ano BETWEEN 2002 AND 2025
      AND indicador_verde_estrito
    GROUP BY bloco_tematico

    UNION ALL

    SELECT
        'Contratações' AS universo,
        bloco_tematico AS bloco_raw,
        SUM(CAST(valor_contratado_real_jun2026 AS DECIMAL(38,6))) AS valor_real
    FROM core_bndes.fato_subcredito_nao_automatico
    WHERE ano BETWEEN 2002 AND 2025
      AND indicador_verde_estrito
    GROUP BY bloco_tematico
)
SELECT
    universo,
    bloco_raw,
    SUM(valor_real) AS valor_real
FROM base
GROUP BY universo, bloco_raw
ORDER BY universo, valor_real DESC
"""

FONT = "Arial"
TEXT = "#111820"
WHITE = "#FFFFFF"
GRID = "#E1E4E6"
EDGE = "#1D252C"
PANEL_COLORS = {
    "Desembolsos": "#163A5F",
    "Contratações": "#526475",
}


def fold_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", "" if value is None else str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^A-Z0-9]+", " ", text.upper()).strip()


def normalize_block(value: object) -> str | None:
    return {
        "BIOCOMBUSTIVEIS": "Biocombustíveis",
        "CLIMA E DESCARBONIZACAO": "Clima e descarbonização",
        "ENERGIA E EFICIENCIA": "Energia e eficiência",
        "FLORESTAS E BIOECONOMIA": "Florestas e bioeconomia",
        "MEIO AMBIENTE": "Meio ambiente",
        "SANEAMENTO": "Saneamento",
    }.get(fold_text(value))


def dec(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def number_br(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def pct_br(value: float) -> str:
    return f"{value:.1f}%".replace(".", ",")


def prepare() -> tuple[pd.DataFrame, dict[str, object]]:
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        raw = con.execute(SQL).fetchdf()

    raw["bloco_tematico"] = raw["bloco_raw"].map(normalize_block)
    if raw["bloco_tematico"].isna().any():
        invalid = raw.loc[raw["bloco_tematico"].isna(), "bloco_raw"].unique().tolist()
        raise AssertionError(f"Blocos temáticos não reconhecidos: {invalid}")

    values: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
    totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    for row in raw.itertuples(index=False):
        universe = str(row.universo)
        block = str(row.bloco_tematico)
        value = dec(row.valor_real)
        values[(universe, block)] += value
        totals[universe] += value

    reference = (
        pd.read_csv(VE02_DATA)
        .groupby("universo", as_index=True)["valor_verde_real_jun2026"]
        .sum()
        .to_dict()
    )

    rows: list[dict[str, object]] = []
    maximum_difference = 0.0
    maximum_share_error = 0.0

    for universe in UNIVERSES:
        total = totals[universe]
        if total <= 0:
            raise AssertionError(f"Total não positivo: {universe}")

        blocks_total = sum(
            (values[(universe, block)] for block in BLOCKS), Decimal("0")
        )
        if blocks_total != total:
            raise AssertionError(f"Reconciliação por bloco falhou: {universe}")

        difference = abs(float(total) - float(reference[universe]))
        maximum_difference = max(maximum_difference, difference)
        if not math.isclose(
            float(total), float(reference[universe]), rel_tol=1e-12, abs_tol=0.10
        ):
            raise AssertionError(f"VE09 diverge de VE02: {universe}")

        ordered = sorted(
            BLOCKS, key=lambda block: values[(universe, block)], reverse=True
        )
        shares: list[Decimal] = []
        for rank, block in enumerate(ordered, start=1):
            value = values[(universe, block)]
            share = value / total * Decimal("100")
            shares.append(share)
            rows.append(
                {
                    "universo": universe,
                    "painel": PANELS[universe],
                    "posicao": rank,
                    "bloco_tematico": block,
                    "valor_real_jun2026": float(value),
                    "valor_real_bilhoes_jun2026": float(
                        value / Decimal("1000000000")
                    ),
                    "valor_total_verde_real_jun2026": float(total),
                    "participacao_total_verde_estrito_pct": float(share),
                }
            )
        maximum_share_error = max(
            maximum_share_error,
            float(abs(sum(shares, Decimal("0")) - Decimal("100"))),
        )

    data = pd.DataFrame(rows)
    if len(data) != 12:
        raise AssertionError("VE09 deve conter 12 linhas analíticas.")
    if set(data["bloco_tematico"]) != set(BLOCKS):
        raise AssertionError("VE09 não contém exatamente os seis blocos válidos.")
    if not data["participacao_total_verde_estrito_pct"].between(0, 100).all():
        raise AssertionError("Participação fora do intervalo de 0% a 100%.")

    orders = {
        universe: data.loc[data["universo"] == universe]
        .sort_values("posicao")["bloco_tematico"]
        .tolist()
        for universe in UNIVERSES
    }
    if orders["Desembolsos"] != orders["Contratações"]:
        raise AssertionError(
            "A ordem dos blocos diverge entre fluxos; revisar o desenho compartilhado."
        )

    checks = {
        "diferenca_maxima_ve02_reais": maximum_difference,
        "erro_maximo_soma_blocos_pp": maximum_share_error,
        "ordem_comum_blocos": orders["Desembolsos"],
        "totais_verde_estrito_reais": {
            universe: float(totals[universe]) for universe in UNIVERSES
        },
    }
    return data, checks


def render(data: pd.DataFrame) -> None:
    order = (
        data.loc[data["universo"] == "Desembolsos"]
        .sort_values("posicao")["bloco_tematico"]
        .tolist()
    )
    y = np.arange(len(order))

    maximum = float(data["valor_real_bilhoes_jun2026"].max())
    label_allowance = 13.0
    axis_maximum = math.ceil((maximum + label_allowance) / 10.0) * 10.0

    mpl.rcParams.update(
        {
            "font.family": FONT,
            "font.size": 9.0,
            "axes.unicode_minus": False,
            "figure.facecolor": WHITE,
            "savefig.facecolor": WHITE,
            "axes.facecolor": WHITE,
        }
    )

    fig, axes = plt.subplots(
        1, 2, figsize=(9.0, 4.55), sharex=True, sharey=True
    )
    fig.subplots_adjust(
        left=0.235, right=0.985, top=0.875, bottom=0.16, wspace=0.13
    )

    for axis, universe in zip(axes, UNIVERSES):
        selected = (
            data.loc[data["universo"] == universe]
            .set_index("bloco_tematico")
            .loc[order]
            .reset_index()
        )
        color = PANEL_COLORS[universe]
        bars = axis.barh(
            y,
            selected["valor_real_bilhoes_jun2026"],
            height=0.56,
            color=color,
            edgecolor=EDGE,
            linewidth=0.45,
            zorder=3,
        )

        for bar, row in zip(bars, selected.itertuples(index=False)):
            value = float(row.valor_real_bilhoes_jun2026)
            share = float(row.participacao_total_verde_estrito_pct)
            axis.text(
                value + 0.75,
                bar.get_y() + bar.get_height() / 2,
                f"R$ {number_br(value)} bi ({pct_br(share)})",
                ha="left",
                va="center",
                fontsize=7.25,
                fontweight="bold",
                color=TEXT,
            )

        axis.set_xlim(0, axis_maximum)
        axis.set_ylim(-0.6, len(order) - 0.4)
        axis.invert_yaxis()
        axis.xaxis.set_major_locator(MultipleLocator(10))
        axis.grid(axis="x", color=GRID, linewidth=0.55, zorder=0)
        axis.tick_params(
            axis="x", colors=TEXT, labelsize=8.0, length=3.0, width=0.7, pad=5
        )
        axis.tick_params(axis="y", colors=TEXT, labelsize=8.2, length=0, pad=6)
        axis.set_yticks(y, order)
        for spine in ("top", "right", "left"):
            axis.spines[spine].set_visible(False)
        axis.spines["bottom"].set_color(EDGE)
        axis.spines["bottom"].set_linewidth(0.7)
        axis.set_title(
            PANELS[universe],
            loc="left",
            fontsize=10.8,
            fontweight="bold",
            color=TEXT,
            pad=18,
        )
        axis.text(
            0.0,
            1.025,
            "R$ bilhões, a preços de junho de 2026",
            transform=axis.transAxes,
            ha="left",
            va="bottom",
            fontsize=8.0,
            color="#4F5B65",
        )

    # Os rótulos dos blocos são compartilhados pelos dois painéis e aparecem
    # somente à esquerda, reduzindo repetição e mantendo o alinhamento.
    axes[1].tick_params(axis="y", labelleft=False)

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_OUTPUT, dpi=600, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)


def main() -> None:
    for directory in (DATA_DIR, FIG_DIR, QA_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    data, checks = prepare()
    data.to_csv(DATA_OUTPUT, index=False, encoding="utf-8-sig")
    render(data)

    payload = {
        "status": "aprovado_tecnicamente_para_validacao_visual",
        "periodo": "2002-2025",
        "precos_constantes": "junho de 2026",
        "universos": UNIVERSES,
        "blocos_tematicos": BLOCKS,
        "linhas_analiticas": len(data),
        **checks,
        "arquivo_png": str(FIG_OUTPUT.relative_to(ROOT)),
        "arquivo_csv": str(DATA_OUTPUT.relative_to(ROOT)),
    }
    QA_OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

