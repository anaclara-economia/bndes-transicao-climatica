"""Converte VE04 e VE05 para o padrão cartográfico aprovado.

VE04 usa mapas coropléticos estaduais com classes comuns. VE05 combina mapas
de pontos para os Top 10 municípios com listas compactas de identificação.
Os dados permanecem os produzidos e reconciliados pelos scripts 03 e 04.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import geopandas as gpd
import matplotlib as mpl

mpl.use("Agg")
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, LinearSegmentedColormap, ListedColormap, Normalize
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "results"
DATA_DIR = BASE / "tables" / "verde_estrito"
FIG_DIR = BASE / "figures" / "verde_estrito"
GEO_DIR = ROOT / "data" / "external" / "ibge_2024"
QA_DIR = BASE / "metadata" / "qa" / "verde_estrito"

VE04_DATA = DATA_DIR / "VE04_distribuicao_uf_verde_estrito_2002_2025.csv"
VE05_DATA = DATA_DIR / "VE05_top10_municipios_verde_estrito_2002_2025_e_2025.csv"
VE04_OUTPUT = FIG_DIR / "VE04_distribuicao_uf_verde_estrito_2002_2025.png"
VE05_OUTPUT = FIG_DIR / "VE05_top10_municipios_verde_estrito_2002_2025_e_2025.png"
VE04_QA = QA_DIR / "validacao_ve04_distribuicao_uf.json"
VE05_QA = QA_DIR / "validacao_ve05_top10_municipios.json"

PANEL_DESEMBOLSOS = "A. Desembolsos realizados"
PANEL_CONTRATADO = "B. Valor contratado"
VE04_PANELS = [PANEL_DESEMBOLSOS, PANEL_CONTRATADO]
VE05_PANELS = [
    "A. Desembolsos — média anual, 2002–2025",
    "B. Desembolsos — 2025",
    "C. Valor contratado — média anual, 2002–2025",
    "D. Valor contratado — 2025",
]
VE05_PANEL_TITLES = {
    "A. Desembolsos — média anual, 2002–2025": "A. Desembolsos\nMédia anual, 2002–2025",
    "B. Desembolsos — 2025": "B. Desembolsos\n2025",
    "C. Valor contratado — média anual, 2002–2025": "C. Valor contratado\nMédia anual, 2002–2025",
    "D. Valor contratado — 2025": "D. Valor contratado\n2025",
}

FONT = "Times New Roman"
TEXT = "#171717"
BORDER = "#77736C"
BASE_FILL = "#F7F4EC"
WHITE = "#FFFFFF"

CLASS_LABELS = ["0%", ">0–1%", ">1–5%", ">5–10%", ">10–20%", ">20%"]
CLASS_COLORS = [
    "#F7F4EC",
    "#FFF7BC",
    "#FEC44F",
    "#FE9929",
    "#D95F0E",
    "#8C2D04",
]
CLASS_CMAP = ListedColormap(CLASS_COLORS, name="verde_estrito_territorial_classes")
CLASS_NORM = BoundaryNorm(np.arange(-0.5, 6.5, 1.0), CLASS_CMAP.N)
POINT_CMAP = LinearSegmentedColormap.from_list(
    "verde_estrito_municipios",
    ["#FFF7BC", "#FEC44F", "#FE9929", "#D95F0E", "#8C2D04"],
)

LABEL_OFFSETS = {
    "DF": (1.55, 0.20),
    "ES": (1.40, -0.05),
    "RJ": (1.30, -0.55),
    "SE": (1.50, -0.10),
    "AL": (1.45, 0.30),
    "PB": (1.45, 0.55),
    "RN": (1.15, 0.65),
}


mpl.rcParams.update(
    {
        "font.family": FONT,
        "font.size": 9.0,
        "axes.facecolor": WHITE,
        "figure.facecolor": WHITE,
        "savefig.facecolor": WHITE,
        "axes.unicode_minus": False,
    }
)


def load_states() -> gpd.GeoDataFrame:
    states = gpd.read_file(
        GEO_DIR / "ibge_ufs_2024_simplificado_epsg4674.gpkg",
        layer="ufs_2024",
        engine="pyogrio",
    ).to_crs(4674)
    states["code_state"] = states["code_state"].astype(int)
    states["abbrev_state"] = states["abbrev_state"].astype(str).str.upper()
    if len(states) != 27 or states["abbrev_state"].nunique() != 27:
        raise AssertionError("A malha estadual deve conter as 27 UFs")
    if not states.geometry.is_valid.all():
        raise AssertionError("A malha estadual contém geometria inválida")
    return states


def state_representative_points(states: gpd.GeoDataFrame) -> dict[str, tuple[float, float]]:
    projected = states.to_crs(5880)
    points = gpd.GeoSeries(projected.geometry.representative_point(), crs=5880).to_crs(4674)
    return {
        uf: (float(point.x), float(point.y))
        for uf, point in zip(states["abbrev_state"], points)
    }


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


def render_ve04(states: gpd.GeoDataFrame) -> dict[str, object]:
    data = pd.read_csv(VE04_DATA)
    data = data.loc[data["tipo_linha"] == "UF"].copy()
    if len(data) != 54 or data.groupby("painel")["territorio"].nunique().ne(27).any():
        raise AssertionError("VE04 deve conter 27 UFs em cada painel")
    data["classe_id"] = data["participacao_pct"].map(class_id)
    points = state_representative_points(states)

    fig, axes = plt.subplots(1, 2, figsize=(8.6, 4.75))
    for ax, panel in zip(axes, VE04_PANELS):
        selected = data.loc[data["painel"] == panel].copy()
        gdf = states.merge(
            selected[["territorio", "participacao_pct", "classe_id"]],
            left_on="abbrev_state",
            right_on="territorio",
            how="left",
            validate="one_to_one",
        )
        if gdf["participacao_pct"].isna().any():
            raise AssertionError(f"UF sem valor em VE04: {panel}")
        gdf.plot(
            column="classe_id",
            cmap=CLASS_CMAP,
            norm=CLASS_NORM,
            linewidth=0.48,
            edgecolor=BORDER,
            ax=ax,
        )
        values = dict(zip(gdf["abbrev_state"], gdf["participacao_pct"]))
        classes = dict(zip(gdf["abbrev_state"], gdf["classe_id"]))
        for uf, (x, y) in points.items():
            dx, dy = LABEL_OFFSETS.get(uf, (0.0, 0.0))
            tx, ty = x + dx, y + dy
            if uf in LABEL_OFFSETS:
                ax.plot([x, tx - 0.08], [y, ty], color=BORDER, linewidth=0.38, zorder=5)
            dark = int(classes[uf]) >= 4
            label = ax.text(
                tx,
                ty,
                uf,
                ha="center",
                va="center",
                fontsize=6.1,
                fontweight="bold",
                color=WHITE if dark else TEXT,
                zorder=6,
            )
            label.set_path_effects(
                [path_effects.withStroke(linewidth=0.75, foreground="#7A2505" if dark else WHITE)]
            )
        ax.set_axis_off()
        ax.set_title(panel, loc="left", fontsize=11.2, fontweight="bold", color=TEXT, pad=3.5)

    handles = [
        Patch(facecolor=color, edgecolor=BORDER, linewidth=0.45, label=label)
        for color, label in zip(CLASS_COLORS, CLASS_LABELS)
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.015),
        ncol=6,
        frameon=False,
        fontsize=8.4,
        handlelength=1.45,
        columnspacing=1.35,
    )
    fig.subplots_adjust(left=0.018, right=0.985, top=0.965, bottom=0.105, wspace=0.015)
    VE04_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(VE04_OUTPUT, dpi=600, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)

    class_counts = (
        data.groupby(["painel", "classe_id"]).size().unstack(fill_value=0).to_dict(orient="index")
    )
    return {"classes_por_painel": class_counts, "ufs_por_painel": {panel: 27 for panel in VE04_PANELS}}


def load_municipality_points() -> gpd.GeoDataFrame:
    municipalities = gpd.read_file(
        GEO_DIR / "ibge_municipios_2024_simplificado_epsg4674.gpkg",
        layer="municipios_2024",
        engine="pyogrio",
    ).to_crs(4674)
    municipalities["codigo_municipio"] = municipalities["code_muni"].astype("int64").astype(str).str.zfill(7)
    projected = municipalities.to_crs(5880)
    points = gpd.GeoDataFrame(
        municipalities[["codigo_municipio"]].copy(),
        geometry=projected.geometry.representative_point(),
        crs=5880,
    ).to_crs(4674)
    if points["codigo_municipio"].duplicated().any():
        raise AssertionError("A malha municipal contém códigos duplicados")
    return points


def pct_br(value: float) -> str:
    return f"{value:.1f}%".replace(".", ",")


def repel_coordinates(
    x_values: np.ndarray,
    y_values: np.ndarray,
    bounds: np.ndarray,
    minimum_distance: float = 0.040,
) -> tuple[np.ndarray, np.ndarray]:
    """Afasta símbolos coincidentes e mantém a posição real como âncora.

    O algoritmo opera em coordenadas normalizadas para respeitar a proporção
    do mapa. As linhas-guia desenhadas posteriormente preservam a referência
    geográfica de cada município deslocado.
    """
    min_x, min_y, max_x, max_y = [float(value) for value in bounds]
    width = max_x - min_x
    height = max_y - min_y
    x_norm = (x_values.astype(float) - min_x) / width
    y_norm = (y_values.astype(float) - min_y) / height

    for iteration in range(180):
        changed = False
        for left in range(len(x_norm)):
            for right in range(left + 1, len(x_norm)):
                dx = x_norm[left] - x_norm[right]
                dy = y_norm[left] - y_norm[right]
                distance = math.hypot(dx, dy)
                if distance >= minimum_distance:
                    continue
                if distance < 1e-9:
                    angle = math.radians((left * 47 + right * 71 + iteration) % 360)
                    dx, dy, distance = math.cos(angle), math.sin(angle), 1.0
                push = (minimum_distance - distance) / 2.0 + 0.0004
                x_norm[left] += dx / distance * push
                y_norm[left] += dy / distance * push
                x_norm[right] -= dx / distance * push
                y_norm[right] -= dy / distance * push
                changed = True
        x_norm = np.clip(x_norm, -0.015, 1.015)
        y_norm = np.clip(y_norm, -0.015, 1.015)
        if not changed:
            break
    return min_x + x_norm * width, min_y + y_norm * height


def render_ve05(states: gpd.GeoDataFrame) -> dict[str, object]:
    ranking = pd.read_csv(VE05_DATA, dtype={"codigo_municipio": str})
    ranking["codigo_municipio"] = ranking["codigo_municipio"].str.zfill(7)
    if len(ranking) != 40 or ranking.groupby("painel").size().ne(10).any():
        raise AssertionError("VE05 deve conter dez municípios em cada painel")
    points = load_municipality_points()
    ranking = ranking.merge(points, on="codigo_municipio", how="left", validate="many_to_one")
    if ranking.geometry.isna().any():
        raise AssertionError("Município ranqueado sem ponto cartográfico")
    ranking = gpd.GeoDataFrame(ranking, geometry="geometry", crs=4674)

    maximum = float(ranking["participacao_total_pct"].max())
    norm = Normalize(vmin=0.0, vmax=maximum)
    map_bounds = states.total_bounds
    fig = plt.figure(figsize=(11.2, 8.3))
    outer = fig.add_gridspec(2, 2, left=0.025, right=0.985, top=0.975, bottom=0.105, wspace=0.12, hspace=0.20)

    for index, panel in enumerate(VE05_PANELS):
        inner = outer[index // 2, index % 2].subgridspec(
            2,
            2,
            height_ratios=[0.13, 0.87],
            width_ratios=[1.38, 1.0],
            hspace=0.01,
            wspace=0.015,
        )
        title_ax = fig.add_subplot(inner[0, :])
        map_ax = fig.add_subplot(inner[1, 0])
        list_ax = fig.add_subplot(inner[1, 1])
        selected = ranking.loc[ranking["painel"] == panel].sort_values("posicao").copy()

        title_ax.set_axis_off()
        title_ax.text(
            0.0,
            0.55,
            panel,
            ha="left",
            va="center",
            fontsize=9.7,
            fontweight="bold",
            color=TEXT,
        )

        states.plot(ax=map_ax, facecolor=BASE_FILL, edgecolor=BORDER, linewidth=0.42)
        sizes = 34.0 + 72.0 * np.sqrt(selected["participacao_total_pct"] / maximum)
        colors = POINT_CMAP(norm(selected["participacao_total_pct"].to_numpy()))
        anchor_x = selected.geometry.x.to_numpy(dtype=float)
        anchor_y = selected.geometry.y.to_numpy(dtype=float)
        display_x, display_y = repel_coordinates(anchor_x, anchor_y, map_bounds)
        for x0, y0, x1, y1 in zip(anchor_x, anchor_y, display_x, display_y):
            normalized_shift = math.hypot(
                (x1 - x0) / (map_bounds[2] - map_bounds[0]),
                (y1 - y0) / (map_bounds[3] - map_bounds[1]),
            )
            if normalized_shift > 0.003:
                map_ax.plot([x0, x1], [y0, y1], color=BORDER, linewidth=0.42, zorder=4)
        map_ax.scatter(
            display_x,
            display_y,
            s=sizes,
            c=colors,
            edgecolors=TEXT,
            linewidths=0.55,
            alpha=0.94,
            zorder=5,
        )
        for row, color, x_position, y_position in zip(
            selected.itertuples(index=False), colors, display_x, display_y
        ):
            luminance = 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]
            label_color = WHITE if luminance < 0.52 else TEXT
            map_ax.text(
                x_position,
                y_position,
                str(int(row.posicao)),
                ha="center",
                va="center",
                fontsize=5.6,
                fontweight="bold",
                color=label_color,
                zorder=6,
            )
        map_ax.set_axis_off()

        list_ax.set_axis_off()
        list_ax.text(0.0, 0.985, "Município (UF)", ha="left", va="top", fontsize=7.2, fontweight="bold", color=TEXT)
        list_ax.text(0.99, 0.985, "%", ha="right", va="top", fontsize=7.2, fontweight="bold", color=TEXT)
        for position, row in enumerate(selected.itertuples(index=False), start=1):
            y = 0.905 - (position - 1) * 0.086
            list_ax.text(
                0.0,
                y,
                f"{int(row.posicao)}. {row.municipio} ({row.uf})",
                ha="left",
                va="center",
                fontsize=6.55,
                color=TEXT,
            )
            list_ax.text(
                0.99,
                y,
                pct_br(float(row.participacao_total_pct)),
                ha="right",
                va="center",
                fontsize=6.55,
                fontweight="bold",
                color=TEXT,
            )
        list_ax.set_xlim(0, 1)
        list_ax.set_ylim(0, 1)

    cax = fig.add_axes([0.25, 0.047, 0.50, 0.020])
    scalar = mpl.cm.ScalarMappable(norm=norm, cmap=POINT_CMAP)
    scalar.set_array([])
    ticks = np.linspace(0, maximum, 5)
    colorbar = fig.colorbar(scalar, cax=cax, orientation="horizontal", ticks=ticks)
    colorbar.set_label("Participação no total do Verde estrito (%)", fontsize=8.4, color=TEXT)
    colorbar.ax.tick_params(labelsize=7.4, length=2.3, color=BORDER)
    colorbar.outline.set_edgecolor(BORDER)
    colorbar.outline.set_linewidth(0.5)
    colorbar.formatter = FuncFormatter(lambda value, _: f"{value:.1f}".replace(".", ","))
    colorbar.update_ticks()

    VE05_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(VE05_OUTPUT, dpi=600, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    return {
        "municipios_por_painel": ranking.groupby("painel").size().astype(int).to_dict(),
        "participacao_minima_pct": float(ranking["participacao_total_pct"].min()),
        "participacao_maxima_pct": maximum,
    }


def update_qa(path: Path, updates: dict[str, object]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(updates)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    states = load_states()
    ve04 = render_ve04(states)
    ve05 = render_ve05(states)
    update_qa(
        VE04_QA,
        {
            "tipo_visualizacao": "mapa coroplético estadual em dois painéis",
            "classes_cartograficas": CLASS_LABELS,
            "paleta": CLASS_COLORS,
            "validacao_cartografica": ve04,
        },
    )
    update_qa(
        VE05_QA,
        {
            "tipo_visualizacao": "mapas municipais de pontos em quatro painéis com ranking lateral",
            "paleta": "sequencial amarelo-laranja-vermelho",
            "validacao_cartografica": ve05,
        },
    )
    print(json.dumps({"VE04": ve04, "VE05": ve05}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
