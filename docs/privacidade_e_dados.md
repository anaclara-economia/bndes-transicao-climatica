# Privacidade e governança dos dados

A auditoria do projeto de origem identificou bases com nome de cliente, CPF/CNPJ, número de contrato e informações contratuais. Embora parte desses dados esteja em fontes públicas, a cópia do GitHub adota minimização e não redistribui registros individualizados.

Não são publicados: `data/raw`, `data/interim`, `data/processed`, DuckDB, entregas integrais, CPF/CNPJ, nomes de clientes, números de contrato, PBIX, ABF, caches, backups, documentos do artigo, PDFs de terceiros, áudios, transcrições e resultados marcados como preliminares ou protótipos.

Os resultados incluídos são agregados por ano, UF, município, setor ou bloco temático. Município e UF são atributos geográficos, não nomes de pessoas. O manifesto público registra cada arquivo selecionado e seu SHA-256.

Antes de qualquer publicação, execute `python scripts/check_repository.py`. Uma falha impede o envio até revisão manual.
