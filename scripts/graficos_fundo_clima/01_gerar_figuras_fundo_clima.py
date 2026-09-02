"""Produz as cinco figuras sintéticas do Programa Fundo Clima (2013–2025).

O recorte é identificado diretamente pelo instrumento financeiro
``PROGRAMA FUNDO CLIMA``. Desembolsos e valor contratado são mantidos como
universos independentes; para contratações, somam-se operações automáticas e
subcréditos não automáticos.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

import duckdb
import geopandas as gpd
import matplotlib as mpl

mpl.use("Agg")
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MultipleLocator
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "results"
DB_PATH = ROOT / "data" / "local" / "bndes_governanca_v1.duckdb"
GEO_PATH = ROOT / "data" / "external" / "ibge_2024" / "ibge_ufs_2024_simplificado_epsg4674.gpkg"
DATA_DIR = BASE / "tables" / "fundo_clima"
FIG_DIR = BASE / "figures" / "fundo_clima"
QA_DIR = BASE / "metadata" / "qa" / "fundo_clima"
GOV_DIR = BASE / "metadata" / "fundo_clima"

YEARS = list(range(2013, 2026))
YEAR_TICKS = [2013, 2015, 2017, 2019, 2021, 2023, 2025]
UNIVERSES = ["Desembolsos", "Contratações"]
PANEL_TITLES = {
    "Desembolsos": "A. Desembolsos realizados",
    "Contratações": "B. Valor contratado",
}
SERIES_STYLE = {
    "Desembolsos": {"color": "#1D252C", "linestyle": "solid", "marker": "o"},
    "Contratações": {"color": "#59616A", "linestyle": (0, (5, 2.2)), "marker": "s"},
}
SECTOR_ORDER = ["Agropecuária", "Comércio e Serviços", "Indústria", "Infraestrutura"]
SECTOR_STYLE = {
    "Agropecuária": {"color": "#79A6A3", "linestyle": "solid", "marker": "o"},
    "Comércio e Serviços": {"color": "#D2A24C", "linestyle": (0, (4, 2)), "marker": "s"},
    "Indústria": {"color": "#5B7EA4", "linestyle": (0, (5, 1.7, 1.1, 1.7)), "marker": "D"},
    "Infraestrutura": {"color": "#A65A4C", "linestyle": (0, (1.2, 1.8)), "marker": "^"},
    "Sem classificação setorial": {"color": "#B4B9BD", "linestyle": (0, (1, 1)), "marker": "x"},
}
FONT = "Arial"
INK = "#202A33"
GRID = "#DCE1E5"
WHITE = "#FFFFFF"
MAP_COLORS = ["#F7F4EC", "#FFF7BC", "#FEE391", "#FEC44F", "#FE9929", "#CC4C02"]
MAP_LABELS = ["0%", ">0–1%", ">1–5%", ">5–10%", ">10–20%", ">20%"]


SQL = """
WITH todos AS (
    SELECT 'Desembolsos' AS universo, ano, produto_bndes, instrumento_financeiro,
           setor_bndes, uf, codigo_municipio, geografia_valida,
           CAST(valor_desembolso_real_jun2026 AS DOUBLE) AS valor_real,
           indicador_verde_estrito
    FROM core_bndes.fato_desembolso_mensal
    WHERE ano BETWEEN 2013 AND 2025

    UNION ALL

    SELECT 'Contratações', ano, produto_bndes, instrumento_financeiro,
           setor_bndes, uf, codigo_municipio, geografia_valida,
           CAST(valor_contratado_real_jun2026 AS DOUBLE), indicador_verde_estrito
    FROM core_bndes.fato_operacao_automatica
    WHERE ano BETWEEN 2013 AND 2025

    UNION ALL

    SELECT 'Contratações', ano, produto_bndes, instrumento_financeiro,
           setor_bndes, uf, codigo_municipio, geografia_valida,
           CAST(valor_contratado_real_jun2026 AS DOUBLE), indicador_verde_estrito
    FROM core_bndes.fato_subcredito_nao_automatico
    WHERE ano BETWEEN 2013 AND 2025
)
SELECT * FROM todos
"""


def fold_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", "" if value is None else str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
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


def fmt_pt(value: float, decimals: int = 1) -> str:
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def apply_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": FONT,
            "font.size": 9,
            "axes.unicode_minus": False,
            "figure.facecolor": WHITE,
            "savefig.facecolor": WHITE,
        }
    )


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        raw = con.execute(SQL).fetchdf()
    raw["ano"] = raw["ano"].astype(int)
    raw["instrumento_norm"] = raw["instrumento_financeiro"].map(fold_text)
    fund = raw.loc[raw["instrumento_norm"].eq("PROGRAMA FUNDO CLIMA")].copy()
    if fund.empty:
        raise AssertionError("Programa Fundo Clima não encontrado nas tabelas-fato.")

    annual_fund = (
        fund.groupby(["universo", "ano"], as_index=False)["valor_real"].sum()
        .rename(columns={"valor_real": "valor_fundo_clima_real_jun2026"})
    )
    annual_green = (
        raw.loc[raw["indicador_verde_estrito"]]
        .groupby(["universo", "ano"], as_index=False)["valor_real"].sum()
        .rename(columns={"valor_real": "valor_verde_estrito_real_jun2026"})
    )
    calendar = pd.MultiIndex.from_product([UNIVERSES, YEARS], names=["universo", "ano"]).to_frame(index=False)
    annual = calendar.merge(annual_fund, on=["universo", "ano"], how="left").merge(
        annual_green, on=["universo", "ano"], how="left"
    )
    annual["valor_fundo_clima_real_jun2026"] = annual["valor_fundo_clima_real_jun2026"].fillna(0.0)
    annual["valor_verde_estrito_real_jun2026"] = annual["valor_verde_estrito_real_jun2026"].fillna(0.0)
    if (annual["valor_verde_estrito_real_jun2026"] <= 0).any():
        raise AssertionError("Há ano sem denominador Verde estrito.")
    annual["participacao_no_verde_estrito_pct"] = (
        annual["valor_fundo_clima_real_jun2026"]
        / annual["valor_verde_estrito_real_jun2026"]
        * 100
    )
    if not annual["participacao_no_verde_estrito_pct"].between(0, 100).all():
        raise AssertionError("Participação do Fundo Clima fora de 0–100%.")
    for universe in UNIVERSES:
        mask = annual["universo"].eq(universe)
        base = float(annual.loc[mask & annual["ano"].eq(2013), "valor_fundo_clima_real_jun2026"].iloc[0])
        if base <= 0:
            raise AssertionError(f"Base 2013 nula para {universe}.")
        annual.loc[mask, "indice_2013_100"] = annual.loc[mask, "valor_fundo_clima_real_jun2026"] / base * 100
    return annual, fund


def base_axes(ax: plt.Axes, *, y_percent: bool = False) -> None:
    ax.grid(axis="y", color=GRID, linewidth=0.55, zorder=0)
    ax.grid(axis="x", visible=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(INK)
    ax.spines[["left", "bottom"]].set_linewidth(0.72)
    ax.tick_params(axis="x", labelsize=8.2, colors=INK, length=3, width=0.7, pad=5)
    ax.tick_params(axis="y", labelsize=8.2, colors=INK, length=0, pad=5)
    if y_percent:
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0f}%"))


def render_fc01(annual: pd.DataFrame) -> Path:
    apply_style()
    ymax = max(5, math.ceil(float(annual["participacao_no_verde_estrito_pct"].max()) / 10) * 10 + 5)
    fig, axes = plt.subplots(1, 2, figsize=(9.25, 4.6), sharey=True)
    fig.subplots_adjust(left=0.09, right=0.985, top=0.92, bottom=0.15, wspace=0.15)
    for ax, universe in zip(axes, UNIVERSES):
        part = annual.loc[annual["universo"].eq(universe)].sort_values("ano")
        style = SERIES_STYLE[universe]
        ax.plot(part["ano"], part["participacao_no_verde_estrito_pct"], color=style["color"],
                linestyle=style["linestyle"], linewidth=1.55, marker=style["marker"], markersize=4.5,
                markerfacecolor=WHITE, markeredgewidth=1.0, zorder=3)
        last = part.iloc[-1]
        peak = part.loc[part["participacao_no_verde_estrito_pct"].idxmax()]
        for point, text, dy in ((last, fmt_pt(float(last["participacao_no_verde_estrito_pct"])) + "%", 0.035),
                                (peak, fmt_pt(float(peak["participacao_no_verde_estrito_pct"])) + "%", 0.035)):
            ax.annotate(text, (point["ano"], point["participacao_no_verde_estrito_pct"]),
                        xytext=(0, ymax * dy), textcoords="offset points", ha="center", va="bottom",
                        fontsize=8.3, fontweight="bold", color=style["color"])
        ax.set_title(PANEL_TITLES[universe], loc="left", fontsize=11.2, fontweight="bold", color=INK, pad=11)
        ax.set_xlim(2012.6, 2025.45)
        ax.set_ylim(0, ymax)
        ax.set_xticks(YEAR_TICKS)
        ax.set_xticklabels([str(year) for year in YEAR_TICKS])
        base_axes(ax, y_percent=True)
    fig.supylabel("Participação no Verde estrito", x=0.02, fontsize=8.7, color=INK)
    output = FIG_DIR / "FC01_participacao_anual_fundo_clima_no_verde_estrito_2013_2025.png"
    fig.savefig(output, dpi=600, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    return output


def annotate_final_values(ax: plt.Axes, data: pd.DataFrame, column: str, *, decimals: int = 1) -> None:
    for universe in UNIVERSES:
        part = data.loc[data["universo"].eq(universe)].sort_values("ano")
        style = SERIES_STYLE[universe]
        point = part.iloc[-1]
        value = float(point[column])
        # Rótulos curtos, dentro da área útil, ao lado do ponto final.
        xoffset, yoffset = (7, -13) if universe == "Desembolsos" else (7, 7)
        ax.annotate(
            fmt_pt(value, decimals),
            (int(point["ano"]), value),
            xytext=(xoffset, yoffset),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=7.6,
            fontweight="bold",
            color=style["color"],
        )


def render_fc02(annual: pd.DataFrame) -> Path:
    apply_style()
    plot = annual.copy()
    plot["valor_bilhoes"] = plot["valor_fundo_clima_real_jun2026"] / 1_000_000_000
    value_max = float(plot["valor_bilhoes"].max()) * 1.18
    index_max = float(plot["indice_2013_100"].max()) * 1.18
    fig, axes = plt.subplots(1, 2, figsize=(9.25, 4.6))
    # A legenda é uma informação comum aos dois painéis: reservamos uma faixa
    # própria abaixo deles para impedir que invada a área de desenho.
    fig.subplots_adjust(left=0.075, right=0.985, top=0.86, bottom=0.27, wspace=0.24)
    specs = [
        (axes[0], "valor_bilhoes", "A. Valor real", "R$ bilhões, a preços de junho de 2026", value_max,
         lambda value: "0" if value == 0 else fmt_pt(value, 0)),
        (axes[1], "indice_2013_100", "B. Índice de evolução", "Índice (2013 = 100)", index_max,
         lambda value: fmt_pt(value, 0)),
    ]
    handles = []
    for ax, column, title, subtitle, ymax, formatter in specs:
        for universe in UNIVERSES:
            part = plot.loc[plot["universo"].eq(universe)].sort_values("ano")
            style = SERIES_STYLE[universe]
            ax.plot(part["ano"], part[column], color=style["color"], linestyle=style["linestyle"],
                    linewidth=1.45, marker=style["marker"], markersize=4.0, markerfacecolor=WHITE,
                    markeredgewidth=0.9, label=PANEL_TITLES[universe][3:], zorder=3)
            if ax is axes[0]:
                handles.append(Line2D([0], [0], color=style["color"], linestyle=style["linestyle"],
                                      marker=style["marker"], markerfacecolor=WHITE, label=PANEL_TITLES[universe][3:]))
        if column == "valor_bilhoes":
            annotate_final_values(ax, plot, column, decimals=1)
        else:
            annotate_final_values(ax, plot, column, decimals=0)
        ax.set_title(title, loc="left", fontsize=11.2, fontweight="bold", color=INK, pad=22)
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, ha="left", va="bottom", fontsize=8.4, color="#59636C")
        ax.set_xlim(2012.6, 2025.45)
        ax.set_ylim(0, ymax)
        ax.set_xticks(YEAR_TICKS)
        ax.set_xticklabels([str(year) for year in YEAR_TICKS])
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: formatter(value)))
        base_axes(ax)
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.015), ncol=2,
               frameon=False, fontsize=8.0, handlelength=2.8, columnspacing=2.0)
    output = FIG_DIR / "FC02_evolucao_e_indice_fundo_clima_2013_2025.png"
    fig.savefig(output, dpi=600, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    return output


def render_fc03(fund: pd.DataFrame) -> tuple[Path, pd.DataFrame]:
    apply_style()
    data = fund.groupby(["universo", "produto_bndes"], as_index=False)["valor_real"].sum()
    data["produto_bndes"] = data["produto_bndes"].fillna("Produto não informado")
    data["participacao_pct"] = data["valor_real"] / data.groupby("universo")["valor_real"].transform("sum") * 100
    data["valor_bilhoes"] = data["valor_real"] / 1_000_000_000
    # Painéis verticais evitam que os nomes dos produtos do painel direito se
    # sobreponham ao painel esquerdo em uma composição com poucas categorias.
    fig, axes = plt.subplots(2, 1, figsize=(8.7, 5.8))
    fig.subplots_adjust(left=0.30, right=0.97, top=0.93, bottom=0.10, hspace=0.48)
    for ax, universe in zip(axes, UNIVERSES):
        part = data.loc[data["universo"].eq(universe)].sort_values("valor_real").reset_index(drop=True)
        y = np.arange(len(part))
        bars = ax.barh(y, part["valor_bilhoes"], color="#17365D", edgecolor="#17365D", height=0.56)
        for bar, row in zip(bars, part.itertuples(index=False)):
            ax.text(bar.get_width() + max(float(part["valor_bilhoes"].max()) * 0.02, 0.02), bar.get_y() + bar.get_height() / 2,
                    f"{fmt_pt(float(row.valor_bilhoes))}  ({fmt_pt(float(row.participacao_pct))}%)",
                    va="center", ha="left", fontsize=7.5, color=INK)
        ax.set_yticks(y)
        ax.set_yticklabels(part["produto_bndes"], fontsize=8.2, color=INK)
        ax.set_xlim(0, float(part["valor_bilhoes"].max()) * 1.24)
        ax.set_title(PANEL_TITLES[universe], loc="left", fontsize=11.2, fontweight="bold", color=INK, pad=11)
        ax.set_xlabel("R$ bilhões acumulados", fontsize=8.3, color=INK, labelpad=8)
        ax.grid(axis="x", color=GRID, linewidth=0.55, zorder=0)
        ax.grid(axis="y", visible=False)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.spines["bottom"].set_color(INK)
        ax.tick_params(axis="y", length=0, pad=5)
        ax.tick_params(axis="x", labelsize=8.0, colors=INK, length=3, width=0.7)
    output = FIG_DIR / "FC03_composicao_operacional_fundo_clima_produto_bndes_2013_2025.png"
    fig.savefig(output, dpi=600, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    return output, data.sort_values(["universo", "valor_real"], ascending=[True, False])


def prepare_sectors(fund: pd.DataFrame, annual: pd.DataFrame) -> pd.DataFrame:
    data = fund.copy()
    data["setor_bndes"] = data["setor_bndes"].map(normalize_sector).fillna("Sem classificação setorial")
    sector = data.groupby(["universo", "ano", "setor_bndes"], as_index=False)["valor_real"].sum()
    complete = pd.MultiIndex.from_product([UNIVERSES, YEARS, SECTOR_ORDER], names=["universo", "ano", "setor_bndes"]).to_frame(index=False)
    sector = complete.merge(sector, on=["universo", "ano", "setor_bndes"], how="left").fillna({"valor_real": 0.0})
    unknown = data.loc[data["setor_bndes"].eq("Sem classificação setorial")].groupby(["universo", "ano"], as_index=False)["valor_real"].sum()
    if not unknown.empty and float(unknown["valor_real"].sum()) > 0:
        unknown["setor_bndes"] = "Sem classificação setorial"
        sector = pd.concat([sector, unknown], ignore_index=True)
    sector = sector.merge(annual[["universo", "ano", "valor_fundo_clima_real_jun2026"]], on=["universo", "ano"], how="left")
    sector["participacao_pct"] = sector["valor_real"] / sector["valor_fundo_clima_real_jun2026"] * 100
    check = sector.groupby(["universo", "ano"])["valor_real"].sum().reset_index().merge(
        annual[["universo", "ano", "valor_fundo_clima_real_jun2026"]], on=["universo", "ano"]
    )
    if not np.allclose(check["valor_real"], check["valor_fundo_clima_real_jun2026"], atol=0.10):
        raise AssertionError("Setores não reconciliam com o Fundo Clima.")
    return sector


def render_fc04(sector: pd.DataFrame) -> Path:
    apply_style()
    active = [item for item in SECTOR_ORDER + ["Sem classificação setorial"] if item in set(sector["setor_bndes"])]
    # Em vez de linhas que se cruzam fortemente em anos de alta concentração,
    # usamos barras empilhadas de 100%: a pergunta é de composição setorial.
    fig, axes = plt.subplots(1, 2, figsize=(9.25, 4.8), sharex=True, sharey=True)
    fig.subplots_adjust(left=0.09, right=0.985, top=0.90, bottom=0.25, wspace=0.16)
    for ax, universe in zip(axes, UNIVERSES):
        bottom = np.zeros(len(YEARS), dtype=float)
        for category in active:
            part = sector.loc[(sector["universo"].eq(universe)) & (sector["setor_bndes"].eq(category))].sort_values("ano")
            style = SECTOR_STYLE[category]
            values = part.set_index("ano").reindex(YEARS)["participacao_pct"].fillna(0).to_numpy()
            ax.bar(YEARS, values, bottom=bottom, width=0.74, color=style["color"],
                   edgecolor=WHITE, linewidth=0.35, label=category, zorder=3)
            bottom += values
        ax.set_title(PANEL_TITLES[universe], loc="left", fontsize=11.2, fontweight="bold", color=INK, pad=11)
        ax.set_xlim(2012.35, 2025.65)
        ax.set_ylim(0, 100)
        ax.set_xticks(YEAR_TICKS)
        ax.set_xticklabels([str(year) for year in YEAR_TICKS])
        base_axes(ax, y_percent=True)
    fig.supylabel("Participação no total anual do Fundo Clima", x=0.02, fontsize=8.7, color=INK)
    handles = [Patch(facecolor=SECTOR_STYLE[item]["color"], edgecolor=WHITE, label=item) for item in active]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.025), ncol=len(active),
               frameon=False, fontsize=7.35, handlelength=2.8, columnspacing=1.15)
    output = FIG_DIR / "FC04_participacao_anual_setor_bndes_fundo_clima_2013_2025.png"
    fig.savefig(output, dpi=600, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    return output


def class_id(value: float) -> int:
    if value <= 0:
        return 0
    if value <= 1:
        return 1
    if value <= 5:
        return 2
    if value <= 10:
        return 3
    if value <= 20:
        return 4
    return 5


IBGE_PREFIX_TO_UF = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}


def uf_from_codigo_municipio(value: object) -> str | None:
    digits = re.sub(r"\\D", "", "" if value is None else str(value))
    return IBGE_PREFIX_TO_UF.get(digits[:2]) if len(digits) >= 2 else None


def render_fc05(fund: pd.DataFrame) -> tuple[Path, pd.DataFrame]:
    apply_style()
    states = gpd.read_file(GEO_PATH, layer="ufs_2024", engine="pyogrio").to_crs(4674)
    states["uf"] = states["abbrev_state"].astype(str).str.upper()
    valid_ufs = set(states["uf"])
    data = fund.copy()
    data["uf"] = data["uf"].fillna("").astype(str).str.upper().str.strip()
    data["uf"] = data["uf"].where(data["uf"].isin(valid_ufs), data["codigo_municipio"].map(uf_from_codigo_municipio))
    # A Figura FC05 é estadual. Portanto, a UF disponível é suficiente para a
    # alocação cartográfica; a validade municipal não é requisito neste nível.
    data["uf_valida"] = data["uf"].isin(valid_ufs)
    grouped = data.loc[data["uf_valida"]].groupby(["universo", "uf"], as_index=False)["valor_real"].sum()
    totals = data.groupby("universo", as_index=False)["valor_real"].sum().rename(columns={"valor_real": "total_fundo"})
    grouped = grouped.merge(totals, on="universo", how="left")
    grouped["participacao_pct"] = grouped["valor_real"] / grouped["total_fundo"] * 100
    grouped["media_anual_milhoes"] = grouped["valor_real"] / 13 / 1_000_000
    grouped["classe"] = grouped["participacao_pct"].map(class_id)
    residual = data.loc[~data["uf_valida"]].groupby("universo", as_index=False)["valor_real"].sum().merge(totals, on="universo")
    residual["residual_pct"] = residual["valor_real"] / residual["total_fundo"] * 100

    cmap = ListedColormap(MAP_COLORS)
    norm = BoundaryNorm(np.arange(-0.5, 6.5, 1), cmap.N)
    fig, axes = plt.subplots(1, 2, figsize=(9.25, 5.2))
    fig.subplots_adjust(left=0.03, right=0.98, top=0.88, bottom=0.17, wspace=0.06)
    for ax, universe in zip(axes, UNIVERSES):
        part = grouped.loc[grouped["universo"].eq(universe), ["uf", "classe"]]
        mapped = states.merge(part, on="uf", how="left").fillna({"classe": 0})
        mapped.plot(ax=ax, column="classe", cmap=cmap, norm=norm, edgecolor="#958F84", linewidth=0.42)
        points = mapped.geometry.representative_point()
        for (_, row), point in zip(mapped.iterrows(), points):
            ax.text(point.x, point.y, row["uf"], ha="center", va="center", fontsize=5.7, color=INK,
                    path_effects=[path_effects.withStroke(linewidth=1.1, foreground=WHITE)])
        ax.set_title(PANEL_TITLES[universe], loc="left", fontsize=11.2, fontweight="bold", color=INK, pad=9)
        ax.set_axis_off()
    legend = [Patch(facecolor=color, edgecolor="#958F84", label=label) for color, label in zip(MAP_COLORS, MAP_LABELS)]
    fig.legend(handles=legend, title="Participação no Fundo Clima", loc="lower center", bbox_to_anchor=(0.5, 0.01),
               ncol=6, frameon=False, fontsize=7.1, title_fontsize=7.5, handlelength=1.2, columnspacing=1.1)
    output = FIG_DIR / "FC05_distribuicao_uf_fundo_clima_2013_2025.png"
    fig.savefig(output, dpi=600, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    residual = residual[["universo", "residual_pct"]]
    return output, grouped.merge(residual, on="universo", how="left")


def main() -> None:
    for folder in (DATA_DIR, FIG_DIR, QA_DIR, GOV_DIR):
        folder.mkdir(parents=True, exist_ok=True)
    annual, fund = load_data()
    sector = prepare_sectors(fund, annual)
    fc01 = render_fc01(annual)
    fc02 = render_fc02(annual)
    fc03, products = render_fc03(fund)
    fc04 = render_fc04(sector)
    fc05, ufs = render_fc05(fund)

    annual.to_csv(DATA_DIR / "FC01_FC02_serie_anual_fundo_clima_2013_2025.csv", index=False, encoding="utf-8-sig")
    products.to_csv(DATA_DIR / "FC03_composicao_operacional_fundo_clima_2013_2025.csv", index=False, encoding="utf-8-sig")
    sector.to_csv(DATA_DIR / "FC04_setores_bndes_fundo_clima_2013_2025.csv", index=False, encoding="utf-8-sig")
    ufs.to_csv(DATA_DIR / "FC05_distribuicao_uf_fundo_clima_2013_2025.csv", index=False, encoding="utf-8-sig")

    qa = {
        "status": "produzido_para_validacao_visual",
        "recorte": "instrumento financeiro: PROGRAMA FUNDO CLIMA",
        "periodo": "2013-2025",
        "indice_base": "2013 = 100",
        "universos_independentes": UNIVERSES,
        "participacao_fundo_clima_no_verde_estrito_min_pct": float(annual["participacao_no_verde_estrito_pct"].min()),
        "participacao_fundo_clima_no_verde_estrito_max_pct": float(annual["participacao_no_verde_estrito_pct"].max()),
        "arquivos_png": [str(path.relative_to(ROOT)) for path in (fc01, fc02, fc03, fc04, fc05)],
    }
    (QA_DIR / "validacao_figuras_fundo_clima.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = {
        "FC01": "Participação anual do Programa Fundo Clima no Verde estrito.",
        "FC02": "Evolução em valores reais e índice com 2013 = 100.",
        "FC03": "Composição operacional por produto BNDES observado.",
        "FC04": "Participação anual por setor BNDES no Programa Fundo Clima.",
        "FC05": "Participação estadual acumulada no Programa Fundo Clima; a média anual em R$ milhões está disponível no CSV.",
        "nota_metodologica": "O programa é identificado no campo instrumento_financeiro. A participação no Verde estrito é Fundo Clima dividido pelo valor anual do respectivo fluxo Verde estrito.",
    }
    (GOV_DIR / "metadados_figuras_fundo_clima.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(qa, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
