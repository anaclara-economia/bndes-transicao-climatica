"""Funções pequenas e auditáveis usadas nos testes públicos com dados sintéticos."""

from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd

VALID_CLASSES = {"Verde estrito", "Demais operações"}
PROHIBITED_PUBLIC_COLUMNS = {
    "cpf", "cnpj", "cpf_cnpj", "cpf_cnpj_cliente", "cliente",
    "nome_cliente", "numero_contrato", "numero_do_contrato", "contrato_sk",
}


def _normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def classify_binary(frame: pd.DataFrame) -> pd.Series:
    """Aplica a regra conservadora: somente correspondência confirmada pode ser verde."""
    required = {"politica_identificada_no_registro", "classificacao_fonte"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Colunas ausentes: {sorted(missing)}")
    identified = frame["politica_identificada_no_registro"].fillna(False).astype(bool)
    green = identified & frame["classificacao_fonte"].eq("Verde estrito")
    result = pd.Series(np.where(green, "Verde estrito", "Demais operações"), index=frame.index)
    if not set(result.unique()).issubset(VALID_CLASSES):
        raise AssertionError("Classificação fora do domínio binário")
    return result


def constant_price(nominal: pd.Series, observed_index: pd.Series, reference_index: float) -> pd.Series:
    """Converte valor nominal para preços do mês de referência: Vt * Iref / It."""
    if reference_index <= 0 or (observed_index <= 0).any():
        raise ValueError("Índices de preços devem ser positivos")
    return nominal.astype(float) * float(reference_index) / observed_index.astype(float)


def aggregate_independent_flows(
    disbursements: pd.DataFrame,
    contracts: pd.DataFrame,
    year: str = "ano",
    disbursement_value: str = "valor_desembolso",
    contract_value: str = "valor_contratado",
) -> pd.DataFrame:
    """Agrega os dois fluxos separadamente, sem criar total aditivo conjunto."""
    d = disbursements.groupby(year, as_index=False)[disbursement_value].sum()
    d = d.rename(columns={disbursement_value: "valor"}).assign(universo="Desembolsos")
    c = contracts.groupby(year, as_index=False)[contract_value].sum()
    c = c.rename(columns={contract_value: "valor"}).assign(universo="Contratações")
    return pd.concat([d, c], ignore_index=True)[["universo", year, "valor"]]


def validate_public_columns(columns) -> None:
    """Bloqueia identificadores pessoais ou contratuais conhecidos em resultados públicos."""
    normalized = {_normalize_name(column) for column in columns}
    found = sorted(normalized.intersection(PROHIBITED_PUBLIC_COLUMNS))
    if found:
        raise ValueError(f"Colunas proibidas em resultado público: {found}")
