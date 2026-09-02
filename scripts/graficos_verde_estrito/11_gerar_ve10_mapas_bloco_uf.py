"""Gera VE10A/B: distribuição estadual do Verde estrito por bloco temático."""

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
GEO_PATH = (
    BASE
    / "05_geometrias"
    / "ibge_2024"
    / "ibge_ufs_2024_simplificado_epsg4674.gpkg"
)
VE09_DATA = (
    BASE
    / "01_dados_analiticos"
    / "verde_estrito"
    / "VE09_composicao_verde_estrito_por_bloco_tematico_2002_2025.csv"
)
DATA_DIR = BASE / "tables" / "verde_estrito"
FIG_DIR = BASE / "figures" / "verde_estrito"
QA_DIR = BASE / "metadata" / "qa" / "verde_estrito"

DATA_A = (
    DATA_DIR
    / "VE10A_distribuicao_uf_desembolsos_verde_estrito_por_bloco_2002_2025.csv"
)
DATA_B = (
    DATA_DIR
    / "VE10B_distribuicao_uf_valor_contratado_verde_estrito_por_bloco_2002_2025.csv"
)
FIG_A = (
    FIG_DIR
    / "VE10A_distribuicao_uf_desembolsos_verde_estrito_por_bloco_2002_2025.png"
)
FIG_B = (
    FIG_DIR
    / "VE10B_distribuicao_uf_valor_contratado_verde_estrito_por_bloco_2002_2025.png"
)
QA_OUTPUT = QA_DIR / "validacao_ve10_mapas_bloco_uf.json"

RESIDUAL = "Sem identificação territorial"
UNIVERSES = ["Desembolsos", "Contratações"]
BLOCKS = [
    ("Biocombustíveis", "A. Biocombustíveis"),
    ("Clima e descarbonização", "B. Clima e descarbonização"),
    ("Energia e eficiência", "C. Energia e eficiência"),
    ("Florestas e bioeconomia", "D. Florestas e bioeconomia"),
    ("Meio ambiente", "E. Meio ambiente"),
    ("Saneamento", "F. Saneamento"),
]

UF_NAME_TO_ABBREV = {
    "ACRE": "AC",
    "ALAGOAS": "AL",
    "AMAPA": "AP",
    "AMAZONAS": "AM",
    "BAHIA": "BA",
    "CEARA": "CE",
    "DISTRITO FEDERAL": "DF",
    "ESPIRITO SANTO": "ES",
    "GOIAS": "GO",
    "MARANHAO": "MA",
    "MATO GROSSO": "MT",
    "MATO GROSSO DO SUL": "MS",
    "MINAS GERAIS": "MG",
    "PARA": "PA",
    "PARAIBA": "PB",
    "PARANA": "PR",
    "PERNAMBUCO": "PE",
    "PIAUI": "PI",
    "RIO DE JANEIRO": "RJ",
    "RIO GRANDE DO NORTE": "RN",
    "RIO GRANDE DO SUL": "RS",
    "RONDONIA": "RO",
    "RORAIMA": "RR",
    "SANTA CATARINA": "SC",
    "SAO PAULO": "SP",
    "SERGIPE": "SE",
    "TOCANTINS": "TO",
}
VALID_UFS = set(UF_NAME_TO_ABBREV.values())
IBGE_PREFIX_TO_UF = {
    "11": "RO",
    "12": "AC",
    "13": "AM",
    "14": "RR",
    "15": "PA",
    "16": "AP",
    "17": "TO",
    "21": "MA",
    "22": "PI",
    "23": "CE",
    "24": "RN",
    "25": "PB",
    "26": "PE",
    "27": "AL",
    "28": "SE",
    "29": "BA",
    "31": "MG",
    "32": "ES",
    "33": "RJ",
    "35": "SP",
    "41": "PR",
    "42": "SC",
    "43": "RS",
    "50": "MS",
    "51": "MT",
    "52": "GO",
    "53": "DF",
}

SQL = """
WITH base AS (
    SELECT
        'Desembolsos' AS universo,
        bloco_tematico AS bloco_raw,
        COALESCE(CAST(uf AS VARCHAR), '') AS uf_raw,
        COALESCE(CAST(codigo_municipio AS VARCHAR), '') AS codigo_municipio_raw,
        SUM(CAST(valor_desembolso_real_jun2026 AS DECIMAL(38,6))) AS valor_real
    FROM core_bndes.fato_desembolso_mensal
    WHERE ano BETWEEN 2002 AND 2025
      AND indicador_verde_estrito
    GROUP BY bloco_tematico, uf, codigo_municipio

    UNION ALL

    SELECT
        'Contratações' AS universo,
        bloco_tematico AS bloco_raw,
        COALESCE(CAST(uf AS VARCHAR), '') AS uf_raw,
        COALESCE(CAST(codigo_municipio AS VARCHAR), '') AS codigo_municipio_raw,
        SUM(CAST(valor_contratado_real_jun2026 AS DECIMAL(38,6))) AS valor_real
    FROM core_bndes.fato_operacao_automatica
    WHERE ano BETWEEN 2002 AND 2025
      AND indicador_verde_estrito
    GROUP BY bloco_tematico, uf, codigo_municipio

    UNION ALL

    SELECT
        'Contratações' AS universo,
        bloco_tematico AS bloco_raw,
        COALESCE(CAST(uf AS VARCHAR), '') AS uf_raw,
        COALESCE(CAST(codigo_municipio AS VARCHAR), '') AS codigo_municipio_raw,
        SUM(CAST(valor_contratado_real_jun2026 AS DECIMAL(38,6))) AS valor_real
    FROM core_bndes.fato_subcredito_nao_automatico
    WHERE ano BETWEEN 2002 AND 2025
      AND indicador_verde_estrito
    GROUP BY bloco_tematico, uf, codigo_municipio
)
SELECT
    universo,
    bloco_raw,
    uf_raw,
    codigo_municipio_raw,
    SUM(valor_real) AS valor_real
FROM base
GROUP BY universo, bloco_raw, uf_raw, codigo_municipio_raw
ORDER BY universo, bloco_raw, uf_raw, codigo_municipio_raw
"""

FONT = "Times New Roman"
TEXT = "#171717"
BORDER = "#77736C"
WHITE = "#FFFFFF"
CLASS_LABELS = ["0%", ">0–1%", ">1–5%", ">5–10%", ">10–20%", ">20%"]
CLASS_COLORS = [
    "#F7F4EC",
    "#FFF7BC",
    "#FEE391",
    "#FEC44F",
    "#FE9929",
    "#CC4C02",
]
CLASS_CMAP = ListedColormap(CLASS_COLORS, name="ve10_participacao_uf")
CLASS_NORM = BoundaryNorm(
    np.arange(-0.5, len(CLASS_COLORS) + 0.5, 1.0), CLASS_CMAP.N
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


def normalize_uf(value: object) -> str | None:
    key = fold_text(value)
    return key if key in VALID_UFS else UF_NAME_TO_ABBREV.get(key)


def dec(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


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


def load_states() -> gpd.GeoDataFrame:
    states = gpd.read_file(GEO_PATH, layer="ufs_2024", engine="pyogrio").to_crs(4674)
    states["abbrev_state"] = states["abbrev_state"].astype(str).str.upper()
    if (
        len(states) != 27
        or states["abbrev_state"].nunique() != 27
        or not states.geometry.is_valid.all()
    ):
        raise AssertionError("Malha estadual inválida.")
    return states


def representative_points(
    states: gpd.GeoDataFrame,
) -> dict[str, tuple[float, float]]:
    projected = states.to_crs(5880)
    points = gpd.GeoSeries(
        projected.geometry.representative_point(), crs=5880
    ).to_crs(4674)
    return {
        uf: (float(point.x), float(point.y))
        for uf, point in zip(states["abbrev_state"], points)
    }


def prepare() -> tuple[pd.DataFrame, dict[str, object]]:
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        raw = con.execute(SQL).fetchdf()

    raw["bloco_tematico"] = raw["bloco_raw"].map(normalize_block)
    if raw["bloco_tematico"].isna().any():
        invalid = raw.loc[
            raw["bloco_tematico"].isna(), "bloco_raw"
        ].unique().tolist()
        raise AssertionError(f"Blocos não reconhecidos: {invalid}")

    values: defaultdict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    totals: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)

    for row in raw.itertuples(index=False):
        universe = str(row.universo)
        block = str(row.bloco_tematico)
        value = dec(row.valor_real)
        uf_text = normalize_uf(row.uf_raw)
        digits = re.sub(r"\D", "", str(row.codigo_municipio_raw))
        code = digits.zfill(7) if digits else ""
        uf_code = IBGE_PREFIX_TO_UF.get(code[:2]) if len(code) == 7 else None
        conflict = (
            uf_text is not None and uf_code is not None and uf_text != uf_code
        )
        territory = (
            uf_text if uf_text is not None and not conflict else RESIDUAL
        )
        values[(universe, block, territory)] += value
        totals[(universe, block)] += value

    reference = {
        (str(row.universo), str(row.bloco_tematico)): float(
            row.valor_real_jun2026
        )
        for row in pd.read_csv(VE09_DATA).itertuples(index=False)
    }

    territories = sorted(VALID_UFS) + [RESIDUAL]
    rows: list[dict[str, object]] = []
    maximum_difference = 0.0
    maximum_share_error = 0.0
    residual_shares: dict[str, float] = {}

    for universe in UNIVERSES:
        for block, _ in BLOCKS:
            total = totals[(universe, block)]
            parts = sum(
                (values[(universe, block, territory)] for territory in territories),
                Decimal("0"),
            )
            if total <= 0 or parts != total:
                raise AssertionError(
                    f"Reconciliação territorial falhou: {universe}, {block}"
                )

            difference = abs(float(total) - reference[(universe, block)])
            maximum_difference = max(maximum_difference, difference)
            if not math.isclose(
                float(total),
                reference[(universe, block)],
                rel_tol=1e-12,
                abs_tol=0.10,
            ):
                raise AssertionError(f"VE10 diverge de VE09: {universe}, {block}")

            shares: list[Decimal] = []
            for territory in territories:
                value = values[(universe, block, territory)]
                share = value / total * Decimal("100")
                shares.append(share)
                rows.append(
                    {
                        "universo": universe,
                        "bloco_tematico": block,
                        "territorio": territory,
                        "tipo_territorio": (
                            "Residual" if territory == RESIDUAL else "UF"
                        ),
                        "valor_real_jun2026": float(value),
                        "valor_total_bloco_real_jun2026": float(total),
                        "participacao_total_bloco_pct": float(share),
                        "classe_mapa": CLASS_LABELS[class_id(float(share))],
                    }
                )

            maximum_share_error = max(
                maximum_share_error,
                float(abs(sum(shares, Decimal("0")) - Decimal("100"))),
            )
            residual_shares[f"{universe} | {block}"] = float(
                values[(universe, block, RESIDUAL)]
                / total
                * Decimal("100")
            )

    data = pd.DataFrame(rows)
    if len(data) != 336:
        raise AssertionError("VE10 deve conter 336 linhas analíticas.")
    if not data["participacao_total_bloco_pct"].between(0, 100).all():
        raise AssertionError("Participação territorial fora de 0%–100%.")

    return data, {
        "diferenca_maxima_ve09_reais": maximum_difference,
        "erro_maximo_uf_mais_residual_pp": maximum_share_error,
        "residual_territorial_pct": residual_shares,
    }


def render(
    states: gpd.GeoDataFrame,
    data: pd.DataFrame,
    universe: str,
    output: Path,
) -> None:
    points = representative_points(states)
    fig, axes = plt.subplots(3, 2, figsize=(7.2, 8.65))

    for axis, (block, panel_title) in zip(axes.ravel(), BLOCKS):
        selected = data.loc[
            (data["universo"] == universe)
            & (data["bloco_tematico"] == block)
            & (data["tipo_territorio"] == "UF")
        ].copy()
        if len(selected) != 27:
            raise AssertionError(f"Mapa incompleto: {universe}, {block}")

        selected["classe_id"] = selected["participacao_total_bloco_pct"].map(
            class_id
        )
        mapped = states.merge(
            selected[["territorio", "participacao_total_bloco_pct", "classe_id"]],
            left_on="abbrev_state",
            right_on="territorio",
            how="left",
            validate="one_to_one",
        )
        if mapped["participacao_total_bloco_pct"].isna().any():
            raise AssertionError(f"UF sem participação: {universe}, {block}")

        mapped.plot(
            column="classe_id",
            cmap=CLASS_CMAP,
            norm=CLASS_NORM,
            linewidth=0.44,
            edgecolor=BORDER,
            ax=axis,
        )
        class_by_uf = dict(zip(mapped["abbrev_state"], mapped["classe_id"]))
        for uf, (x, y) in points.items():
            dx, dy = LABEL_OFFSETS.get(uf, (0.0, 0.0))
            tx, ty = x + dx, y + dy
            if uf in LABEL_OFFSETS:
                axis.plot(
                    [x, tx - 0.08],
                    [y, ty],
                    color=BORDER,
                    linewidth=0.34,
                    zorder=5,
                )
            dark = int(class_by_uf[uf]) >= 4
            label = axis.text(
                tx,
                ty,
                uf,
                ha="center",
                va="center",
                fontsize=5.55,
                fontweight="bold",
                color=WHITE if dark else TEXT,
                zorder=6,
            )
            label.set_path_effects(
                [
                    path_effects.withStroke(
                        linewidth=0.70,
                        foreground="#762603" if dark else WHITE,
                    )
                ]
            )

        axis.set_axis_off()
        axis.set_title(
            panel_title,
            loc="left",
            fontsize=9.7,
            fontweight="bold",
            color=TEXT,
            pad=2.5,
        )

    handles = [
        Patch(
            facecolor=color,
            edgecolor=BORDER,
            linewidth=0.42,
            label=label,
        )
        for color, label in zip(CLASS_COLORS, CLASS_LABELS)
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.012),
        ncol=6,
        frameon=False,
        fontsize=7.5,
        handlelength=1.12,
        handletextpad=0.40,
        columnspacing=0.90,
    )
    fig.subplots_adjust(
        left=0.018,
        right=0.985,
        top=0.985,
        bottom=0.075,
        wspace=0.015,
        hspace=0.055,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=600, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


def main() -> None:
    for directory in (DATA_DIR, FIG_DIR, QA_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    mpl.rcParams.update(
        {
            "font.family": FONT,
            "font.size": 9.0,
            "figure.facecolor": WHITE,
            "savefig.facecolor": WHITE,
            "axes.facecolor": WHITE,
        }
    )
    states = load_states()
    data, checks = prepare()

    data.loc[data["universo"] == "Desembolsos"].to_csv(
        DATA_A, index=False, encoding="utf-8-sig"
    )
    data.loc[data["universo"] == "Contratações"].to_csv(
        DATA_B, index=False, encoding="utf-8-sig"
    )
    render(states, data, "Desembolsos", FIG_A)
    render(states, data, "Contratações", FIG_B)

    payload = {
        "status": "aprovado_tecnicamente_para_validacao_visual",
        "periodo": "2002-2025",
        "unidade_mapa": "participação da UF no total do próprio bloco",
        "classes": CLASS_LABELS,
        "blocos_tematicos": [block for block, _ in BLOCKS],
        "ufs_por_painel": 27,
        "linhas_analiticas": len(data),
        **checks,
        "arquivos_png": [
            str(FIG_A.relative_to(ROOT)),
            str(FIG_B.relative_to(ROOT)),
        ],
        "arquivos_csv": [
            str(DATA_A.relative_to(ROOT)),
            str(DATA_B.relative_to(ROOT)),
        ],
    }
    QA_OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

