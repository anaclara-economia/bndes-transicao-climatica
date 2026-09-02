# Dicionário analítico

O dicionário técnico completo de nomenclatura está em `configs/dicionario_nomenclatura.json`.

`universo` identifica `Desembolsos` ou `Contratações`. `valor_desembolso_real_jun2026` e `valor_contratado_real_jun2026` representam valores corrigidos para junho de 2026. `classificacao_analise` aceita `Verde estrito` e `Demais operações`. `indicador_verde_estrito` indica inclusão no numerador verde. `politica_identificada_no_registro` indica correspondência confirmada, não necessariamente identificação individual de uma política.

`geografia_valida` informa se município e UF podem ser utilizados em rankings territoriais. `setor_bndes` preserva a classificação setorial analítica. `chave_tecnica_snapshot` e `id_subcredito_derivado` são identificadores técnicos; não devem ser apresentados como identificadores oficiais do BNDES.

Campos como cliente, CPF/CNPJ e número de contrato podem existir nas fontes locais, mas são proibidos nos resultados públicos deste repositório.
