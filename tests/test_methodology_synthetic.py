import unittest

import pandas as pd

from bndes_financiamento_verde.public_methods import (
    aggregate_independent_flows,
    classify_binary,
    constant_price,
    validate_public_columns,
)


class MethodologySyntheticTests(unittest.TestCase):
    def test_unidentified_record_stays_out_of_green_numerator(self):
        data = pd.DataFrame({
            "politica_identificada_no_registro": [True, False, True],
            "classificacao_fonte": ["Verde estrito", "Verde estrito", "Demais operações"],
        })
        self.assertEqual(
            classify_binary(data).tolist(),
            ["Verde estrito", "Demais operações", "Demais operações"],
        )

    def test_constant_price_formula(self):
        nominal = pd.Series([100.0, 100.0])
        observed = pd.Series([100.0, 125.0])
        result = constant_price(nominal, observed, reference_index=125.0)
        self.assertEqual(result.round(6).tolist(), [125.0, 100.0])

    def test_flows_remain_independent(self):
        desembolsos = pd.DataFrame({"ano": [2025, 2025], "valor_desembolso": [10.0, 5.0]})
        contratacoes = pd.DataFrame({"ano": [2025], "valor_contratado": [30.0]})
        result = aggregate_independent_flows(desembolsos, contratacoes)
        self.assertEqual(result["universo"].tolist(), ["Desembolsos", "Contratações"])
        self.assertEqual(result["valor"].tolist(), [15.0, 30.0])

    def test_sensitive_columns_are_blocked(self):
        with self.assertRaises(ValueError):
            validate_public_columns(["ano", "cpf_cnpj", "valor"])
        validate_public_columns(["ano", "uf", "nome_municipio", "valor_agregado"])


if __name__ == "__main__":
    unittest.main()
