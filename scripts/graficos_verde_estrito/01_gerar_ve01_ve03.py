"""Gera VE01, VE02 e VE03 da seção Verde estrito.

Os cálculos partem diretamente das três tabelas-fato do núcleo DuckDB. Os
desembolsos e o valor contratado permanecem universos independentes.
"""

from __future__ import annotations

import json
import math
from decimal import Decimal, getcontext
from pathlib import Path

import duckdb
import matplotlib as mpl

mpl.use("Agg")
import numpy as np
import pandas as pd
from matplotlib import font_manager
from plotnine import (
    aes,
    element_blank,
    element_line,
    element_rect,
    element_text,
    geom_line,
    geom_point,
    geom_text,
    ggplot,
    labs,
    scale_color_manual,
    scale_linetype_manual,
    scale_shape_manual,
    scale_x_continuous,
    scale_y_continuous,
    theme,
    theme_classic,
)

getcontext().prec = 50

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "results"
DB_PATH = ROOT / "data" / "local" / "bndes_governanca_v1.duckdb"
GENERAL_DATA = BASE / "tables" / "geral" / "G01_serie_anual_universos_independentes_2002_2025.csv"
DATA_DIR = BASE / "tables" / "verde_estrito"
FIG_DIR = BASE / "figures" / "verde_estrito"
QA_DIR = BASE / "metadata" / "qa" / "verde_estrito"
GOV_DIR = BASE / "metadata" / "verde_estrito"

YEARS = list(range(2002, 2026))
YEAR_TICKS = [2002, 2006, 2010, 2014, 2018, 2022, 2025]
INDEX_BASE_YEAR = 2006
INDEX_YEARS = list(range(INDEX_BASE_YEAR, 2026))
INDEX_YEAR_TICKS = [2006, 2010, 2014, 2018, 2022, 2025]
DESEMBOLSOS = "Desembolsos realizados"
CONTRATADO = "Valor contratado"
UNIVERSE_LABELS = {"Desembolsos": DESEMBOLSOS, "Contratações": CONTRATADO}

FONT = "Times New Roman"
BLACK = "#000000"
GRID = "#D9DEE3"
BORDER = "#000000"
TEXT = "#000000"
WHITE = "#FFFFFF"

SQL_ANNUAL = """
WITH fatos AS (
    SELECT 'Desembolsos' AS universo, ano, indicador_verde_estrito,
           CAST(valor_desembolso_real_jun2026 AS DECIMAL(38,6)) AS valor_real
    FROM core_bndes.fato_desembolso_mensal
    WHERE ano BETWEEN 2002 AND 2025
    UNION ALL
    SELECT 'Contratações', ano, indicador_verde_estrito,
           CAST(valor_contratado_real_jun2026 AS DECIMAL(38,6))
    FROM core_bndes.fato_operacao_automatica
    WHERE ano BETWEEN 2002 AND 2025
    UNION ALL
    SELECT 'Contratações', ano, indicador_verde_estrito,
           CAST(valor_contratado_real_jun2026 AS DECIMAL(38,6))
    FROM core_bndes.fato_subcredito_nao_automatico
    WHERE ano BETWEEN 2002 AND 2025
)
SELECT universo, ano,
       SUM(valor_real) AS valor_total_real_jun2026,
       SUM(CASE WHEN indicador_verde_estrito THEN valor_real ELSE 0 END)
           AS valor_verde_real_jun2026
FROM fatos
GROUP BY universo, ano
ORDER BY universo, ano
"""


def as_decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def format_pt(value: float, decimals: int = 1) -> str:
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def nice_step(maximum: float, target_ticks: int = 5) -> float:
    if maximum <= 0:
        return 1.0
    rough = maximum / target_ticks
    magnitude = 10 ** math.floor(math.log10(rough))
    normalized = rough / magnitude
    for candidate in (1.0, 2.0, 2.5, 5.0, 10.0):
        if normalized <= candidate:
            return candidate * magnitude
    return 10.0 * magnitude


def axis_spec(maximum: float) -> tuple[float, list[float]]:
    padded = maximum * 1.18
    step = nice_step(padded)
    upper = math.ceil(padded / step) * step
    return float(upper), np.arange(0.0, upper + step * 0.25, step).astype(float).tolist()


def check_font() -> str:
    resolved = Path(font_manager.findfont(FONT, fallback_to_default=False))
    if not resolved.exists():
        raise RuntimeError(f"Fonte obrigatória não encontrada: {FONT}")
    return str(resolved)


def load_data() -> tuple[pd.DataFrame, dict[str, float]]:
    if not DB_PATH.exists():
        raise FileNotFoundError(DB_PATH)
    with duckdb.connect(str(DB_PATH), read_only=True) as connection:
        rows = connection.execute(SQL_ANNUAL).fetchall()

    records: list[dict[str, object]] = []
    for universe, year, total, green in rows:
        total_d, green_d = as_decimal(total), as_decimal(green)
        if total_d <= 0 or green_d < 0 or green_d > total_d:
            raise AssertionError(f"Valores inválidos: {universe}, {year}")
        records.append(
            {
                "universo": str(universe),
                "serie": UNIVERSE_LABELS[str(universe)],
                "ano": int(year),
                "valor_total_real_jun2026": float(total_d),
                "valor_verde_real_jun2026": float(green_d),
                "valor_verde_bilhoes_jun2026": float(green_d / Decimal("1000000000")),
                "participacao_verde_pct": float(green_d / total_d * Decimal("100")),
            }
        )

    data = pd.DataFrame(records)
    expected = {(u, y) for u in UNIVERSE_LABELS for y in YEARS}
    if len(data) != 48 or set(zip(data["universo"], data["ano"])) != expected:
        raise AssertionError("Séries anuais incompletas para 2002–2025")

    for universe, frame in data.groupby("universo", sort=False):
        frame = frame.sort_values("ano")
        base = float(
            frame.loc[
                frame["ano"] == INDEX_BASE_YEAR, "valor_verde_real_jun2026"
            ].iloc[0]
        )
        if base <= 0:
            raise AssertionError(f"Base {INDEX_BASE_YEAR} nula para {universe}")
        data.loc[frame.index, "indice_verde_2006_100"] = (
            frame["valor_verde_real_jun2026"] / base * 100.0
        )

    if GENERAL_DATA.exists():
        general = pd.read_csv(GENERAL_DATA)
        comparison = data.merge(
            general[["universo", "ano", "valor_real_jun2026"]].rename(
                columns={"valor_real_jun2026": "valor_total_geral_validado"}
            ),
            on=["universo", "ano"], how="left", validate="one_to_one",
        )
        if comparison["valor_total_geral_validado"].isna().any():
            raise AssertionError("Falha na reconciliação com o G01")
        difference = (
            comparison["valor_total_real_jun2026"] - comparison["valor_total_geral_validado"]
        ).abs()
        if not np.allclose(
            comparison["valor_total_real_jun2026"], comparison["valor_total_geral_validado"],
            rtol=1e-12, atol=0.10,
        ):
            raise AssertionError("Totais anuais divergem do G01 validado")
    else:
        difference = pd.Series([float("nan")])

    summary = {
        "diferenca_maxima_reconciliacao_reais": (float(difference.max()) if difference.notna().any() else None),
        "participacao_minima_pct": float(data["participacao_verde_pct"].min()),
        "participacao_maxima_pct": float(data["participacao_verde_pct"].max()),
        "indice_2006_2025_minimo": float(
            data.loc[data["ano"] >= INDEX_BASE_YEAR, "indice_verde_2006_100"].min()
        ),
        "indice_2006_2025_maximo": float(
            data.loc[data["ano"] >= INDEX_BASE_YEAR, "indice_verde_2006_100"].max()
        ),
    }
    return data.sort_values(["universo", "ano"]).reset_index(drop=True), summary


def build_annotations(
    frame: pd.DataFrame,
    metric: str,
    y_max: float,
    formatter,
    roles: tuple[str, ...],
) -> pd.DataFrame:
    labels: list[dict[str, object]] = []
    for series_name, series in frame.groupby("serie", sort=False):
        series = series.sort_values("ano")
        all_points = [
            ("inicio", series.iloc[0]),
            ("fim", series.iloc[-1]),
            ("maximo", series.loc[series[metric].idxmax()]),
            ("minimo", series.loc[series[metric].idxmin()]),
        ]
        points = [item for item in all_points if item[0] in roles]
        used_years: set[int] = set()
        for role, point in points:
            year = int(point["ano"])
            if year in used_years:
                continue
            used_years.add(year)
            value = float(point[metric])
            if role == "inicio":
                x_label, h_align, direction = float(year) + 0.18, "left", 1
            elif role == "fim":
                x_label, h_align, direction = float(year) + 0.22, "left", 1
            elif role == "maximo":
                x_label, h_align, direction = float(year), "center", 1
            else:
                x_label, h_align, direction = float(year), "center", -1
            offset = y_max * (0.018 if role in {"inicio", "fim"} else 0.022)
            proposed = value + direction * offset

            # Os valores iniciais de VE02 ficam muito próximos de zero. Em vez
            # de afastá-los verticalmente, as duas séries são separadas por um
            # pequeno deslocamento lateral, mantendo cada rótulo junto ao ponto.
            if role == "inicio" and value < y_max * 0.08:
                if series_name == DESEMBOLSOS:
                    x_label, h_align = float(year) + 0.28, "left"
                    proposed = value + y_max * 0.030
                else:
                    x_label, h_align = float(year) - 0.18, "right"
                    proposed = value + y_max * 0.014
            if proposed < y_max * 0.012:
                proposed = value + offset
            if role == "minimo" and proposed < y_max * 0.020:
                x_label, h_align = float(year) + 0.16, "left"
                proposed = value + y_max * 0.012
            if proposed > y_max * 0.965:
                proposed = value - offset
            labels.append(
                {
                    "serie": series_name,
                    "papel": role,
                    "x_rotulo": x_label,
                    "y_rotulo": proposed,
                    "rotulo": formatter(value),
                    "ha": h_align,
                    "va": "bottom" if proposed >= value else "top",
                }
            )
    return pd.DataFrame(labels)


def render_chart(
    data: pd.DataFrame,
    *,
    metric: str,
    unit_label: str,
    stem: str,
    axis_formatter,
    label_formatter,
    annotation_roles: tuple[str, ...],
    x_ticks: list[int],
    x_limits: tuple[float, float],
) -> Path:
    chart_data = data[["serie", "ano", metric]].copy()
    y_max, y_breaks = axis_spec(float(chart_data[metric].max()))
    annotations = build_annotations(
        chart_data, metric, y_max, label_formatter, annotation_roles
    )

    plot = (
        ggplot(
            chart_data,
            aes(x="ano", y=metric, color="serie", linetype="serie", shape="serie", group="serie"),
        )
        + geom_line(size=0.76, lineend="round")
        + geom_point(size=1.42, stroke=0.50, fill=WHITE)
        + scale_color_manual(values={DESEMBOLSOS: BLACK, CONTRATADO: BLACK})
        + scale_linetype_manual(values={DESEMBOLSOS: "solid", CONTRATADO: "dashed"})
        + scale_shape_manual(values={DESEMBOLSOS: "o", CONTRATADO: "s"})
        + scale_x_continuous(
            limits=x_limits, breaks=x_ticks,
            labels=[str(value) for value in x_ticks], expand=(0, 0),
        )
        + scale_y_continuous(
            limits=(0.0, y_max), breaks=y_breaks,
            labels=[axis_formatter(value) for value in y_breaks], expand=(0, 0),
        )
        + labs(subtitle=unit_label, x=None, y=None, color=None, linetype=None, shape=None)
        + theme_classic(base_family=FONT, base_size=9.0)
        + theme(
            figure_size=(9.2, 5.0), dpi=600,
            legend_position="top", legend_direction="horizontal",
            legend_title=element_blank(),
            legend_text=element_text(size=8.2, color=TEXT),
            legend_key=element_rect(fill=WHITE, color=None),
            legend_background=element_rect(fill=WHITE, color=None),
            axis_title_x=element_blank(), axis_title_y=element_blank(),
            axis_text_x=element_text(size=8.2, color=TEXT, rotation=0, ha="center", margin={"t": 7}),
            axis_text_y=element_text(size=8.2, color=TEXT, margin={"r": 5}),
            axis_ticks_x=element_line(color=BORDER, size=0.36),
            axis_ticks_y=element_blank(),
            axis_line=element_line(color=BORDER, size=0.42),
            panel_background=element_rect(fill=WHITE, color=None),
            panel_grid_major_y=element_line(color=GRID, size=0.38),
            panel_grid_major_x=element_blank(), panel_grid_minor=element_blank(),
            panel_border=element_blank(),
            plot_subtitle=element_text(size=8.2, color=BORDER, ha="left", margin={"b": 4}),
            plot_title_position="plot",
            plot_background=element_rect(fill=WHITE, color=None),
            plot_margin_left=0.02, plot_margin_right=0.02,
            plot_margin_top=0.02, plot_margin_bottom=0.02,
        )
    )
    for row in annotations.to_dict("records"):
        color = BLACK
        plot += geom_text(
            data=pd.DataFrame([row]),
            mapping=aes(x="x_rotulo", y="y_rotulo", label="rotulo"),
            inherit_aes=False, color=color, ha=str(row["ha"]), va=str(row["va"]),
            size=7.0, family=FONT, fontweight="bold", show_legend=False,
        )
    output = FIG_DIR / f"{stem}.png"
    plot.save(filename=output, format="png", dpi=600, verbose=False)
    return output


def export_csvs(data: pd.DataFrame) -> dict[str, Path]:
    common = ["universo", "serie", "ano", "valor_total_real_jun2026", "valor_verde_real_jun2026"]
    outputs = {
        "VE01": DATA_DIR / "VE01_participacao_anual_verde_estrito_2002_2025.csv",
        "VE02": DATA_DIR / "VE02_valor_real_anual_verde_estrito_2002_2025.csv",
        "VE03": DATA_DIR / "VE03_indice_evolucao_verde_estrito_2006_2025.csv",
    }
    data[common + ["participacao_verde_pct"]].to_csv(outputs["VE01"], index=False, encoding="utf-8-sig")
    data[common + ["valor_verde_bilhoes_jun2026"]].to_csv(outputs["VE02"], index=False, encoding="utf-8-sig")
    data.loc[data["ano"] >= INDEX_BASE_YEAR, common + ["indice_verde_2006_100"]].to_csv(
        outputs["VE03"], index=False, encoding="utf-8-sig"
    )
    return outputs


def export_excel_source(data: pd.DataFrame) -> Path:
    """Grava uma fonte JSON estável para a planilha editável.

    Os indicadores derivados continuarão sendo calculados por fórmulas no
    Excel; o JSON contém apenas os totais e os valores verdes reconciliados.
    """
    output = DATA_DIR / "fonte_excel_ve01_ve03.json"
    fields = [
        "universo",
        "serie",
        "ano",
        "valor_total_real_jun2026",
        "valor_verde_real_jun2026",
    ]
    records = data[fields].to_dict(orient="records")
    output.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output


def write_metadata() -> Path:
    metadata = {
        "VE01": {
            "titulo": "Participação do financiamento Verde estrito no total do BNDES — Brasil, 2002–2025",
            "fonte": "Elaboração dos autores com base no Portal de Dados Abertos do BNDES e no IPCA/IBGE.",
            "notas": [
                "A participação corresponde ao valor do Verde estrito dividido pelo total anual do respectivo fluxo.",
                "Desembolsos realizados e valor contratado constituem universos analíticos independentes.",
            ],
        },
        "VE02": {
            "titulo": "Evolução anual do financiamento Verde estrito no BNDES — Brasil, 2002–2025",
            "fonte": "Elaboração dos autores com base no Portal de Dados Abertos do BNDES e no IPCA/IBGE.",
            "notas": [
                "Valores a preços de junho de 2026, deflacionados pelo IPCA mensal.",
                "A sobreposição permite comparar trajetórias, mas os dois fluxos não devem ser somados ou subtraídos.",
            ],
        },
        "VE03": {
            "titulo": "Índice de evolução do financiamento Verde estrito no BNDES — Brasil, 2006–2025",
            "fonte": "Elaboração dos autores com base no Portal de Dados Abertos do BNDES e no IPCA/IBGE.",
            "notas": [
                "Índice calculado separadamente para cada fluxo, com 2006 = 100.",
                "O índice mede evolução relativa e não representa participação percentual no total do BNDES.",
            ],
        },
    }
    output = GOV_DIR / "metadados_ve01_ve03.json"
    output.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def main() -> None:
    for directory in (DATA_DIR, FIG_DIR, QA_DIR, GOV_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    font_path = check_font()
    mpl.rcParams.update(
        {
            "font.family": FONT,
            "axes.unicode_minus": False,
            "figure.facecolor": WHITE,
            "savefig.facecolor": WHITE,
        }
    )
    data, summary = load_data()
    csvs = export_csvs(data)
    excel_source = export_excel_source(data)
    figures = {
        "VE01": render_chart(
            data,
            metric="participacao_verde_pct",
            unit_label="Participação no total anual do respectivo fluxo (%)",
            stem="VE01_participacao_anual_verde_estrito_2002_2025",
            axis_formatter=lambda value: f"{format_pt(value, 0)}%",
            label_formatter=lambda value: f"{format_pt(value, 1)}%",
            annotation_roles=("fim", "maximo"),
            x_ticks=YEAR_TICKS,
            x_limits=(2001.0, 2027.0),
        ),
        "VE02": render_chart(
            data,
            metric="valor_verde_bilhoes_jun2026",
            unit_label="R$ bilhões, a preços de junho de 2026",
            stem="VE02_valor_real_anual_verde_estrito_2002_2025",
            axis_formatter=lambda value: "0" if abs(value) < 1e-12 else format_pt(value, 0 if value >= 1 else 1),
            label_formatter=lambda value: format_pt(value, 1),
            annotation_roles=("inicio", "fim", "maximo", "minimo"),
            x_ticks=YEAR_TICKS,
            x_limits=(2001.0, 2027.0),
        ),
        "VE03": render_chart(
            data.loc[data["ano"] >= INDEX_BASE_YEAR].copy(),
            metric="indice_verde_2006_100",
            unit_label="Índice de evolução (2006 = 100)",
            stem="VE03_indice_evolucao_verde_estrito_2006_2025",
            axis_formatter=lambda value: format_pt(value, 0),
            label_formatter=lambda value: format_pt(value, 0),
            annotation_roles=("fim", "maximo"),
            x_ticks=INDEX_YEAR_TICKS,
            x_limits=(2005.0, 2027.0),
        ),
    }
    metadata = write_metadata()
    qa = {
        "status": "aprovado_tecnicamente",
        "fonte_times_new_roman": font_path,
        "linhas": len(data),
        "anos_por_universo": {u: int(len(f)) for u, f in data.groupby("universo")},
        "bases_2006_reais": {
            u: float(
                f.loc[f["ano"] == INDEX_BASE_YEAR, "valor_verde_real_jun2026"].iloc[0]
            )
            for u, f in data.groupby("universo")
        },
        "resumo": summary,
        "csvs": {key: str(path.relative_to(ROOT)) for key, path in csvs.items()},
        "fonte_excel": str(excel_source.relative_to(ROOT)),
        "figuras": {key: str(path.relative_to(ROOT)) for key, path in figures.items()},
        "metadados": str(metadata.relative_to(ROOT)),
        "invariantes": {
            "periodo_2002_2025_completo": True,
            "participacoes_entre_zero_e_cem": bool(data["participacao_verde_pct"].between(0, 100).all()),
            "verde_nao_supera_total": bool(
                (data["valor_verde_real_jun2026"] <= data["valor_total_real_jun2026"]).all()
            ),
            "indice_2006_igual_100": bool(
                np.allclose(
                    data.loc[
                        data["ano"] == INDEX_BASE_YEAR, "indice_verde_2006_100"
                    ],
                    100.0, rtol=0, atol=1e-10,
                )
            ),
        },
    }
    if not all(qa["invariantes"].values()):
        raise AssertionError(f"Falha nos invariantes: {qa['invariantes']}")
    qa_output = QA_DIR / "validacao_ve01_ve03.json"
    qa_output.write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(qa, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
