"""GUI tkinter para el consolidador."""
from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
from datetime import date
from pathlib import Path
from tkinter import (
    BOTH,
    DISABLED,
    END,
    HORIZONTAL,
    LEFT,
    NORMAL,
    RIGHT,
    Tk,
    Toplevel,
    X,
    filedialog,
    messagebox,
    StringVar,
)
from tkinter import ttk

from .config import RunParams
from .controller import ConsolidationController
from .models import RunSummary


PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")


class ConsolidatorApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        root.title("Consolidador de Cuentas Corrientes")
        root.geometry("860x640")
        root.minsize(760, 520)

        self._log_queue: "queue.Queue[str]" = queue.Queue()
        self._running = False
        self._last_output_dir: Path | None = None
        self._last_summary: RunSummary | None = None

        today = date.today()
        default_period = f"{today.year:04d}-{today.month:02d}"

        self.var_input = StringVar()
        self.var_output = StringVar()
        self.var_period = StringVar(value=default_period)
        self.var_status = StringVar(value="Listo")

        self._build_ui()
        self._poll_log_queue()

    # ---------- UI ----------
    def _build_ui(self) -> None:
        frm = ttk.Frame(self.root, padding=12)
        frm.pack(fill=BOTH, expand=True)

        # Fila: carpeta origen
        row = 0
        ttk.Label(frm, text="Carpeta de origen:").grid(row=row, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.var_input, width=70).grid(row=row, column=1, sticky="we", padx=4)
        ttk.Button(frm, text="Examinar...", command=self._pick_input).grid(row=row, column=2, padx=4)

        # Fila: archivo salida
        row += 1
        ttk.Label(frm, text="Archivo Excel de salida:").grid(row=row, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frm, textvariable=self.var_output, width=70).grid(row=row, column=1, sticky="we", padx=4, pady=(8, 0))
        ttk.Button(frm, text="Guardar como...", command=self._pick_output).grid(row=row, column=2, padx=4, pady=(8, 0))

        # Fila: periodo
        row += 1
        ttk.Label(frm, text="Período (YYYY-MM):").grid(row=row, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frm, textvariable=self.var_period, width=12).grid(row=row, column=1, sticky="w", padx=4, pady=(8, 0))

        # Fila: botones principales
        row += 1
        btns = ttk.Frame(frm)
        btns.grid(row=row, column=0, columnspan=3, sticky="we", pady=(12, 4))
        self.btn_run = ttk.Button(btns, text="Procesar", command=self._run)
        self.btn_run.pack(side=LEFT)
        self.btn_open = ttk.Button(btns, text="Abrir carpeta de salida", command=self._open_output, state=DISABLED)
        self.btn_open.pack(side=LEFT, padx=8)

        # Fila: progreso
        row += 1
        self.progress = ttk.Progressbar(frm, orient=HORIZONTAL, mode="determinate")
        self.progress.grid(row=row, column=0, columnspan=3, sticky="we", pady=6)

        # Fila: estado
        row += 1
        ttk.Label(frm, textvariable=self.var_status, anchor="w").grid(row=row, column=0, columnspan=3, sticky="we")

        # Fila: log
        row += 1
        ttk.Label(frm, text="Log:").grid(row=row, column=0, sticky="w", pady=(8, 0))
        row += 1
        log_frame = ttk.Frame(frm)
        log_frame.grid(row=row, column=0, columnspan=3, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame)
        scrollbar.pack(side=RIGHT, fill="y")
        from tkinter import Text  # import tardío para PyInstaller
        self.log_text = Text(log_frame, height=18, yscrollcommand=scrollbar.set, wrap="word")
        self.log_text.pack(fill=BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)

        # responsive
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(row, weight=1)

    # ---------- acciones ----------
    def _pick_input(self) -> None:
        d = filedialog.askdirectory(title="Elegir carpeta de archivos origen")
        if d:
            self.var_input.set(d)
            if not self.var_output.get():
                out_default = Path(d).parent / "CUENTAS_CORRIENTES_CONSOLIDADO.xlsx"
                self.var_output.set(str(out_default))

    def _pick_output(self) -> None:
        f = filedialog.asksaveasfilename(
            title="Guardar Excel consolidado como...",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile="CUENTAS_CORRIENTES_CONSOLIDADO.xlsx",
        )
        if f:
            self.var_output.set(f)

    def _open_output(self) -> None:
        if self._last_output_dir and self._last_output_dir.exists():
            try:
                if sys.platform.startswith("win"):
                    os.startfile(str(self._last_output_dir))  # type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(self._last_output_dir)])
                else:
                    subprocess.Popen(["xdg-open", str(self._last_output_dir)])
            except Exception as exc:
                messagebox.showerror("Error", f"No se pudo abrir la carpeta: {exc}")

    def _run(self) -> None:
        if self._running:
            return
        input_dir = self.var_input.get().strip()
        output_file = self.var_output.get().strip()
        period = self.var_period.get().strip()

        if not input_dir or not Path(input_dir).is_dir():
            messagebox.showerror("Datos inválidos", "Carpeta de origen inválida.")
            return
        if not output_file:
            messagebox.showerror("Datos inválidos", "Falta archivo de salida.")
            return
        if not PERIOD_RE.match(period):
            messagebox.showerror("Datos inválidos", "Período debe ser YYYY-MM.")
            return

        self._running = True
        self.btn_run.config(state=DISABLED)
        self.btn_open.config(state=DISABLED)
        self.log_text.delete("1.0", END)
        self.progress["value"] = 0
        self.var_status.set("Procesando...")

        params = RunParams(input_dir=input_dir, output_file=output_file, period=period)

        t = threading.Thread(target=self._run_thread, args=(params,), daemon=True)
        t.start()

    def _run_thread(self, params: RunParams) -> None:
        try:
            ctrl = ConsolidationController(
                progress_cb=self._on_progress,
                log_cb=self._enqueue_log,
            )
            summary = ctrl.run(params)
            self._last_output_dir = Path(params.output_file).parent.resolve()
            self._last_summary = summary
            self._enqueue_log("=== FIN ===")
            self._enqueue_log(
                f"Total={summary.total_rows_generated} | archivos procesados={len(summary.files_processed)} "
                f"| omitidos={len(summary.files_skipped)} | rechazados={summary.rejected_rows_count}"
            )
            for comp, n in summary.rows_by_company.items():
                self._enqueue_log(f"  {comp}: {n}")
            self.root.after(0, self._on_done_ok)
        except Exception as exc:
            self._enqueue_log(f"ERROR: {exc}")
            self.root.after(0, lambda: self._on_done_error(exc))

    def _on_done_ok(self) -> None:
        self._running = False
        self.btn_run.config(state=NORMAL)
        self.btn_open.config(state=NORMAL)
        self.progress["value"] = self.progress["maximum"]
        total = self._last_summary.total_rows_generated if self._last_summary else 0
        self.var_status.set(f"Terminado. {total} filas generadas.")

    def _on_done_error(self, exc: Exception) -> None:
        self._running = False
        self.btn_run.config(state=NORMAL)
        self.var_status.set(f"Error: {exc}")
        messagebox.showerror("Error", str(exc))

    # ---------- progreso + log ----------
    def _on_progress(self, current: int, total: int, label: str) -> None:
        def update():
            self.progress["maximum"] = max(1, total)
            self.progress["value"] = current
            self.var_status.set(f"[{current}/{total}] {label}")
        self.root.after(0, update)

    def _enqueue_log(self, msg: str) -> None:
        self._log_queue.put(msg)

    def _poll_log_queue(self) -> None:
        try:
            while True:
                msg = self._log_queue.get_nowait()
                self.log_text.insert(END, msg + "\n")
                self.log_text.see(END)
        except queue.Empty:
            pass
        self.root.after(120, self._poll_log_queue)


def launch() -> None:
    root = Tk()
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    ConsolidatorApp(root)
    root.mainloop()
