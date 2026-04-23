"""Detección de parsers por nombre de archivo y utilidades de I/O."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..config import PARSER_BY_FILE_KEY
from .strings import normalize_file_key

SUPPORTED_SUFFIXES = {".xlsx", ".xls", ".xlsm", ".pdf"}


def list_input_files(input_dir: str) -> list[Path]:
    p = Path(input_dir)
    if not p.exists() or not p.is_dir():
        return []
    files = []
    for f in sorted(p.iterdir()):
        if not f.is_file():
            continue
        if f.name.startswith("~"):
            continue
        # Ignorar el maestro de ejemplo u otros ficheros genéricos
        lname = f.name.lower()
        if lname.startswith("cuentas corrientes"):
            continue
        if f.suffix.lower() in SUPPORTED_SUFFIXES:
            files.append(f)
    return files


def detect_parser(filename: str) -> Optional[str]:
    """Devuelve el nombre del parser o None si no se reconoce."""
    key = normalize_file_key(filename)
    # Buscamos el match más largo (para evitar que "SMG" matchee antes que "SMG ART")
    best = None
    best_len = -1
    for candidate_key, parser_name in PARSER_BY_FILE_KEY.items():
        if candidate_key in key and len(candidate_key) > best_len:
            best = parser_name
            best_len = len(candidate_key)
    return best


def ensure_parent_dir(path: str) -> None:
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
