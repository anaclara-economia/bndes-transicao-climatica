"""Gera VE07A/B: média anual do Verde estrito por setor do BNDES e UF."""

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
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

getcontext().prec = 50

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "results"
DB_PATH = ROOT / "data" / "local" / "bndes_governanca_v1.duckdb"
GEO_PATH = ROOT / "data" / "external" / "ibge_2024" / "ibge_ufs_2024_simplificado_epsg4674.gpkg"
VE06_DATA = BASE / "tables" / "verde_estrito" / "VE06_participacao_anual_setor_bndes_verde_estrito_2002_2025.csv"
DATA_DIR = BASE / "tables" / "verde_estrito"
FIG_DIR = BASE / "figures" / "verde_estrito"
QA_DIR = BASE / "metadata" / "qa" / "verde_estrito"
DATA_A = DATA_DIR / "VE07A_media_anual_desembolsos_verde_estrito_setor_uf_2002_2025.csv"
DATA_B = DATA_DIR / "VE07B_media_anual_valor_contratado_verde_estrito_setor_uf_2002_2025.csv"
FIG_A = FIG_DIR / "VE07A_media_anual_desembolsos_verde_estrito_setor_uf_2002_2025.png"
FIG_B = FIG_DIR / "VE07B_media_anual_valor_contratado_verde_estrito_setor_uf_2002_2025.png"
QA_OUTPUT = QA_DIR / "validacao_ve07_mapas_setor_uf.json"

N_YEARS = 24
RESIDUAL = "Sem identificação territorial"
UNIVERSES = ["Desembolsos", "Contratações"]
SECTORS = [
    ("Agropecuária", "A. Agropecuária"),
    ("Comércio e Serviços", "B. Comércio e Serviços"),
    ("Indústria", "C. Indústria"),
    ("Infraestrutura", "D. Infraestrutura"),
]

UF_NAME_TO_ABBREV = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM", "BAHIA": "BA",
    "CEARA": "CE", "DISTRITO FEDERAL": "DF", "ESPIRITO SANTO": "ES", "GOIAS": "GO",
    "MARANHAO": "MA", "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS",
    "MINAS GERAIS": "MG", "PARA": "PA", "PARAIBA": "PB", "PARANA": "PR",
    "PERNAMBUCO": "PE", "PIAUI": "PI", "RIO DE JANEIRO": "RJ",
    "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO",
    "RORAIMA": "RR", "SANTA CATARINA": "SC", "SAO PAULO": "SP", "SERGIPE": "SE",
    "TOCANTINS": "TO",
}
VALID_UFS = set(UF_NAME_TO_ABBREV.values())
IBGE_PREFIX_TO_UF = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}

SQL = """
WITH base AS (
 SELECT 'Desembolsos' universo, setor_bndes setor_raw,
        COALESCE(CAST(uf AS VARCHAR), '') uf_raw,
        COALESCE(CAST(codigo_municipio AS VARCHAR), '') codigo_municipio_raw,
        SUM(CAST(valor_desembolso_real_jun2026 AS DECIMAL(38,6))) valor_real
 FROM core_bndes.fato_desembolso_mensal
 WHERE ano BETWEEN 2002 AND 2025 AND indicador_verde_estrito
 GROUP BY setor_bndes, uf, codigo_municipio
 UNION ALL
 SELECT 'Contratações', setor_bndes, COALESCE(CAST(uf AS VARCHAR), ''),
        COALESCE(CAST(codigo_municipio AS VARCHAR), ''),
        SUM(CAST(valor_contratado_real_jun2026 AS DECIMAL(38,6)))
 FROM core_bndes.fato_operacao_automatica
 WHERE ano BETWEEN 2002 AND 2025 AND indicador_verde_estrito
 GROUP BY setor_bndes, uf, codigo_municipio
 UNION ALL
 SELECT 'Contratações', setor_bndes, COALESCE(CAST(uf AS VARCHAR), ''),
        COALESCE(CAST(codigo_municipio AS VARCHAR), ''),
        SUM(CAST(valor_contratado_real_jun2026 AS DECIMAL(38,6)))
 FROM core_bndes.fato_subcredito_nao_automatico
 WHERE ano BETWEEN 2002 AND 2025 AND indicador_verde_estrito
 GROUP BY setor_bndes, uf, codigo_municipio
)
SELECT universo, setor_raw, uf_raw, codigo_municipio_raw, SUM(valor_real) valor_real
FROM base GROUP BY universo, setor_raw, uf_raw, codigo_municipio_raw
ORDER BY universo, setor_raw, uf_raw, codigo_municipio_raw
"""

FONT, TEXT, BORDER, WHITE = "Times New Roman", "#171717", "#77736C", "#FFFFFF"
CLASS_LABELS = ["0", ">0–10", ">10–50", ">50–100", ">100–250", ">250–500", ">500"]
CLASS_COLORS = ["#F7F4EC", "#FFF7BC", "#FEE391", "#FEC44F", "#FE9929", "#EC7014", "#8C2D04"]
CLASS_CMAP = ListedColormap(CLASS_COLORS, name="ve07_media_anual_classes")
CLASS_NORM = BoundaryNorm(np.arange(-0.5, len(CLASS_COLORS) + 0.5, 1.0), CLASS_CMAP.N)
LABEL_OFFSETS = {"DF": (1.55, 0.20), "ES": (1.40, -0.05), "RJ": (1.30, -0.55),
                 "SE": (1.50, -0.10), "AL": (1.45, 0.30), "PB": (1.45, 0.55), "RN": (1.15, 0.65)}


def fold_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", "" if value is None else str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^A-Z0-9]+", " ", text.upper()).strip()


def normalize_sector(value: object) -> str | None:
    return {"AGROPECUARIA": "Agropecuária", "COMERCIO E SERVICOS": "Comércio e Serviços",
            "COMERCIO SERVICOS": "Comércio e Serviços", "INDUSTRIA": "Indústria",
            "INFRAESTRUTURA": "Infraestrutura", "INFRA ESTRUTURA": "Infraestrutura"}.get(fold_text(value))


def normalize_uf(value: object) -> str | None:
    key = fold_text(value)
    return key if key in VALID_UFS else UF_NAME_TO_ABBREV.get(key)


def dec(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def class_id(value: float) -> int:
    if value <= 0: return 0
    if value <= 10: return 1
    if value <= 50: return 2
    if value <= 100: return 3
    if value <= 250: return 4
    if value <= 500: return 5
    return 6


def load_states() -> gpd.GeoDataFrame:
    states = gpd.read_file(GEO_PATH, layer="ufs_2024", engine="pyogrio").to_crs(4674)
    states["abbrev_state"] = states["abbrev_state"].astype(str).str.upper()
    if len(states) != 27 or states["abbrev_state"].nunique() != 27 or not states.geometry.is_valid.all():
        raise AssertionError("Malha estadual inválida")
    return states


def representative_points(states: gpd.GeoDataFrame) -> dict[str, tuple[float, float]]:
    projected = states.to_crs(5880)
    points = gpd.GeoSeries(projected.geometry.representative_point(), crs=5880).to_crs(4674)
    return {uf: (float(point.x), float(point.y)) for uf, point in zip(states["abbrev_state"], points)}


def prepare() -> tuple[pd.DataFrame, dict[str, object]]:
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        raw = con.execute(SQL).fetchdf()
    raw["setor_bndes"] = raw["setor_raw"].map(normalize_sector)
    if raw["setor_bndes"].isna().any():
        raise AssertionError(f"Setores não reconhecidos: {raw.loc[raw['setor_bndes'].isna(), 'setor_raw'].unique().tolist()}")
    values: defaultdict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    totals: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for row in raw.itertuples(index=False):
        universe, sector, value = str(row.universo), str(row.setor_bndes), dec(row.valor_real)
        uf_text = normalize_uf(row.uf_raw)
        code = re.sub(r"\D", "", str(row.codigo_municipio_raw)).zfill(7)
        uf_code = IBGE_PREFIX_TO_UF.get(code[:2]) if len(code) == 7 else None
        conflict = uf_text is not None and uf_code is not None and uf_text != uf_code
        territory = uf_text if uf_text is not None and not conflict else RESIDUAL
        values[(universe, sector, territory)] += value
        totals[(universe, sector)] += value

    ve06 = pd.read_csv(VE06_DATA)
    expected = ve06.groupby(["universo", "setor_bndes"])["valor_real_jun2026"].sum().to_dict()
    rows, max_diff, residual_pct = [], 0.0, {}
    territories = sorted(VALID_UFS) + [RESIDUAL]
    for universe in UNIVERSES:
        for sector, _ in SECTORS:
            total = totals[(universe, sector)]
            parts = sum((values[(universe, sector, territory)] for territory in territories), Decimal("0"))
            if total <= 0 or parts != total:
                raise AssertionError(f"Reconciliação territorial falhou: {universe}, {sector}")
            difference = abs(float(total) - float(expected[(universe, sector)]))
            max_diff = max(max_diff, difference)
            if not math.isclose(float(total), float(expected[(universe, sector)]), rel_tol=1e-12, abs_tol=0.10):
                raise AssertionError(f"VE07 diverge de VE06: {universe}, {sector}")
            residual_pct[f"{universe} | {sector}"] = float(values[(universe, sector, RESIDUAL)] / total * Decimal("100"))
            for territory in territories:
                accumulated = values[(universe, sector, territory)]
                mean = accumulated / Decimal(N_YEARS)
                rows.append({"universo": universe, "setor_bndes": sector, "territorio": territory,
                             "tipo_territorio": "Residual" if territory == RESIDUAL else "UF",
                             "valor_acumulado_real_jun2026": float(accumulated),
                             "valor_medio_anual_real_jun2026": float(mean),
                             "valor_medio_anual_milhoes": float(mean / Decimal("1000000")),
                             "participacao_total_setor_pct": float(accumulated / total * Decimal("100"))})
    data = pd.DataFrame(rows)
    return data, {"diferenca_maxima_ve06_reais": max_diff, "residual_territorial_pct": residual_pct}


def render(states: gpd.GeoDataFrame, data: pd.DataFrame, universe: str, output: Path) -> None:
    points = representative_points(states)
    fig, axes = plt.subplots(2, 2, figsize=(8.25, 7.35))
    for ax, (sector, panel_title) in zip(axes.ravel(), SECTORS):
        selected = data.loc[(data["universo"] == universe) & (data["setor_bndes"] == sector) &
                            (data["tipo_territorio"] == "UF")].copy()
        if len(selected) != 27:
            raise AssertionError(f"Mapa incompleto: {universe}, {sector}")
        selected["classe_id"] = selected["valor_medio_anual_milhoes"].map(class_id)
        gdf = states.merge(selected[["territorio", "valor_medio_anual_milhoes", "classe_id"]],
                           left_on="abbrev_state", right_on="territorio", how="left", validate="one_to_one")
        if gdf["valor_medio_anual_milhoes"].isna().any():
            raise AssertionError(f"UF sem valor: {universe}, {sector}")
        gdf.plot(column="classe_id", cmap=CLASS_CMAP, norm=CLASS_NORM, linewidth=0.46, edgecolor=BORDER, ax=ax)
        classes = dict(zip(gdf["abbrev_state"], gdf["classe_id"]))
        for uf, (x, y) in points.items():
            dx, dy = LABEL_OFFSETS.get(uf, (0.0, 0.0)); tx, ty = x + dx, y + dy
            if uf in LABEL_OFFSETS:
                ax.plot([x, tx - 0.08], [y, ty], color=BORDER, linewidth=0.36, zorder=5)
            dark = int(classes[uf]) >= 5
            label = ax.text(tx, ty, uf, ha="center", va="center", fontsize=5.8, fontweight="bold",
                            color=WHITE if dark else TEXT, zorder=6)
            label.set_path_effects([path_effects.withStroke(linewidth=0.72, foreground="#7A2505" if dark else WHITE)])
        ax.set_axis_off()
        ax.set_title(panel_title, loc="left", fontsize=10.5, fontweight="bold", color=TEXT, pad=2.5)
    handles = [Patch(facecolor=color, edgecolor=BORDER, linewidth=0.45, label=label)
               for color, label in zip(CLASS_COLORS, CLASS_LABELS)]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.012), ncol=7, frameon=False,
               fontsize=7.4, handlelength=1.10, columnspacing=0.85,
               title="Média anual (R$ milhões, a preços de jun. 2026)", title_fontsize=8.4)
    fig.subplots_adjust(left=0.018, right=0.985, top=0.985, bottom=0.125, wspace=0.02, hspace=0.06)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=600, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


def main() -> None:
    for directory in (DATA_DIR, FIG_DIR, QA_DIR): directory.mkdir(parents=True, exist_ok=True)
    mpl.rcParams.update({"font.family": FONT, "font.size": 9.0, "figure.facecolor": WHITE,
                         "savefig.facecolor": WHITE, "axes.facecolor": WHITE})
    states = load_states()
    data, checks = prepare()
    data.loc[data["universo"] == "Desembolsos"].to_csv(DATA_A, index=False, encoding="utf-8-sig")
    data.loc[data["universo"] == "Contratações"].to_csv(DATA_B, index=False, encoding="utf-8-sig")
    render(states, data, "Desembolsos", FIG_A)
    render(states, data, "Contratações", FIG_B)
    payload = {"status": "aprovado_tecnicamente_para_validacao_visual", "periodo": "2002-2025",
               "divisor_media_anual": N_YEARS, "unidade_mapa": "R$ milhões a preços de junho de 2026",
               "classes": CLASS_LABELS, "setores": [sector for sector, _ in SECTORS],
               "ufs_por_setor": 27, "linhas_analiticas": len(data), **checks,
               "amplitude_media_anual_milhoes": {"minimo": float(data.loc[data['tipo_territorio'] == 'UF', 'valor_medio_anual_milhoes'].min()),
                                                  "maximo": float(data.loc[data['tipo_territorio'] == 'UF', 'valor_medio_anual_milhoes'].max())},
               "arquivos_png": [str(FIG_A.relative_to(ROOT)), str(FIG_B.relative_to(ROOT))],
               "arquivos_csv": [str(DATA_A.relative_to(ROOT)), str(DATA_B.relative_to(ROOT))]}
    QA_OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
