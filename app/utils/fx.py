"""Tipos de cambio USD->ARS por compañía.

Las compañías que liquidan en dólares (INTEGRITY, SAN CRISTOBAL USD,
MERCANTIL ANDINA USD, etc.) no exponen el tipo de cambio en el archivo:
el cliente lo busca en la web de la aseguradora y lo aplica a mano.

Para no hardcodear valores, esta utilidad expone una función única
`get_fx(company)` que resuelve el TC con la siguiente prioridad:

1. Variable de entorno `<COMPANY_KEY>_USD_TC` (ej `INTEGRITY_USD_TC=1234.56`).
2. Variable de entorno general `FX_TC_BY_COMPANY` con JSON
   (ej `FX_TC_BY_COMPANY={"INTEGRITY": 1234.56, "SAN_CRISTOBAL": 1240}`).
3. Archivo `config/fx.json` con el mismo formato JSON.
4. None -> el parser debe rechazar la fila con razón clara.

`company` se normaliza a mayúsculas + guion bajo (espacios y guiones se
reemplazan por `_`), de modo que el llamador puede pasar "INTEGRITY",
"SAN CRISTOBAL USD" o "san_cristobal" indistintamente.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .logging_utils import get_logger
from .numbers import to_float

log = get_logger()


# Compañías que requieren TC USD externo (el cliente lo busca en la web de la
# aseguradora). Cada entrada es (display_name, fx_key).
# - display_name: lo que se muestra en la GUI.
# - fx_key: la clave normalizada usada en config/fx.json y en la env var
#   correspondiente (`<KEY>_USD_TC`).
FX_COMPANIES: list[tuple[str, str]] = [
    ("INTEGRITY", "INTEGRITY"),
    ("SAN CRISTOBAL USD", "SAN_CRISTOBAL"),
    ("MERCANTIL ANDINA USD", "MERCANTIL_ANDINA"),
]


def _norm_key(company: str) -> str:
    return (
        company.strip()
        .upper()
        .replace(" USD", "")
        .replace("-", "_")
        .replace(" ", "_")
    )


def _config_path() -> Path:
    """Ruta canónica de config/fx.json (junto al proyecto)."""
    return Path(__file__).resolve().parent.parent.parent / "config" / "fx.json"


@lru_cache(maxsize=1)
def _load_json_map() -> dict[str, float]:
    out: dict[str, float] = {}
    raw_env = os.environ.get("FX_TC_BY_COMPANY", "").strip()
    if raw_env:
        try:
            data = json.loads(raw_env)
            for k, v in data.items():
                fv = to_float(v)
                if fv is not None:
                    out[_norm_key(str(k))] = fv
        except Exception as exc:
            log.warning("FX_TC_BY_COMPANY inválido: %s", exc)

    candidates = [
        Path("config") / "fx.json",
        _config_path(),
    ]
    for path in candidates:
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                for k, v in data.items():
                    fv = to_float(v)
                    if fv is not None:
                        out.setdefault(_norm_key(str(k)), fv)
                break
        except Exception as exc:
            log.warning("config/fx.json inválido (%s): %s", path, exc)
    return out


def get_fx(company: str) -> Optional[float]:
    """Devuelve el TC USD->ARS para `company` o None si no está configurado."""
    key = _norm_key(company)
    env_var = f"{key}_USD_TC"
    raw = os.environ.get(env_var)
    if raw:
        v = to_float(raw)
        if v is not None and v > 0:
            return v
        log.warning("Variable %s no es número válido: %r", env_var, raw)
    fmap = _load_json_map()
    v = fmap.get(key)
    if v is not None and v > 0:
        return v
    return None


def reset_cache() -> None:
    """Limpia el cache del mapa JSON. Necesario después de escribir
    config/fx.json desde la GUI para que la próxima lectura levante los valores
    nuevos."""
    _load_json_map.cache_clear()


def read_fx_config() -> dict[str, float]:
    """Lee config/fx.json y devuelve un dict normalizado (key -> float).

    Se ignora la env `FX_TC_BY_COMPANY` a propósito: este helper sirve para
    pre-llenar la GUI con los valores persistidos del último run.
    """
    path = _config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("read_fx_config: no se pudo leer %s (%s)", path, exc)
        return {}
    out: dict[str, float] = {}
    for k, v in data.items():
        fv = to_float(v)
        if fv is not None and fv > 0:
            out[_norm_key(str(k))] = fv
    return out


def write_fx_config(values: dict[str, float]) -> Path:
    """Persiste `values` en config/fx.json y limpia el cache.

    `values` es `{display_or_key: numero}`; las claves se normalizan. Los
    valores <= 0 o no numéricos se ignoran. Devuelve la ruta escrita.
    """
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean: dict[str, float] = {}
    for k, v in (values or {}).items():
        fv = to_float(v)
        if fv is not None and fv > 0:
            clean[_norm_key(str(k))] = round(float(fv), 4)
    path.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    reset_cache()
    return path
