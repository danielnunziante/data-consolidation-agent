"""Controlador: orquesta la consolidación end-to-end."""
from __future__ import annotations

import csv
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .config import RunParams
from .models import ParseResult, Record, RunSummary
from .parsers import get_parser
from .utils.dates import first_day_of_period
from .utils.files import detect_parser, ensure_parent_dir, list_input_files
from .utils.logging_utils import configure_logger
from .utils.seccion import normalize_records
from .validators import (
    expected_counts_warnings,
    summarize_by_company,
    validate_records,
)
from .workbook_builder import build_workbook


ProgressCb = Callable[[int, int, str], None]  # (current, total, label)
LogCb = Callable[[str], None]


class ConsolidationController:
    def __init__(
        self,
        progress_cb: Optional[ProgressCb] = None,
        log_cb: Optional[LogCb] = None,
    ) -> None:
        self.progress_cb = progress_cb or (lambda c, t, l: None)
        self.log_cb = log_cb

    def _progress(self, current: int, total: int, label: str) -> None:
        try:
            self.progress_cb(current, total, label)
        except Exception:
            pass

    def run(self, params: RunParams) -> RunSummary:
        started = datetime.now().isoformat(timespec="seconds")
        started_t = time.time()

        output_path = Path(params.output_file).expanduser().resolve()
        ensure_parent_dir(str(output_path))

        # Logs se emiten junto al archivo de salida
        out_dir = output_path.parent
        log_path = out_dir / "process_log.txt"
        rejected_path = out_dir / "rejected_rows.csv"
        summary_path = out_dir / "summary.json"

        logger = configure_logger(str(log_path), self.log_cb)
        logger.info("=== Inicio consolidación ===")
        logger.info("Carpeta origen: %s", params.input_dir)
        logger.info("Archivo destino: %s", params.output_file)
        logger.info("Período: %s", params.period)

        try:
            fecha = first_day_of_period(params.period)
        except ValueError as exc:
            logger.error("Período inválido: %s", exc)
            raise

        files = list_input_files(params.input_dir)
        logger.info("Archivos detectados: %d", len(files))

        summary = RunSummary(
            period=params.period,
            input_dir=str(Path(params.input_dir).resolve()),
            output_file=str(output_path),
            started_at=started,
        )

        all_records: list[Record] = []
        all_rejected = []

        total_steps = max(1, len(files) + 2)
        step = 0

        for f in files:
            step += 1
            parser_name = detect_parser(f.name)
            if parser_name is None:
                logger.warning("Omitido (sin parser): %s", f.name)
                summary.files_skipped.append({"file": f.name, "reason": "parser no implementado"})
                self._progress(step, total_steps, f"{f.name} (omitido)")
                continue

            parser_fn = get_parser(parser_name)
            if parser_fn is None:
                logger.warning("Omitido (parser desconocido %s): %s", parser_name, f.name)
                summary.files_skipped.append({"file": f.name, "reason": f"parser {parser_name} no registrado"})
                self._progress(step, total_steps, f"{f.name} (omitido)")
                continue

            logger.info("Procesando %s con parser=%s", f.name, parser_name)
            self._progress(step, total_steps, f"{f.name}")

            try:
                result: ParseResult = parser_fn(str(f), fecha)
            except Exception as exc:
                logger.exception("Error en parser %s: %s", parser_name, exc)
                summary.files_skipped.append({"file": f.name, "reason": f"excepción: {exc}"})
                continue

            if not result.records and not result.rejected:
                summary.files_skipped.append({"file": f.name, "reason": "sin filas"})
                logger.warning(" -> sin filas válidas")
                continue

            all_records.extend(result.records)
            all_rejected.extend(result.rejected)
            summary.files_processed.append(f.name)
            if parser_name not in summary.parsers_used:
                summary.parsers_used.append(parser_name)

            logger.info(
                " -> %d filas generadas, %d filas rechazadas",
                len(result.records),
                len(result.rejected),
            )

        # Normalizar la columna SECCION según equivalencias por compañía
        unmapped = normalize_records(all_records)
        if unmapped:
            total_unmapped = sum(unmapped.values())
            logger.info(
                "SECCION: %d filas sin equivalencia (se conserva el valor crudo) "
                "en %d combinaciones (compañía, sección):",
                total_unmapped,
                len(unmapped),
            )
            for (comp, sec), n in sorted(unmapped.items(), key=lambda kv: (-kv[1], kv[0])):
                logger.info("  - %s | %r x%d", comp, sec, n)

        # Validar + construir workbook
        step += 1
        self._progress(step, total_steps, "Validando registros")
        warnings = validate_records(all_records)
        for w in warnings[:50]:  # evitar spam infinito
            logger.warning(w)
        if len(warnings) > 50:
            logger.warning("... %d warnings adicionales ocultos ...", len(warnings) - 50)

        rows_by_company = summarize_by_company(all_records)
        present = set(rows_by_company.keys())
        for w in expected_counts_warnings(rows_by_company, present):
            logger.warning(w)

        summary.total_rows_generated = len(all_records)
        summary.rows_by_company = dict(sorted(rows_by_company.items()))
        summary.rejected_rows_count = len(all_rejected)

        step += 1
        self._progress(step, total_steps, "Generando Excel")
        build_workbook(all_records, str(output_path), fecha)
        logger.info("Excel generado: %s", output_path)

        # Escribir rejected_rows.csv
        with rejected_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["source_file", "source_sheet", "source_row", "compania", "reason", "raw"],
            )
            writer.writeheader()
            for r in all_rejected:
                writer.writerow(
                    {
                        "source_file": r.source_file,
                        "source_sheet": r.source_sheet or "",
                        "source_row": r.source_row or "",
                        "compania": r.compania or "",
                        "reason": r.reason,
                        "raw": r.raw,
                    }
                )
        logger.info("Filas rechazadas: %d (%s)", len(all_rejected), rejected_path)

        summary.finished_at = datetime.now().isoformat(timespec="seconds")
        with summary_path.open("w", encoding="utf-8") as fh:
            json.dump(summary.to_dict(), fh, ensure_ascii=False, indent=2)
        logger.info("Resumen guardado: %s", summary_path)

        elapsed = time.time() - started_t
        logger.info("=== Fin consolidación en %.2fs ===", elapsed)

        return summary
