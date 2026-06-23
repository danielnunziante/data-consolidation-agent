"""OCR de PDFs escaneados vía visión de OpenAI (opcional).

Algunas aseguradoras (p.ej. VICTORIA ART) entregan la cuenta corriente como
un PDF escaneado: cada página es una imagen, sin capa de texto extraíble. Para
esos casos rasterizamos cada página y se la enviamos a un modelo de visión de
OpenAI, que lee la tabla y la devuelve como JSON estructurado.

Es OPCIONAL. Si no hay API key configurada (o faltan las librerías), las
funciones lo indican y el parser cae al comportamiento previo (rechazar la
fila pidiendo OCR). Así una instalación sin OpenAI sigue funcionando igual y
los tests/builds no dependen de la red.

La API key y el modelo se resuelven con la misma prioridad que `fx.py`:
1. Variables de entorno `OPENAI_API_KEY` / `OCR_MODEL`.
2. Archivo `config/ocr.json` -> {"openai_api_key": "...", "model": "gpt-4o"}.

`config/ocr.json` contiene un secreto: está en `.gitignore` y la GUI lo
escribe en la máquina del cliente. El cliente usa su propia cuenta de OpenAI.
"""
from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
from typing import Optional

from .logging_utils import get_logger

log = get_logger()

# Modelo de visión por defecto. Configurable por si el cliente quiere otro.
DEFAULT_MODEL = "gpt-4o"

# Lado más largo (px) de la imagen que se envía al modelo. OpenAI reescala
# internamente cualquier imagen a un máximo de ~2048px (y el lado corto a 768),
# así que enviar más es desperdiciar tokens. Apuntamos a ese tope.
MAX_LONG_EDGE = 2048

# Lado más largo (px) al que rasterizamos ANTES de recortar y reducir. El PDF
# escaneado original es enorme (~10208px); renderizar alto y luego reducir da un
# downscale más limpio (texto más legible) que renderizar directo a 2048.
RENDER_LONG_EDGE = 4200

# Umbral para considerar un píxel como "contenido" (no fondo) al recortar
# márgenes en blanco. El escaneo es bilevel (negro sobre blanco).
_TRIM_THRESHOLD = 32
_TRIM_MARGIN_PX = 16


# --------------------------------------------------------------------------- #
# Config (API key + modelo)
# --------------------------------------------------------------------------- #
def _config_path() -> Path:
    """Ruta canónica de config/ocr.json (junto al proyecto)."""
    return Path(__file__).resolve().parent.parent.parent / "config" / "ocr.json"


def _load_config_file() -> dict:
    path = _config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        log.warning("config/ocr.json inválido: %s", exc)
        return {}


def get_openai_api_key() -> Optional[str]:
    """Devuelve la API key de OpenAI o None si no está configurada."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    key = str(_load_config_file().get("openai_api_key", "")).strip()
    return key or None


def get_ocr_model() -> str:
    m = os.environ.get("OCR_MODEL", "").strip()
    if m:
        return m
    m = str(_load_config_file().get("model", "")).strip()
    return m or DEFAULT_MODEL


def read_ocr_config() -> dict:
    """Lee config/ocr.json para prellenar la GUI (ignora env vars a propósito)."""
    cfg = _load_config_file()
    return {
        "openai_api_key": str(cfg.get("openai_api_key", "") or ""),
        "model": str(cfg.get("model", "") or "") or DEFAULT_MODEL,
    }


def write_ocr_config(api_key: str, model: str = "") -> Path:
    """Persiste la API key y el modelo en config/ocr.json. Devuelve la ruta."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "openai_api_key": (api_key or "").strip(),
        "model": (model or "").strip() or DEFAULT_MODEL,
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def ocr_available() -> tuple[bool, str]:
    """(disponible, motivo). disponible=True si hay key y las librerías están."""
    if not get_openai_api_key():
        return False, "no hay OPENAI_API_KEY configurada (env var o config/ocr.json)"
    missing = []
    for mod in ("pypdfium2", "PIL", "openai"):
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    if missing:
        return False, f"falta(n) librería(s): {', '.join(missing)}"
    return True, "ok"


# --------------------------------------------------------------------------- #
# Rasterizado + visión
# --------------------------------------------------------------------------- #
def _trim_whitespace(img):
    """Recorta los márgenes en blanco para que el contenido llene el marco.

    Quitar el gran espacio vacío (típico al pie de estos reportes) hace que la
    tabla ocupe más píxeles tras el reescalado interno de OpenAI -> texto más
    legible. Robusto a ruido: sólo cuenta píxeles bien distintos del blanco.
    """
    from PIL import Image, ImageChops

    bg = Image.new("RGB", img.size, (255, 255, 255))
    diff = ImageChops.difference(img, bg).convert("L")
    mask = diff.point(lambda px: 255 if px > _TRIM_THRESHOLD else 0)
    bbox = mask.getbbox()
    if not bbox:
        return img
    left, top, right, bottom = bbox
    left = max(0, left - _TRIM_MARGIN_PX)
    top = max(0, top - _TRIM_MARGIN_PX)
    right = min(img.width, right + _TRIM_MARGIN_PX)
    bottom = min(img.height, bottom + _TRIM_MARGIN_PX)
    return img.crop((left, top, right, bottom))


def _fit_long_edge(img, max_long_edge: int):
    from PIL import Image

    long_side = max(img.size)
    if long_side <= max_long_edge:
        return img
    scale = max_long_edge / long_side
    new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    return img.resize(new_size, Image.LANCZOS)


def render_pdf_pages(
    file_path: str,
    max_long_edge: int = MAX_LONG_EDGE,
    *,
    trim_whitespace: bool = True,
) -> list[bytes]:
    """Rasteriza cada página del PDF a PNG (bytes). Import perezoso.

    Renderiza alto (RENDER_LONG_EDGE), recorta el blanco, y reduce a
    `max_long_edge` para maximizar la resolución efectiva del contenido.
    """
    import pypdfium2 as pdfium

    out: list[bytes] = []
    pdf = pdfium.PdfDocument(file_path)
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            long_pt = max(page.get_size()) or 1
            scale = max(1.0, min(8.0, RENDER_LONG_EDGE / long_pt))
            pil = page.render(scale=scale).to_pil().convert("RGB")
            if trim_whitespace:
                pil = _trim_whitespace(pil)
            pil = _fit_long_edge(pil, max_long_edge)
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            out.append(buf.getvalue())
    finally:
        pdf.close()
    return out


def vision_extract_json(
    images: list[bytes],
    system_prompt: str,
    user_prompt: str,
    *,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    image_format: str = "png",
) -> dict:
    """Envía las imágenes al modelo de visión de OpenAI y parsea el JSON.

    Devuelve el dict parseado. Lanza RuntimeError con un mensaje claro si falla
    (sin key, error de red/API, o respuesta no-JSON).
    """
    from openai import OpenAI

    api_key = api_key or get_openai_api_key()
    if not api_key:
        raise RuntimeError("OCR sin OPENAI_API_KEY configurada")
    model = model or get_ocr_model()

    content: list[dict] = [{"type": "text", "text": user_prompt}]
    for img in images:
        b64 = base64.b64encode(img).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{image_format};base64,{b64}",
                    "detail": "high",
                },
            }
        )

    client = OpenAI(api_key=api_key)
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
        )
    except Exception as exc:  # errores de red/autenticación/cuota
        raise RuntimeError(f"llamada a OpenAI falló ({model}): {exc}") from exc

    text = (resp.choices[0].message.content or "").strip() or "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"respuesta de OpenAI no es JSON válido: {exc}: {text[:200]}")
