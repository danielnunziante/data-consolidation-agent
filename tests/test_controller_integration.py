"""Test de integración mínimo: carpeta vacía, se genera workbook vacío y summary.json."""
import json
from pathlib import Path

from app.config import RunParams
from app.controller import ConsolidationController


def test_controller_empty_folder(tmp_path: Path):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    output_file = tmp_path / "out" / "consolidado.xlsx"

    ctrl = ConsolidationController()
    summary = ctrl.run(RunParams(input_dir=str(input_dir), output_file=str(output_file), period="2026-03"))

    assert output_file.exists()
    assert (output_file.parent / "summary.json").exists()
    assert (output_file.parent / "process_log.txt").exists()
    assert (output_file.parent / "rejected_rows.csv").exists()

    data = json.loads((output_file.parent / "summary.json").read_text(encoding="utf-8"))
    assert data["period"] == "2026-03"
    assert data["total_rows_generated"] == 0
    assert summary.total_rows_generated == 0
