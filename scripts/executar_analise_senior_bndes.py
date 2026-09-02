from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bndes_financiamento_verde.analise_senior import executar_pipeline


if __name__ == "__main__":
    artefatos = executar_pipeline()
    print(json.dumps(artefatos.resumo, ensure_ascii=False, indent=2))
