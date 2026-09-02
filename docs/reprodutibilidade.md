# Reprodutibilidade

## Ambiente

Use Python 3.10 a 3.12. O ambiente auditado na preparação da cópia utilizou Python 3.11 e as versões de `requirements.lock.txt`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.lock.txt
```

## Dados

Consulte `manifests/sources.json` e baixe os recursos oficiais. Armazene os arquivos em `data/raw`. Não use arquivos recebidos por terceiros sem registrar origem e SHA-256. Nenhum dado local deve ser commitado.

## Ordem de execução

Execute os notebooks 01 a 05 em ordem. O notebook 02 acessa a internet e o notebook 04 grava arquivos em `data/`. As cópias públicas não contêm saídas executadas. Revise as células antes de executar e confirme os diretórios de destino.

Depois da preparação dos Parquets locais, os scripts de materialização criam o DuckDB em `data/local`. Os scripts de figuras leem esse banco e gravam somente resultados agregados em `results/`.

## Verificações

```powershell
python scripts/check_repository.py
python -m unittest discover -s tests -v
```

A validação pública cobre estrutura, sintaxe, segurança, dados sintéticos e integridade dos resultados incluídos. A reprodução integral exige os snapshots oficiais e recursos computacionais locais. Resultados idênticos dependem de utilizar as mesmas versões e os mesmos arquivos de entrada registrados por hash.
