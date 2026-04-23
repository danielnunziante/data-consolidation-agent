"""Helpers de logging."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable


class CallbackHandler(logging.Handler):
    """Handler que redirige mensajes de log a un callback (para la GUI)."""

    def __init__(self, callback: Callable[[str], None]):
        super().__init__()
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._callback(msg)
        except Exception:
            self.handleError(record)


def configure_logger(log_path: str, gui_callback: Callable[[str], None] | None = None) -> logging.Logger:
    """Configura un logger raíz `consolidador` con archivo + stream + callback opcional."""
    logger = logging.getLogger("consolidador")
    logger.setLevel(logging.DEBUG)
    # limpiar handlers previos para no duplicar en ejecuciones repetidas
    for h in list(logger.handlers):
        logger.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_path, encoding="utf-8", mode="w")
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO)
    logger.addHandler(sh)

    if gui_callback:
        gh = CallbackHandler(gui_callback)
        gh.setFormatter(fmt)
        gh.setLevel(logging.INFO)
        logger.addHandler(gh)

    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("consolidador")
