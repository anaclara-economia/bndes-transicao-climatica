"""Auditoria bloqueante da cópia pública; não acessa rede nem microdados."""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_TOP = {
    ".github", ".gitattributes", ".gitignore", "CITATION.cff", "LICENSE.md", "LICENSES",
    "README.md", "configs", "data", "docs", "manifests", "notebooks",
    "pyproject.toml", "requirements.lock.txt", "results", "scripts", "sql",
    "src", "tests",
}
FORBIDDEN_SUFFIXES = {
    ".abf", ".duckdb", ".feather", ".ogg", ".parquet", ".pbix", ".pem",
    ".pfx", ".zip", ".7z", ".rar", ".docx", ".pdf",
}
FORBIDDEN_NAME_PARTS = {
    "preliminar", "prototipo", "rascunho", "backup", "transcricao",
    "transcription", "codex_work", "node_modules", "__pycache__",
}
PROHIBITED_HEADERS = {
    "cpf", "cnpj", "cpf_cnpj", "cpf_cnpj_cliente", "cliente", "nome_cliente",
    "numero_contrato", "numero_do_contrato", "contrato_sk",
}
MAX_FILE_SIZE = 25 * 1024 * 1024
ABSOLUTE_PATH = re.compile(r"(?i)(?:[A-Z]:[\\/]+Us" + r"ers[\\/]|C:/" + r"Users/)")
SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|password|senha)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
]
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".toml", ".yml", ".yaml", ".sql", ".cff", ".gitignore"}


def normalize(value: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", value)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def public_files() -> list[Path]:
    return sorted(
        p for p in ROOT.rglob("*")
        if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts
    )


def check_files(errors: list[str]) -> None:
    for path in public_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel.split("/", 1)[0] not in ALLOWED_TOP:
            errors.append(f"fora da lista positiva: {rel}")
        if path.stat().st_size > MAX_FILE_SIZE:
            errors.append(f"arquivo maior que 25 MiB: {rel}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"extensão proibida: {rel}")
        normalized_path = normalize(rel)
        if any(part in normalized_path for part in FORBIDDEN_NAME_PARTS):
            errors.append(f"nome proibido: {rel}")
        if path.suffix.lower() in TEXT_SUFFIXES or path.name == ".gitignore":
            try:
                text = path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                errors.append(f"texto sem UTF-8: {rel}")
                continue
            if ABSOLUTE_PATH.search(text):
                errors.append(f"caminho absoluto de usuário: {rel}")
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    errors.append(f"possível credencial: {rel}")
                    break
        if path.suffix.lower() == ".py":
            try:
                ast.parse(path.read_text(encoding="utf-8-sig"), filename=rel)
            except SyntaxError as exc:
                errors.append(f"sintaxe Python inválida em {rel}: {exc}")
        if path.suffix.lower() == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError as exc:
                errors.append(f"JSON inválido em {rel}: {exc}")
        if path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream)
                headers = next(reader, [])
            blocked = sorted({normalize(h) for h in headers}.intersection(PROHIBITED_HEADERS))
            if blocked:
                errors.append(f"cabeçalho sensível em {rel}: {blocked}")


def check_notebooks(errors: list[str]) -> None:
    for path in sorted((ROOT / "notebooks").glob("*.ipynb")):
        rel = path.relative_to(ROOT).as_posix()
        nb = json.loads(path.read_text(encoding="utf-8-sig"))
        for index, cell in enumerate(nb.get("cells", [])):
            if cell.get("cell_type") != "code":
                continue
            if cell.get("execution_count") is not None or cell.get("outputs"):
                errors.append(f"notebook com execução incorporada: {rel} célula {index}")
            source = "".join(cell.get("source", []))
            if ABSOLUTE_PATH.search(source):
                errors.append(f"notebook com caminho absoluto: {rel} célula {index}")
            try:
                ast.parse(source, filename=f"{rel}:{index}")
            except SyntaxError as exc:
                # Magias Jupyter não são Python puro; só são aceitas se explicitamente iniciadas por % ou !.
                lines = [line.lstrip() for line in source.splitlines() if line.strip()]
                if not any(line.startswith(("%", "!")) for line in lines):
                    errors.append(f"célula Python inválida: {rel} célula {index}: {exc}")


def check_results_manifest(errors: list[str]) -> None:
    path = ROOT / "manifests" / "results.json"
    if not path.exists():
        errors.append("manifesto de resultados ausente")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    listed = set()
    for item in data.get("files", []):
        rel = item["path"]
        listed.add(rel)
        target = ROOT / rel
        if not target.exists():
            errors.append(f"resultado listado ausente: {rel}")
            continue
        if target.stat().st_size != item["size_bytes"]:
            errors.append(f"tamanho divergente: {rel}")
        if digest(target) != item["sha256"]:
            errors.append(f"SHA-256 divergente: {rel}")
    actual = {
        p.relative_to(ROOT).as_posix()
        for base in (ROOT / "results" / "tables", ROOT / "results" / "figures")
        for p in base.rglob("*") if p.is_file()
    }
    if actual != listed:
        errors.append(f"manifesto de resultados não coincide: extras={sorted(actual-listed)}, ausentes={sorted(listed-actual)}")


def check_public_manifest(errors: list[str]) -> None:
    manifest = ROOT / "manifests" / "public_files.json"
    if not manifest.exists():
        errors.append("manifesto público ausente")
        return
    data = json.loads(manifest.read_text(encoding="utf-8"))
    listed = {item["path"]: item for item in data.get("files", [])}
    actual_paths = {
        p.relative_to(ROOT).as_posix()
        for p in public_files()
        if p != manifest
    }
    if set(listed) != actual_paths:
        errors.append(f"lista positiva não coincide: extras={sorted(actual_paths-set(listed))}, ausentes={sorted(set(listed)-actual_paths)}")
    for rel, item in listed.items():
        target = ROOT / rel
        if target.exists() and (target.stat().st_size != item["size_bytes"] or digest(target) != item["sha256"]):
            errors.append(f"inventário público divergente: {rel}")


def main() -> int:
    errors: list[str] = []
    check_files(errors)
    check_notebooks(errors)
    check_results_manifest(errors)
    check_public_manifest(errors)
    if errors:
        print("REPROVADO")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"APROVADO: {len(public_files())} arquivos públicos verificados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
