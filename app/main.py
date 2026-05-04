"""Punto de entrada: lanza la GUI o ejecuta por CLI."""
from __future__ import annotations

import argparse
import sys

from app.config import RunParams
from app.controller import ConsolidationController
from app.gui import launch as launch_gui


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolidador de cuentas corrientes")
    parser.add_argument("--input", help="Carpeta con archivos de entrada")
    parser.add_argument("--output", help="Archivo Excel de salida")
    parser.add_argument("--period", help="Período YYYY-MM")
    parser.add_argument("--no-gui", action="store_true", help="Ejecuta por consola")
    args = parser.parse_args()

    if args.no_gui:
        if not (args.input and args.output and args.period):
            print("--input, --output y --period son obligatorios en --no-gui", file=sys.stderr)
            return 2

        def progress_cb(current: int, total: int, label: str) -> None:
            print(f"[{current}/{total}] {label}", flush=True)

        params = RunParams(input_dir=args.input, output_file=args.output, period=args.period)
        # En CLI el StreamHandler ya imprime los logs en stdout; no pasamos log_cb
        # para evitar salidas duplicadas.
        controller = ConsolidationController(progress_cb=progress_cb, log_cb=None)
        summary = controller.run(params)
        print(f"OK total={summary.total_rows_generated}")
        return 0

    launch_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
