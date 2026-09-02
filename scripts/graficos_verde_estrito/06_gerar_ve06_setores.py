"""Gera VE06: participação anual do Verde estrito por setor do BNDES.

Os dois fluxos permanecem independentes. Em cada painel e ano, os quatro
setores oficiais são divididos pelo total anual do próprio Verde estrito.
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
import pandas as pd

getcontext().prec = 50

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "results"
DB_PATH = ROOT / "data" / "local" / "bndes_governanca_v1.duckdb"
GREEN_SOURCE = BASE / "tables" / "verde_estrito" / "fonte_excel_ve01_ve03.json"
DATA_DIR = BASE / "tables" / "verde_estrito"
FIG_DIR = BASE / "figures" / "verde_estrito"
QA_DIR = BASE / "metadata" / "qa" / "verde_estrito"
DATA_OUTPUT = DATA_DIR / "VE06_participacao_anual_setor_bndes_verde_estrito_2002_2025.csv"
FIG_OUTPUT = FIG_DIR / "VE06_participacao_anual_setor_bndes_verde_estrito_2002_2025.png"
FIG_OUTPUT_VERTICAL = FIG_DIR / "VE06_participacao_anual_setor_bndes_verde_estrito_2002_2025_vertical.png"
QA_OUTPUT = QA_DIR / "validacao_ve06_setores.json"

YEARS = list(range(2002, 2026))
YEAR_TICKS = [2002, 2006, 2010, 2014, 2018, 2022, 2025]
UNIVERSES = ["Desembolsos", "Contratações"]
PANELS = {"Desembolsos": "A. Desembolsos realizados", "Contratações": "B. Valor contratado"}
SECTORS = ["Agropecuária", "Comércio e Serviços", "Indústria", "Infraestrutura"]

SQL = """
WITH base AS (
 SELECT 'Desembolsos' universo, ano, setor_bndes setor_raw,
        SUM(CAST(valor_desembolso_real_jun2026 AS DECIMAL(38,6))) valor_real
 FROM core_bndes.fato_desembolso_mensal
 WHERE ano BETWEEN 2002 AND 2025 AND indicador_verde_estrito
 GROUP BY ano, setor_bndes
 UNION ALL
 SELECT 'Contratações', ano, setor_bndes,
        SUM(CAST(valor_contratado_real_jun2026 AS DECIMAL(38,6)))
 FROM core_bndes.fato_operacao_automatica
 WHERE ano BETWEEN 2002 AND 2025 AND indicador_verde_estrito
 GROUP BY ano, setor_bndes
 UNION ALL
 SELECT 'Contratações', ano, setor_bndes,
        SUM(CAST(valor_contratado_real_jun2026 AS DECIMAL(38,6)))
 FROM core_bndes.fato_subcredito_nao_automatico
 WHERE ano BETWEEN 2002 AND 2025 AND indicador_verde_estrito
 GROUP BY ano, setor_bndes
)
SELECT universo, ano, setor_raw, SUM(valor_real) valor_real
FROM base GROUP BY universo, ano, setor_raw ORDER BY universo, ano, setor_raw
"""

BLACK, WHITE, GRID, FONT = "#1D252C", "#FFFFFF", "#E1E4E6", "Arial"
STYLES = {
    "Agropecuária": {"linestyle": "-", "marker": "o", "color": "#8A8F94"},
    "Comércio e Serviços": {"linestyle": (0, (4.2, 2.2)), "marker": "s", "color": "#8A6F5A"},
    "Indústria": {"linestyle": (0, (5.0, 1.8, 1.2, 1.8)), "marker": "D", "color": "#3F5968"},
    "Infraestrutura": {"linestyle": (0, (1.2, 2.0)), "marker": "^", "color": "#163A5F"},
}


def fold_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", "" if value is None else str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^A-Z0-9]+", " ", text.upper()).strip()


def normalize_sector(value: object) -> str | None:
    return {
        "AGROPECUARIA": "Agropecuária",
        "COMERCIO E SERVICOS": "Comércio e Serviços",
        "COMERCIO SERVICOS": "Comércio e Serviços",
        "INDUSTRIA": "Indústria",
        "INFRAESTRUTURA": "Infraestrutura",
        "INFRA ESTRUTURA": "Infraestrutura",
    }.get(fold_text(value))


def dec(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def pct_br(value: float) -> str:
    return f"{value:.1f}%".replace(".", ",")


def prepare() -> tuple[pd.DataFrame, dict[str, float]]:
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        raw = con.execute(SQL).fetchdf()
    raw["ano"] = raw["ano"].astype(int)
    raw["setor_bndes"] = raw["setor_raw"].map(normalize_sector)
    if raw["setor_bndes"].isna().any():
        bad = raw.loc[raw["setor_bndes"].isna(), "setor_raw"].unique().tolist()
        raise AssertionError(f"Setores não reconhecidos: {bad}")

    values: defaultdict[tuple[str, int, str], Decimal] = defaultdict(Decimal)
    totals: defaultdict[tuple[str, int], Decimal] = defaultdict(Decimal)
    for row in raw.itertuples(index=False):
        key = (str(row.universo), int(row.ano), str(row.setor_bndes))
        value = dec(row.valor_real)
        values[key] += value
        totals[key[:2]] += value

    reference = {
        (str(row["universo"]), int(row["ano"])): float(row["valor_verde_real_jun2026"])
        for row in json.loads(GREEN_SOURCE.read_text(encoding="utf-8"))
    }
    rows, max_diff, max_share_error = [], 0.0, 0.0
    for universe in UNIVERSES:
        for year in YEARS:
            total = totals[(universe, year)]
            parts = sum((values[(universe, year, sector)] for sector in SECTORS), Decimal("0"))
            if total <= 0 or parts != total:
                raise AssertionError(f"Reconciliação setorial falhou: {universe}, {year}")
            difference = abs(float(total) - reference[(universe, year)])
            max_diff = max(max_diff, difference)
            if not math.isclose(float(total), reference[(universe, year)], rel_tol=1e-12, abs_tol=0.10):
                raise AssertionError(f"VE06 diverge da série verde: {universe}, {year}")
            shares = []
            for sector in SECTORS:
                value = values[(universe, year, sector)]
                share = value / total * Decimal("100")
                shares.append(share)
                rows.append({
                    "universo": universe, "painel": PANELS[universe], "ano": year,
                    "setor_bndes": sector, "valor_real_jun2026": float(value),
                    "valor_total_verde_real_jun2026": float(total),
                    "participacao_verde_estrito_pct": float(share),
                })
            max_share_error = max(max_share_error, float(abs(sum(shares, Decimal("0")) - Decimal("100"))))
    data = pd.DataFrame(rows)
    if len(data) != 192:
        raise AssertionError("VE06 deve conter 192 linhas analíticas")
    return data, {"diferenca_maxima_serie_verde_reais": max_diff, "erro_maximo_soma_setorial_pp": max_share_error}


def adjusted_positions(values: dict[str, float], lower: float, upper: float) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: item[1])
    placed: list[list[object]] = []
    for sector, value in ordered:
        position = max(value, lower, float(placed[-1][1]) + 3.0 if placed else lower)
        placed.append([sector, position])
    overflow = max(0.0, float(placed[-1][1]) - upper)
    for item in placed:
        item[1] = float(item[1]) - overflow
    for index in range(len(placed) - 2, -1, -1):
        placed[index][1] = min(float(placed[index][1]), float(placed[index + 1][1]) - 3.0)
    underflow = max(0.0, lower - float(placed[0][1]))
    return {str(sector): float(position) + underflow for sector, position in placed}


def render(data: pd.DataFrame) -> None:
    maximum = float(data["participacao_verde_estrito_pct"].max())
    axis_max = min(100.0, max(50.0, math.ceil((maximum + 5.0) / 10.0) * 10.0))
    mpl.rcParams.update({"font.family": FONT, "font.size": 9.0, "axes.unicode_minus": False,
                         "figure.facecolor": WHITE, "savefig.facecolor": WHITE})
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 4.75), sharex=True, sharey=True)
    fig.subplots_adjust(left=0.087, right=0.975, top=0.91, bottom=0.205, wspace=0.18)
    for ax, universe in zip(axes, UNIVERSES):
        selected = data.loc[data["universo"] == universe]
        endpoints: dict[str, float] = {}
        for sector in SECTORS:
            series = selected.loc[selected["setor_bndes"] == sector].sort_values("ano")
            style = STYLES[sector]
            ax.plot(series["ano"], series["participacao_verde_estrito_pct"], color=style["color"],
                    linestyle=style["linestyle"], linewidth=1.20, marker=style["marker"], markersize=3.40,
                    markerfacecolor=WHITE, markeredgecolor=style["color"], markeredgewidth=0.82,
                    markevery=[0, 4, 8, 12, 16, 20, 23], label=sector, zorder=3)
            endpoints[sector] = float(series.loc[series["ano"] == 2025, "participacao_verde_estrito_pct"].iloc[0])
        positions = adjusted_positions(endpoints, 2.0, axis_max - 2.0)
        for sector in SECTORS:
            color = STYLES[sector]["color"]
            ax.plot([2025.08, 2025.35], [endpoints[sector], positions[sector]], color=color, linewidth=0.55)
            ax.text(2025.45, positions[sector], pct_br(endpoints[sector]), ha="left", va="center",
                    fontsize=7.3, fontweight="bold", color=color)
        ax.set_xlim(2001.5, 2028.0)
        ax.set_ylim(0, axis_max)
        ax.set_xticks(YEAR_TICKS, [str(year) for year in YEAR_TICKS])
        ax.yaxis.set_major_locator(MultipleLocator(10))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0f}%"))
        ax.tick_params(axis="x", labelsize=8.0, colors=BLACK, length=3.0, width=0.7, pad=5)
        ax.tick_params(axis="y", labelsize=8.0, colors=BLACK, length=0, pad=5)
        ax.grid(axis="y", color=GRID, linewidth=0.5, zorder=0)
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
        for spine in ["left", "bottom"]:
            ax.spines[spine].set_color(BLACK)
            ax.spines[spine].set_linewidth(0.7)
        ax.set_title(PANELS[universe], loc="left", fontsize=11.0, fontweight="bold", color=BLACK, pad=11)
    axes[0].set_ylabel("Participação no total anual do Verde estrito", fontsize=8.5, color=BLACK, labelpad=8)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.035), ncol=4,
               frameon=False, fontsize=7.7, handlelength=3.2, handletextpad=0.55, columnspacing=1.5)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_OUTPUT, dpi=600, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


def render_vertical(data: pd.DataFrame) -> None:
    """Renderiza a alternativa com os dois fluxos empilhados verticalmente."""
    maximum = float(data["participacao_verde_estrito_pct"].max())
    axis_max = min(100.0, max(50.0, math.ceil((maximum + 5.0) / 10.0) * 10.0))
    mpl.rcParams.update({"font.family": FONT, "font.size": 9.0, "axes.unicode_minus": False,
                         "figure.facecolor": WHITE, "savefig.facecolor": WHITE})
    fig, axes = plt.subplots(2, 1, figsize=(7.35, 7.65), sharex=False, sharey=True)
    fig.subplots_adjust(left=0.125, right=0.94, top=0.965, bottom=0.125, hspace=0.24)

    for ax, universe in zip(axes, UNIVERSES):
        selected = data.loc[data["universo"] == universe]
        endpoints: dict[str, float] = {}
        for sector in SECTORS:
            series = selected.loc[selected["setor_bndes"] == sector].sort_values("ano")
            style = STYLES[sector]
            ax.plot(series["ano"], series["participacao_verde_estrito_pct"],
                    color=style["color"], linestyle=style["linestyle"], linewidth=1.20,
                    marker=style["marker"], markersize=3.40, markerfacecolor=WHITE,
                    markeredgecolor=style["color"], markeredgewidth=0.82,
                    markevery=[0, 4, 8, 12, 16, 20, 23], label=sector, zorder=3)
            endpoints[sector] = float(series.loc[
                series["ano"] == 2025, "participacao_verde_estrito_pct"].iloc[0])

        positions = adjusted_positions(endpoints, 2.0, axis_max - 2.0)
        for sector in SECTORS:
            color = STYLES[sector]["color"]
            ax.plot([2025.08, 2025.35], [endpoints[sector], positions[sector]],
                    color=color, linewidth=0.55)
            ax.text(2025.45, positions[sector], pct_br(endpoints[sector]),
                    ha="left", va="center", fontsize=7.3, fontweight="bold", color=color)

        ax.set_xlim(2001.5, 2028.0)
        ax.set_ylim(0, axis_max)
        ax.set_xticks(YEAR_TICKS, [str(year) for year in YEAR_TICKS])
        ax.yaxis.set_major_locator(MultipleLocator(10))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0f}%"))
        ax.tick_params(axis="x", labelsize=8.0, colors=BLACK, length=3.0, width=0.7, pad=5)
        ax.tick_params(axis="y", labelsize=8.0, colors=BLACK, length=0, pad=5)
        ax.grid(axis="y", color=GRID, linewidth=0.5, zorder=0)
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
        for spine in ["left", "bottom"]:
            ax.spines[spine].set_color(BLACK)
            ax.spines[spine].set_linewidth(0.7)
        ax.set_title(PANELS[universe], loc="left", fontsize=10.8,
                     fontweight="bold", color=BLACK, pad=9)

    fig.supylabel("Participação no total anual do Verde estrito", x=0.035,
                  fontsize=8.5, color=BLACK)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.025),
               ncol=4, frameon=False, fontsize=7.25, handlelength=3.0,
               handletextpad=0.5, columnspacing=1.15)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_OUTPUT_VERTICAL, dpi=600, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


def main() -> None:
    for directory in (DATA_DIR, FIG_DIR, QA_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    data, checks = prepare()
    data.to_csv(DATA_OUTPUT, index=False, encoding="utf-8-sig")
    render(data)
    render_vertical(data)
    payload = {"status": "aprovado_tecnicamente_para_validacao_visual", "periodo": "2002-2025",
               "universos": UNIVERSES, "setores_bndes": SECTORS, "linhas_analiticas": len(data),
               **checks,
               "participacoes_2025_pct": data.loc[data["ano"] == 2025].pivot(
                   index="setor_bndes", columns="universo", values="participacao_verde_estrito_pct").to_dict(),
               "arquivo_png": str(FIG_OUTPUT.relative_to(ROOT)),
               "arquivo_png_vertical": str(FIG_OUTPUT_VERTICAL.relative_to(ROOT)),
               "arquivo_csv": str(DATA_OUTPUT.relative_to(ROOT))}
    QA_OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
