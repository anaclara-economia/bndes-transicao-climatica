# Relatório de validação da cópia pública

**Data:** 1º de setembro de 2026  
**Escopo:** preparação local anterior ao commit e à publicação.

## Verificações concluídas

- seleção por lista positiva, sem cópia integral de diretórios;
- 5 notebooks saneados, com saídas removidas e contagens de execução nulas;
- sintaxe Python e estrutura JSON verificadas;
- carregamento de 14 scripts em modo de importação, sem erros;
- 4 testes metodológicos com dados sintéticos aprovados;
- `pip check` do ambiente de origem sem dependências quebradas;
- 34 resultados agregados inventariados: 18 CSV e 16 PNG;
- inspeção visual conjunta dos 16 PNG sem falha evidente de renderização;
- bloqueio de DuckDB, Parquet, PBIX, ABF, documentos, arquivos compactados e mídia não selecionada;
- busca por caminhos absolutos, padrões usuais de credenciais e cabeçalhos sensíveis;
- SHA-256 e tamanho registrados para cada resultado e arquivo público.

## Resultado

O inventário contém 87 arquivos públicos e 13,11 MiB. A cópia está apta para revisão do inventário anterior ao push. A publicação permanece bloqueada até autorização expressa dos titulares.

## Limites da validação

Os microdados não integram a cópia e não foram baixados novamente durante esta etapa. Portanto, a validação não constitui reexecução integral do pipeline com um novo snapshot. Os notebooks foram validados estruturalmente e os scripts foram importados, mas a reprodução completa exige os arquivos oficiais registrados e os recursos computacionais descritos em `reprodutibilidade.md`.
