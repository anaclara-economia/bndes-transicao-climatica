# O BNDES no financiamento da transição climática brasileira

Material complementar de transparência, documentação e reprodutibilidade do artigo **“O BNDES no financiamento da transição climática brasileira: trajetória, estrutura e distribuição dos recursos”**, publicado pelo Centro de Financiamento Climático para o Sul Global (CFC-GS).

**Publicação:** https://cfc-gs.com.br/pt/working-papers-geral/o-bndes-no-financiamento-da-transicao-climatica-brasileira-trajetoria-estrutura-e-distribuicao-dos-recursos/

## Escopo

O repositório reúne códigos, notebooks saneados, consultas SQL, documentação metodológica, testes com dados sintéticos e uma seleção conservadora de resultados agregados. O artigo publicado não integra o repositório e não é tratado como rascunho.

Dados brutos, bases tratadas no nível de cliente ou contrato, bancos DuckDB, CPF/CNPJ, nomes de clientes e números de contrato não são distribuídos. Consulte `docs/privacidade_e_dados.md`.

## Metodologia resumida

O período principal é 2002–2025. Desembolsos e contratações são fluxos independentes e não devem ser somados. Valores reais são expressos em preços de junho de 2026, com o IPCA da Tabela 1737 do SIDRA/IBGE. A classificação principal distingue `Verde estrito` e `Demais operações`; registros sem identificação confirmada permanecem no denominador e em `Demais operações`.

## Estrutura

- `configs/`: parâmetros públicos e dicionário de nomenclatura;
- `src/`: funções Python reutilizáveis;
- `scripts/`: execução, auditoria e geração de resultados;
- `notebooks/`: sequência analítica saneada, sem saídas incorporadas;
- `sql/`: views e modelo analítico DuckDB;
- `docs/`: metodologia, fontes, privacidade e reprodutibilidade;
- `data/`: somente instruções; dados locais são ignorados pelo Git;
- `results/`: tabelas e figuras agregadas selecionadas por lista positiva;
- `manifests/`: fontes, resultados e inventário público com SHA-256;
- `tests/`: testes com dados exclusivamente sintéticos;
- `.github/workflows/ci.yml`: validação automática de segurança e integridade.

## Instalação

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.lock.txt
```

As instruções completas estão em `docs/reprodutibilidade.md`. A execução integral requer download das fontes oficiais e espaço local; a CI não baixa microdados nem publica bases locais.

## Resultados incluídos

A seleção pública limita-se a arquivos agregados das seções `verde_estrito` e `fundo_clima` que não estavam em diretórios identificados como preliminares ou protótipos no projeto de origem. Cada arquivo possui tamanho e SHA-256 em `manifests/results.json`.

## Validações

A preparação pública verifica sintaxe Python, estrutura dos notebooks, ausência de saídas executadas, caminhos absolutos, extensões proibidas, arquivos grandes, padrões usuais de credenciais, cabeçalhos sensíveis em CSV e integridade dos manifestos. Os testes analíticos usam dados sintéticos. Essas verificações não equivalem a uma reexecução integral dos microdados.

## Licenças

Os códigos, scripts, notebooks e SQL são licenciados sob a **MIT License**. A documentação, as figuras e as tabelas agregadas produzidas pelos titulares são licenciadas sob **CC BY 4.0**. Os titulares são **Wallace Marcelino Pereira** e **Ana Clara dos Santos Cabral**.

Dados e materiais de terceiros permanecem sujeitos às licenças e condições das fontes. As bases do Portal de Dados Abertos do BNDES informam licença ODbL. O artigo publicado não é relicenciado por este repositório. Consulte `LICENSE.md`.

## Citação

Use `CITATION.cff` para citar o repositório e cite separadamente o artigo publicado e as bases oficiais utilizadas.
