"""Modelos de datos internos del consolidador."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Optional


@dataclass
class Record:
    """Registro normalizado único consumido por el workbook_builder."""

    fecha: date
    poliza: str
    asegurado: str
    seccion: str
    compania: str
    tipo: str  # PR | AY | IND
    comisiones: Optional[float]
    prima: Optional[float]
    premio: Optional[float]
    source_file: str
    source_sheet: Optional[str] = None
    source_row: Optional[int] = None
    observacion: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fecha"] = self.fecha.isoformat() if self.fecha else None
        return d


@dataclass
class RejectedRow:
    source_file: str
    source_sheet: Optional[str]
    source_row: Optional[int]
    compania: Optional[str]
    reason: str
    raw: str = ""


@dataclass
class ParseResult:
    records: list[Record] = field(default_factory=list)
    rejected: list[RejectedRow] = field(default_factory=list)
    parser_name: str = ""
    source_file: str = ""

    def extend(self, other: "ParseResult") -> None:
        self.records.extend(other.records)
        self.rejected.extend(other.rejected)


@dataclass
class RunSummary:
    period: str
    input_dir: str
    output_file: str
    total_rows_generated: int = 0
    rows_by_company: dict[str, int] = field(default_factory=dict)
    files_processed: list[str] = field(default_factory=list)
    files_skipped: list[dict] = field(default_factory=list)
    rejected_rows_count: int = 0
    parsers_used: list[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
