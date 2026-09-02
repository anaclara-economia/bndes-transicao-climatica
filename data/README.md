# Dados locais

Este diretório não distribui dados. Todos os arquivos adicionados aqui, exceto este README, são ignorados pelo Git.

Os downloads oficiais devem ser obtidos nas fontes registradas em `manifests/sources.json`. A estrutura esperada pelos notebooks é `data/raw`, `data/interim`, `data/processed`, `data/external` e `data/local`.

As bases de operações podem conter nomes de clientes, CPF/CNPJ e números de contrato. Não faça commit desses arquivos. O DuckDB gerado localmente deve permanecer em `data/local/bndes_governanca_v1.duckdb`.
