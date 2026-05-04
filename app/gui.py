"""GUI Coberser — diseño simple, responsivo, con scroll global confiable.

Reglas estrictas para evitar los bugs históricos:
- `CTkScrollableFrame` como contenedor único para todo el contenido scrolleable.
- Los hijos directos del scroll usan SIEMPRE `pack(fill=X)`. Nunca se setea
  `width=` en píxeles a un widget hijo (el `CTkScrollableFrame` ya sincroniza
  el ancho interno con su viewport).
- Dentro de cada tarjeta se usa `grid` con `columnconfigure(weight=1)` para
  que los inputs se estiren y los botones queden fijos.
- `wraplength` siempre estático (cabe holgado en el `minsize`); nunca dinámico
  (eso producía un loop de `<Configure>` y "No responde").
- Sin cálculos manuales de píxeles, sin `winfo_width`, sin `after` de layout.
"""
from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
from datetime import date
from pathlib import Path

import customtkinter as ctk
from tkinter import (
    BOTH,
    Canvas,
    END,
    StringVar,
    X,
    filedialog,
    messagebox,
)

from .config import RunParams
from .controller import ConsolidationController
from .models import RunSummary


PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")

# ------------------------------------------------------------------
# Paleta y tipografías
# ------------------------------------------------------------------
APP_BG = "#0f1117"
SURFACE = "#171923"
SURFACE_MUTED = "#12151c"
INPUT_BG = "#1c212c"
INPUT_FOCUS = "#232836"
BORDER_SUBTLE = "#2d3344"
BORDER_STRONG = "#3d4659"
ACCENT = "#3b82f6"
ACCENT_HOVER = "#2563eb"
ACCENT_PRESS = "#1d4ed8"
SUCCESS = "#22c55e"
WARNING = "#f59e0b"
ERROR = "#ef4444"
TEXT_PRIMARY = "#e8eaed"
TEXT_SECONDARY = "#94a3b8"
TEXT_MUTED = "#64748b"

FONT_DISPLAY = ("Segoe UI Semibold", 22)
FONT_H2 = ("Segoe UI Semibold", 13)
FONT_BODY = ("Segoe UI", 12)
FONT_BODY_SM = ("Segoe UI", 11)
FONT_LABEL = ("Segoe UI", 11)
FONT_OVERLINE = ("Segoe UI", 10)
FONT_BTN = ("Segoe UI", 13, "bold")
FONT_BTN_SECONDARY = ("Segoe UI", 12)
FONT_LOG = ("Consolas", 11)
FONT_HINT = ("Segoe UI", 10)

PAD_X = 24       # padding lateral de las tarjetas
PAD_INNER = 20   # padding interno de cada tarjeta
WRAP_TEXT = 720  # estático: cabe en minsize=820 menos padding
LOG_HEIGHT = 260 # alto fijo del visor de log


class ConsolidatorApp:
    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        root.title("Coberser · Consolidador de cuentas corrientes")
        root.geometry("960x700")
        root.minsize(820, 600)
        root.configure(fg_color=APP_BG)

        self._log_queue: queue.Queue[str] = queue.Queue()
        self._running = False
        self._last_output_dir: Path | None = None
        self._last_summary: RunSummary | None = None
        self._pulse_after: str | None = None
        self._status_mode = "idle"
        self._dot_id: int | None = None

        today = date.today()
        default_period = f"{today.year:04d}-{today.month:02d}"

        self.var_input = StringVar()
        self.var_output = StringVar()
        self.var_period = StringVar(value=default_period)
        self.var_status = StringVar(value="Listo para procesar")
        self.var_progress_label = StringVar(value="")

        self.var_input.trace_add("write", lambda *_: self._update_open_folder_state())
        self.var_output.trace_add("write", lambda *_: self._update_open_folder_state())

        self._build_ui()
        self._poll_log_queue()
        self._set_status_appearance("idle")
        self._update_open_folder_state()

        self.root.bind("<Control-Return>", lambda _e: self._run())
        self.root.bind("<F5>", lambda _e: self._run())

    # ------------------------------------------------------------------
    # Helpers de estilo
    # ------------------------------------------------------------------
    def _card(self, parent) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            parent,
            fg_color=SURFACE,
            corner_radius=14,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )

    def _entry(self, parent, variable: StringVar | None = None) -> ctk.CTkEntry:
        e = ctk.CTkEntry(
            parent,
            textvariable=variable,
            height=40,
            font=FONT_BODY,
            fg_color=INPUT_BG,
            text_color=TEXT_PRIMARY,
            placeholder_text_color=TEXT_MUTED,
            border_width=1,
            border_color=BORDER_SUBTLE,
            corner_radius=10,
        )
        e.bind("<FocusIn>", lambda _e: e.configure(fg_color=INPUT_FOCUS, border_color=ACCENT))
        e.bind("<FocusOut>", lambda _e: e.configure(fg_color=INPUT_BG, border_color=BORDER_SUBTLE))
        return e

    def _btn_primary(self, parent, text: str, command) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#ffffff",
            height=42,
            width=160,
            font=FONT_BTN,
            corner_radius=22,
        )

    def _btn_secondary(self, parent, text: str, command, *, width: int = 160) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            height=40,
            font=FONT_BTN_SECONDARY,
            fg_color="transparent",
            hover_color=SURFACE_MUTED,
            text_color=TEXT_PRIMARY,
            border_width=1,
            border_color=BORDER_STRONG,
            corner_radius=10,
        )

    # ------------------------------------------------------------------
    # Construcción del layout
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # Franja de acento arriba (fija)
        accent_strip = ctk.CTkFrame(self.root, fg_color=ACCENT, corner_radius=0, height=3)
        accent_strip.pack(fill=X, side="top")
        accent_strip.pack_propagate(False)

        # Contenedor scrolleable principal — único responsable del scroll global.
        scroll = ctk.CTkScrollableFrame(
            self.root,
            fg_color=APP_BG,
            corner_radius=0,
            border_width=0,
            scrollbar_fg_color=BORDER_SUBTLE,
            scrollbar_button_color=TEXT_MUTED,
            scrollbar_button_hover_color=TEXT_SECONDARY,
        )
        scroll.pack(fill=BOTH, expand=True, side="top")
        self.scroll = scroll

        self._build_header(scroll)
        self._build_form_card(scroll)
        self._build_action_card(scroll)
        self._build_log_card(scroll)

    # ---------- Header ----------
    def _build_header(self, parent) -> None:
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill=X, padx=PAD_X, pady=(18, 6))

        ctk.CTkLabel(
            header,
            text="Coberser",
            font=FONT_DISPLAY,
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).pack(anchor="w", fill=X)

        badge = ctk.CTkFrame(header, fg_color=SURFACE, corner_radius=6)
        badge.pack(anchor="w", pady=(6, 0))
        ctk.CTkLabel(
            badge,
            text="  Consolidador de cuentas corrientes  ",
            font=FONT_HINT,
            text_color=TEXT_MUTED,
        ).pack(padx=8, pady=4)

        ctk.CTkLabel(
            header,
            text=(
                "Seleccioná la carpeta con los archivos de cada aseguradora, definí el Excel "
                "de salida y el período. Al procesar se generará un libro único según las "
                "reglas de cada empresa."
            ),
            font=FONT_BODY,
            text_color=TEXT_SECONDARY,
            justify="left",
            anchor="w",
            wraplength=WRAP_TEXT,
        ).pack(anchor="w", fill=X, pady=(10, 0))

    # ---------- Tarjeta de configuración ----------
    def _build_form_card(self, parent) -> None:
        card = self._card(parent)
        card.pack(fill=X, padx=PAD_X, pady=(10, 8))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill=X, padx=PAD_INNER, pady=PAD_INNER)
        inner.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            inner,
            text="CONFIGURACIÓN DEL PROCESO",
            font=FONT_OVERLINE,
            text_color=TEXT_MUTED,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 12))

        # ---- 1. Carpeta de origen ----
        ctk.CTkLabel(
            inner, text="1 · Carpeta de origen",
            font=FONT_LABEL, text_color=TEXT_SECONDARY, anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 6))

        row_in = ctk.CTkFrame(inner, fg_color="transparent")
        row_in.grid(row=2, column=0, sticky="ew")
        row_in.grid_columnconfigure(0, weight=1)
        self.ent_input = self._entry(row_in, self.var_input)
        self.ent_input.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self._pick_in_btn = self._btn_secondary(
            row_in, "Seleccionar carpeta…", self._pick_input, width=180
        )
        self._pick_in_btn.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(
            inner,
            text="Debe contener Excel/PDF/HTML según cada compañía.",
            font=FONT_HINT, text_color=TEXT_MUTED, anchor="w",
        ).grid(row=3, column=0, sticky="ew", pady=(6, 0))

        # ---- 2. Excel de salida ----
        ctk.CTkLabel(
            inner, text="2 · Archivo Excel de salida",
            font=FONT_LABEL, text_color=TEXT_SECONDARY, anchor="w",
        ).grid(row=4, column=0, sticky="ew", pady=(18, 6))

        row_out = ctk.CTkFrame(inner, fg_color="transparent")
        row_out.grid(row=5, column=0, sticky="ew")
        row_out.grid_columnconfigure(0, weight=1)
        self.ent_output = self._entry(row_out, self.var_output)
        self.ent_output.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self._pick_out_btn = self._btn_secondary(
            row_out, "Guardar como…", self._pick_output, width=160
        )
        self._pick_out_btn.grid(row=0, column=1, sticky="e")

        # ---- 3. Período ----
        ctk.CTkLabel(
            inner, text="3 · Período contable",
            font=FONT_LABEL, text_color=TEXT_SECONDARY, anchor="w",
        ).grid(row=6, column=0, sticky="ew", pady=(18, 6))

        row_per = ctk.CTkFrame(inner, fg_color="transparent")
        row_per.grid(row=7, column=0, sticky="ew")
        row_per.grid_columnconfigure(1, weight=1)
        self.ent_period = self._entry(row_per, self.var_period)
        self.ent_period.configure(width=140)
        self.ent_period.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            row_per,
            text="Formato obligatorio:  AAAA-MM",
            font=FONT_HINT, text_color=TEXT_MUTED, anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(14, 0))

        ctk.CTkLabel(
            inner,
            text="Atajo: Ctrl+Enter o F5 para procesar cuando los datos sean válidos.",
            font=FONT_HINT, text_color=TEXT_MUTED, anchor="w",
        ).grid(row=8, column=0, sticky="ew", pady=(16, 0))

    # ---------- Barra de acciones ----------
    def _build_action_card(self, parent) -> None:
        card = self._card(parent)
        card.pack(fill=X, padx=PAD_X, pady=8)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill=X, padx=PAD_INNER, pady=16)
        inner.grid_columnconfigure(0, weight=1)

        actions = ctk.CTkFrame(inner, fg_color="transparent")
        actions.grid(row=0, column=0, sticky="ew")
        actions.grid_columnconfigure(0, weight=0)
        actions.grid_columnconfigure(1, weight=0)
        actions.grid_columnconfigure(2, weight=1)

        self.btn_run = self._btn_primary(actions, "Procesar", self._run)
        self.btn_run.grid(row=0, column=0, sticky="w", padx=(0, 10))

        self.btn_open = self._btn_secondary(
            actions, "Abrir carpeta de salida", self._open_output, width=210
        )
        self.btn_open.grid(row=0, column=1, sticky="w")

        prog_col = ctk.CTkFrame(actions, fg_color="transparent")
        prog_col.grid(row=0, column=2, sticky="ew", padx=(24, 0))
        prog_col.grid_columnconfigure(0, weight=1)

        prog_top = ctk.CTkFrame(prog_col, fg_color="transparent")
        prog_top.grid(row=0, column=0, sticky="ew")
        prog_top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            prog_top, text="Progreso",
            font=FONT_LABEL, text_color=TEXT_MUTED, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            prog_top, textvariable=self.var_progress_label,
            font=FONT_BODY_SM, text_color=TEXT_SECONDARY, anchor="e",
        ).grid(row=0, column=1, sticky="e")

        self.progress = ctk.CTkProgressBar(
            prog_col,
            mode="determinate",
            progress_color=ACCENT,
            fg_color=INPUT_BG,
            corner_radius=6,
            height=8,
        )
        self.progress.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.progress.set(0)

        # Estado: dot + texto
        status = ctk.CTkFrame(inner, fg_color="transparent")
        status.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        status.grid_columnconfigure(1, weight=1)

        dot_wrap = ctk.CTkFrame(status, fg_color=SURFACE_MUTED, corner_radius=10)
        dot_wrap.grid(row=0, column=0, sticky="w")
        canvas_inner = Canvas(
            dot_wrap, width=10, height=10,
            bg=SURFACE_MUTED, highlightthickness=0, bd=0,
        )
        canvas_inner.pack(padx=10, pady=10)
        self.status_canvas = canvas_inner
        self._dot_id = canvas_inner.create_oval(1, 1, 9, 9, fill=TEXT_MUTED, outline="")

        ctk.CTkLabel(
            status, textvariable=self.var_status,
            font=("Segoe UI", 12, "bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=(12, 0))

    # ---------- Tarjeta de Actividad (log) ----------
    def _build_log_card(self, parent) -> None:
        card = self._card(parent)
        card.pack(fill=X, padx=PAD_X, pady=(8, 18))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill=X, padx=18, pady=(16, 18))
        inner.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(inner, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(0, weight=1)

        hdr_left = ctk.CTkFrame(hdr, fg_color="transparent")
        hdr_left.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            hdr_left, text="Actividad",
            font=FONT_H2, text_color=TEXT_PRIMARY, anchor="w",
        ).pack(anchor="w", fill=X)
        ctk.CTkLabel(
            hdr_left, text="Detalle técnico del proceso y advertencias.",
            font=FONT_HINT, text_color=TEXT_MUTED, anchor="w",
        ).pack(anchor="w", fill=X, pady=(2, 0))

        self.btn_clear_log = self._btn_secondary(hdr, "Limpiar", self._clear_log, width=96)
        self.btn_clear_log.grid(row=0, column=1, sticky="ne", padx=(12, 0))

        # Holder de altura fija para el textbox; el ancho viene de pack(fill=X).
        log_box_holder = ctk.CTkFrame(inner, fg_color="transparent", height=LOG_HEIGHT)
        log_box_holder.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        log_box_holder.grid_propagate(False)
        log_box_holder.pack_propagate(False)

        self.log_tb = ctk.CTkTextbox(
            log_box_holder,
            font=FONT_LOG,
            fg_color=SURFACE_MUTED,
            text_color=TEXT_SECONDARY,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_SUBTLE,
            wrap="word",
            scrollbar_button_color=TEXT_MUTED,
            scrollbar_button_hover_color=TEXT_SECONDARY,
        )
        self.log_tb.pack(fill=BOTH, expand=True)
        self.log_tb.configure(state="disabled")

        tb = getattr(self.log_tb, "_textbox", None)
        self._log_text_inner = tb
        if tb is not None:
            tb.tag_configure("error", foreground=ERROR)
            tb.tag_configure("hint", foreground=TEXT_MUTED)

        self._append_welcome_hint()

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------
    def _append_welcome_hint(self) -> None:
        welcome = (
            "Aún no hay ejecución. Completá la configuración arriba y pulsá «Procesar». "
            "Los mensajes del motor aparecerán aquí línea por línea.\n"
        )
        self.log_tb.configure(state="normal")
        self.log_tb.insert("1.0", welcome)
        if self._log_text_inner is not None:
            try:
                self._log_text_inner.tag_add("hint", "1.0", "1.end")
            except Exception:
                pass
        self.log_tb.configure(state="disabled")

    def _strip_welcome_hint(self) -> None:
        """Quita el texto de bienvenida si sigue solo ese mensaje.

        Debe llamarse con el textbox ya en estado «normal». No volver a
        deshabilitar aquí: si se deshabilita antes de `insert()`, Tk/CTk ignora
        las inserciones y el log queda vacío.
        """
        content = self.log_tb.get("1.0", END).strip()
        if "Aún no hay ejecución" in content and len(content) < 220:
            self.log_tb.delete("1.0", END)

    def _clear_log(self) -> None:
        self.log_tb.configure(state="normal")
        self.log_tb.delete("1.0", END)
        self.log_tb.configure(state="disabled")
        self._append_welcome_hint()

    def _append_log(self, msg: str) -> None:
        self.log_tb.configure(state="normal")
        self._strip_welcome_hint()
        start = self.log_tb.index(END)
        self.log_tb.insert(END, msg + "\n")
        if msg.upper().startswith("ERROR") and self._log_text_inner is not None:
            try:
                line_end = self.log_tb.index(f"{start} lineend")
                self._log_text_inner.tag_add("error", start, line_end)
            except Exception:
                pass
        self.log_tb.configure(state="disabled")
        self.log_tb.see("end")

    # ------------------------------------------------------------------
    # Estado / progreso
    # ------------------------------------------------------------------
    def _set_controls_busy(self, busy: bool) -> None:
        s = "disabled" if busy else "normal"
        self._pick_in_btn.configure(state=s)
        self._pick_out_btn.configure(state=s)
        self.ent_input.configure(state=s)
        self.ent_output.configure(state=s)
        self.ent_period.configure(state=s)
        self.btn_clear_log.configure(state=s)

    def _set_status_appearance(self, mode: str) -> None:
        self._status_mode = mode
        if self._dot_id is None:
            return
        colors = {
            "idle": TEXT_MUTED,
            "running": ACCENT,
            "paused": WARNING,
            "finished": SUCCESS,
            "error": ERROR,
            "aborted": WARNING,
        }
        self.status_canvas.itemconfigure(self._dot_id, fill=colors.get(mode, TEXT_MUTED))

    def _stop_pulse(self) -> None:
        if self._pulse_after is not None:
            try:
                self.root.after_cancel(self._pulse_after)
            except Exception:
                pass
            self._pulse_after = None

    def _pulse_tick(self) -> None:
        if not self._running or self._status_mode != "running":
            self._stop_pulse()
            return
        cur = self.status_canvas.itemcget(self._dot_id, "fill")
        nxt = ACCENT_PRESS if cur == ACCENT else ACCENT
        self.status_canvas.itemconfigure(self._dot_id, fill=nxt)
        self._pulse_after = self.root.after(720, self._pulse_tick)

    def _update_open_folder_state(self) -> None:
        if getattr(self, "btn_open", None) is None:
            return
        if self._running:
            self.btn_open.configure(state="disabled")
            return
        outp = self.var_output.get().strip()
        ok = False
        if outp:
            parent = Path(outp).expanduser().resolve().parent
            ok = parent.exists()
        if self._last_output_dir and self._last_output_dir.exists():
            ok = True
        self.btn_open.configure(state="normal" if ok else "disabled")

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def _pick_input(self) -> None:
        d = filedialog.askdirectory(title="Elegir carpeta de archivos de origen")
        if d:
            self.var_input.set(d)
            if not self.var_output.get():
                out_default = Path(d).parent / "CUENTAS_CORRIENTES_CONSOLIDADO.xlsx"
                self.var_output.set(str(out_default))

    def _pick_output(self) -> None:
        f = filedialog.asksaveasfilename(
            title="Guardar Excel consolidado como…",
            defaultextension=".xlsx",
            filetypes=[("Libro Excel", "*.xlsx"), ("Todos los archivos", "*.*")],
            initialfile="CUENTAS_CORRIENTES_CONSOLIDADO.xlsx",
        )
        if f:
            self.var_output.set(f)

    def _open_output(self) -> None:
        folder: Path | None = None
        if self._last_output_dir and self._last_output_dir.exists():
            folder = self._last_output_dir
        else:
            outp = self.var_output.get().strip()
            if outp:
                folder = Path(outp).expanduser().resolve().parent
        if folder is None or not folder.exists():
            messagebox.showinfo(
                "Carpeta de salida",
                "Elegí un archivo de salida válido o ejecutá el proceso para generar la carpeta.",
            )
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo abrir la carpeta: {exc}")

    def _run(self) -> None:
        if self._running:
            return
        input_dir = self.var_input.get().strip()
        output_file = self.var_output.get().strip()
        period = self.var_period.get().strip()

        if not input_dir or not Path(input_dir).is_dir():
            messagebox.showerror("Revisá los datos", "La carpeta de origen no existe o está vacía el campo.")
            return
        if not output_file:
            messagebox.showerror("Revisá los datos", "Indicá la ruta del archivo Excel de salida.")
            return
        if not PERIOD_RE.match(period):
            messagebox.showerror("Revisá los datos", "El período debe tener formato AAAA-MM (ej. 2026-05).")
            return

        self._running = True
        self._stop_pulse()
        self.btn_run.configure(state="disabled")
        self.btn_open.configure(state="disabled")
        self._set_controls_busy(True)
        self.log_tb.configure(state="normal")
        self.log_tb.delete("1.0", END)
        self.log_tb.configure(state="disabled")
        self.progress.set(0)
        self.var_progress_label.set("0%")
        self.var_status.set("Procesando…")
        self._set_status_appearance("running")
        self._pulse_tick()

        params = RunParams(input_dir=input_dir, output_file=output_file, period=period)
        threading.Thread(target=self._run_thread, args=(params,), daemon=True).start()

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
        self._stop_pulse()
        self.btn_run.configure(state="normal")
        self._set_controls_busy(False)
        self._update_open_folder_state()
        self.progress.set(1.0)
        self.var_progress_label.set("100%")
        total = self._last_summary.total_rows_generated if self._last_summary else 0
        self.var_status.set(f"Listo · {total} filas generadas")
        self._set_status_appearance("finished")

    def _on_done_error(self, exc: Exception) -> None:
        self._running = False
        self._stop_pulse()
        self.btn_run.configure(state="normal")
        self._set_controls_busy(False)
        self._update_open_folder_state()
        self.var_progress_label.set("")
        self.var_status.set(f"Error: {exc}")
        self._set_status_appearance("error")
        messagebox.showerror("Error en el proceso", str(exc))

    def _on_progress(self, current: int, total: int, label: str) -> None:
        def update():
            t = max(1, total)
            frac = min(1.0, current / t)
            self.progress.set(frac)
            pct = int(round(100 * frac))
            self.var_progress_label.set(f"{pct}%")
            self.var_status.set(f"[{current}/{total}] {label}")
            self._set_status_appearance("running")

        self.root.after(0, update)

    def _enqueue_log(self, msg: str) -> None:
        self._log_queue.put(msg)

    def _poll_log_queue(self) -> None:
        try:
            while True:
                msg = self._log_queue.get_nowait()
                self._append_log(msg)
        except queue.Empty:
            pass
        self.root.after(120, self._poll_log_queue)


def launch() -> None:
    ctk.set_appearance_mode("dark")
    root = ctk.CTk(fg_color=APP_BG)
    ConsolidatorApp(root)
    root.mainloop()
