"""GUI Coberser — layout de dos paneles: configuración (izquierda) y
resultados/actividad (derecha).

Reglas estrictas para evitar los bugs históricos de layout:
- Todo contenido scrolleable vive en un `CTkScrollableFrame`; sus hijos
  directos usan SIEMPRE `pack(fill=X)` y nunca reciben `width=` en píxeles
  (el frame ya sincroniza el ancho interno con su viewport).
- Dentro de cada bloque se usa `grid` con `columnconfigure(weight=1)` para
  que los inputs se estiren y los botones queden fijos.
- `wraplength` siempre estático (dimensionado para el ancho mínimo); nunca
  dinámico (eso producía un loop de `<Configure>` y "No responde").
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
from .utils.files import detect_parser, list_input_files
from .utils.fx import FX_COMPANIES, read_fx_config, write_fx_config


PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")

# ------------------------------------------------------------------
# Paleta y tipografías
# ------------------------------------------------------------------
APP_BG = "#0b0e14"
SIDEBAR_BG = "#11141d"
SURFACE = "#161a26"
SURFACE_MUTED = "#10131b"
INPUT_BG = "#1b202d"
INPUT_FOCUS = "#222838"
BORDER_SUBTLE = "#262d3d"
BORDER_STRONG = "#3a4257"
ACCENT = "#3b82f6"
ACCENT_HOVER = "#2563eb"
ACCENT_PRESS = "#1d4ed8"
ACCENT_SOFT = "#162540"
SUCCESS = "#22c55e"
SUCCESS_SOFT = "#10241a"
WARNING = "#f59e0b"
WARNING_SOFT = "#2a2110"
ERROR = "#ef4444"
ERROR_SOFT = "#2a1414"
TEXT_PRIMARY = "#e8eaed"
TEXT_SECONDARY = "#94a3b8"
TEXT_MUTED = "#64748b"

FONT_DISPLAY = ("Segoe UI Semibold", 17)
FONT_H2 = ("Segoe UI Semibold", 13)
FONT_KPI = ("Segoe UI Semibold", 24)
FONT_BODY = ("Segoe UI", 12)
FONT_BODY_SM = ("Segoe UI", 11)
FONT_LABEL = ("Segoe UI", 11)
FONT_OVERLINE = ("Segoe UI Semibold", 10)
FONT_BTN = ("Segoe UI", 13, "bold")
FONT_BTN_SECONDARY = ("Segoe UI", 12)
FONT_LOG = ("Consolas", 11)
FONT_HINT = ("Segoe UI", 10)
FONT_MONO_SM = ("Consolas", 12)

SIDEBAR_W = 372       # ancho fijo del panel izquierdo
PAD = 18              # padding genérico
WRAP_SIDE = 300       # wraplength estático para textos del sidebar
WRAP_MAIN = 470       # wraplength estático para textos del panel derecho


class ConsolidatorApp:
    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        root.title("Coberser · Consolidador de cuentas corrientes")
        root.geometry("1120x720")
        root.minsize(960, 620)
        root.configure(fg_color=APP_BG)

        self._log_queue: queue.Queue[str] = queue.Queue()
        self._running = False
        self._last_output_dir: Path | None = None
        self._last_summary: RunSummary | None = None
        self._pulse_after: str | None = None
        self._status_mode = "idle"
        self._dot_id: int | None = None

        # Período por defecto: el mes ANTERIOR (la consolidación de un mes se
        # hace los primeros días del mes siguiente).
        today = date.today()
        prev_y, prev_m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        default_period = f"{prev_y:04d}-{prev_m:02d}"

        self.var_input = StringVar()
        self.var_output = StringVar()
        self.var_period = StringVar(value=default_period)
        self.var_status = StringVar(value="Listo para procesar")
        self.var_progress_label = StringVar(value="")
        self.var_input_stats = StringVar(value="")

        # Tipos de cambio USD: una StringVar por compañía, pre-llenadas con
        # el último valor persistido en config/fx.json.
        fx_persisted = read_fx_config()
        self.var_fx: dict[str, StringVar] = {}
        for display, key in FX_COMPANIES:
            v = fx_persisted.get(key)
            self.var_fx[key] = StringVar(value=("" if v is None else f"{v:g}"))

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
    def _entry(self, parent, variable: StringVar | None = None) -> ctk.CTkEntry:
        e = ctk.CTkEntry(
            parent,
            textvariable=variable,
            height=38,
            font=FONT_BODY,
            fg_color=INPUT_BG,
            text_color=TEXT_PRIMARY,
            placeholder_text_color=TEXT_MUTED,
            border_width=1,
            border_color=BORDER_SUBTLE,
            corner_radius=9,
        )
        e.bind("<FocusIn>", lambda _e: e.configure(fg_color=INPUT_FOCUS, border_color=ACCENT))
        e.bind("<FocusOut>", lambda _e: e.configure(fg_color=INPUT_BG, border_color=BORDER_SUBTLE))
        return e

    def _btn_secondary(self, parent, text: str, command, *, width: int = 96) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            height=38,
            font=FONT_BTN_SECONDARY,
            fg_color="transparent",
            hover_color=SURFACE_MUTED,
            text_color=TEXT_SECONDARY,
            border_width=1,
            border_color=BORDER_STRONG,
            corner_radius=9,
        )

    def _overline(self, parent, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            parent, text=text, font=FONT_OVERLINE, text_color=TEXT_MUTED, anchor="w"
        )

    # ------------------------------------------------------------------
    # Construcción del layout
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=0)
        self.root.grid_columnconfigure(1, weight=1)

        self._build_sidebar()
        self._build_main()

    # ---------- Panel izquierdo: configuración ----------
    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self.root, fg_color=SIDEBAR_BG, corner_radius=0, width=SIDEBAR_W)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.pack_propagate(False)

        # Footer fijo (botón Procesar) — se packea primero para reservar lugar.
        footer = ctk.CTkFrame(side, fg_color=SIDEBAR_BG, corner_radius=0)
        footer.pack(side="bottom", fill=X)

        sep = ctk.CTkFrame(footer, fg_color=BORDER_SUBTLE, height=1, corner_radius=0)
        sep.pack(fill=X)

        footer_in = ctk.CTkFrame(footer, fg_color="transparent")
        footer_in.pack(fill=X, padx=PAD, pady=(14, 12))

        self.btn_run = ctk.CTkButton(
            footer_in,
            text="Procesar",
            command=self._run,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#ffffff",
            height=44,
            font=FONT_BTN,
            corner_radius=10,
        )
        self.btn_run.pack(fill=X)

        ctk.CTkLabel(
            footer_in,
            text="Atajo: Ctrl+Enter o F5",
            font=FONT_HINT,
            text_color=TEXT_MUTED,
            anchor="center",
        ).pack(fill=X, pady=(8, 0))

        # Contenido scrolleable del sidebar.
        scroll = ctk.CTkScrollableFrame(
            side,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
            scrollbar_fg_color=SIDEBAR_BG,
            scrollbar_button_color=BORDER_STRONG,
            scrollbar_button_hover_color=TEXT_MUTED,
        )
        scroll.pack(fill=BOTH, expand=True)

        # ---- Marca ----
        brand = ctk.CTkFrame(scroll, fg_color="transparent")
        brand.pack(fill=X, padx=PAD, pady=(18, 4))
        brand.grid_columnconfigure(1, weight=1)

        logo = ctk.CTkFrame(brand, fg_color=ACCENT, corner_radius=8, width=34, height=34)
        logo.grid(row=0, column=0, rowspan=2, sticky="w")
        logo.grid_propagate(False)
        ctk.CTkLabel(
            logo, text="C", font=("Segoe UI Black", 16), text_color="#ffffff"
        ).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            brand, text="Coberser", font=FONT_DISPLAY, text_color=TEXT_PRIMARY, anchor="w"
        ).grid(row=0, column=1, sticky="ew", padx=(12, 0))
        ctk.CTkLabel(
            brand,
            text="Consolidador de cuentas corrientes",
            font=FONT_HINT,
            text_color=TEXT_MUTED,
            anchor="w",
        ).grid(row=1, column=1, sticky="ew", padx=(12, 0))

        # ---- 1 · Carpeta de origen ----
        sec1 = ctk.CTkFrame(scroll, fg_color="transparent")
        sec1.pack(fill=X, padx=PAD, pady=(20, 0))
        sec1.grid_columnconfigure(0, weight=1)

        self._overline(sec1, "1 · CARPETA DE ORIGEN").grid(row=0, column=0, columnspan=2, sticky="ew")

        self.ent_input = self._entry(sec1, self.var_input)
        self.ent_input.grid(row=1, column=0, sticky="ew", pady=(8, 0), padx=(0, 8))
        self.ent_input.bind("<FocusOut>", lambda _e: self._refresh_input_stats(), add="+")
        self._pick_in_btn = self._btn_secondary(sec1, "Elegir…", self._pick_input)
        self._pick_in_btn.grid(row=1, column=1, sticky="e", pady=(8, 0))

        self.lbl_input_stats = ctk.CTkLabel(
            sec1,
            textvariable=self.var_input_stats,
            font=FONT_HINT,
            text_color=TEXT_MUTED,
            anchor="w",
            justify="left",
            wraplength=WRAP_SIDE,
        )
        self.lbl_input_stats.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.var_input_stats.set("Carpeta con los archivos de cada aseguradora (Excel/PDF).")

        # ---- 2 · Excel de salida ----
        sec2 = ctk.CTkFrame(scroll, fg_color="transparent")
        sec2.pack(fill=X, padx=PAD, pady=(18, 0))
        sec2.grid_columnconfigure(0, weight=1)

        self._overline(sec2, "2 · EXCEL DE SALIDA").grid(row=0, column=0, columnspan=2, sticky="ew")

        self.ent_output = self._entry(sec2, self.var_output)
        self.ent_output.grid(row=1, column=0, sticky="ew", pady=(8, 0), padx=(0, 8))
        self._pick_out_btn = self._btn_secondary(sec2, "Guardar…", self._pick_output)
        self._pick_out_btn.grid(row=1, column=1, sticky="e", pady=(8, 0))

        ctk.CTkLabel(
            sec2,
            text="El log y las filas rechazadas se guardan en la misma carpeta.",
            font=FONT_HINT,
            text_color=TEXT_MUTED,
            anchor="w",
            justify="left",
            wraplength=WRAP_SIDE,
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        # ---- 3 · Período ----
        sec3 = ctk.CTkFrame(scroll, fg_color="transparent")
        sec3.pack(fill=X, padx=PAD, pady=(18, 0))
        sec3.grid_columnconfigure(1, weight=1)

        self._overline(sec3, "3 · PERÍODO CONTABLE").grid(row=0, column=0, columnspan=2, sticky="ew")

        self.ent_period = self._entry(sec3, self.var_period)
        self.ent_period.configure(width=110, justify="center", font=FONT_MONO_SM)
        self.ent_period.grid(row=1, column=0, sticky="w", pady=(8, 0))
        ctk.CTkLabel(
            sec3,
            text="Formato AAAA-MM. Es la FECHA\nque llevará cada fila de la base.",
            font=FONT_HINT,
            text_color=TEXT_MUTED,
            anchor="w",
            justify="left",
        ).grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(8, 0))

        # ---- 4 · Tipos de cambio USD ----
        sec4 = ctk.CTkFrame(scroll, fg_color="transparent")
        sec4.pack(fill=X, padx=PAD, pady=(18, 16))
        sec4.grid_columnconfigure(0, weight=1)
        sec4.grid_columnconfigure(1, weight=0)

        self._overline(sec4, "4 · DÓLAR POR COMPAÑÍA (OPCIONAL)").grid(
            row=0, column=0, columnspan=2, sticky="ew"
        )
        ctk.CTkLabel(
            sec4,
            text=(
                "Cada aseguradora liquida con SU tipo de cambio. "
                "Si queda vacío, sus filas en dólares se rechazan."
            ),
            font=FONT_HINT,
            text_color=TEXT_MUTED,
            anchor="w",
            justify="left",
            wraplength=WRAP_SIDE,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 4))

        self._fx_entries: dict[str, ctk.CTkEntry] = {}
        for i, (display, key) in enumerate(FX_COMPANIES, start=2):
            ctk.CTkLabel(
                sec4, text=display, font=FONT_LABEL, text_color=TEXT_SECONDARY, anchor="w"
            ).grid(row=i, column=0, sticky="w", pady=(8, 0))
            ent = self._entry(sec4, self.var_fx[key])
            ent.configure(width=110, justify="right", font=FONT_MONO_SM, placeholder_text="1420")
            ent.grid(row=i, column=1, sticky="e", pady=(8, 0))
            self._fx_entries[key] = ent

    # ---------- Panel derecho: estado + pestañas ----------
    def _build_main(self) -> None:
        main = ctk.CTkFrame(self.root, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)

        # ---- Barra de estado ----
        status_card = ctk.CTkFrame(
            main, fg_color=SURFACE, corner_radius=12, border_width=1, border_color=BORDER_SUBTLE
        )
        status_card.grid(row=0, column=0, sticky="ew", padx=PAD, pady=(PAD, 10))
        status_card.grid_columnconfigure(1, weight=1)

        dot_wrap = ctk.CTkFrame(status_card, fg_color="transparent")
        dot_wrap.grid(row=0, column=0, sticky="w", padx=(16, 0), pady=14)
        self.status_canvas = Canvas(
            dot_wrap, width=12, height=12, bg=SURFACE, highlightthickness=0, bd=0
        )
        self.status_canvas.pack()
        self._dot_id = self.status_canvas.create_oval(2, 2, 10, 10, fill=TEXT_MUTED, outline="")

        status_text = ctk.CTkFrame(status_card, fg_color="transparent")
        status_text.grid(row=0, column=1, sticky="ew", padx=(10, 12), pady=10)
        status_text.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            status_text,
            textvariable=self.var_status,
            font=("Segoe UI Semibold", 12),
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")

        prog_row = ctk.CTkFrame(status_text, fg_color="transparent")
        prog_row.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        prog_row.grid_columnconfigure(0, weight=1)
        self.progress = ctk.CTkProgressBar(
            prog_row,
            mode="determinate",
            progress_color=ACCENT,
            fg_color=INPUT_BG,
            corner_radius=4,
            height=6,
        )
        self.progress.grid(row=0, column=0, sticky="ew")
        self.progress.set(0)
        ctk.CTkLabel(
            prog_row,
            textvariable=self.var_progress_label,
            font=FONT_HINT,
            text_color=TEXT_MUTED,
            anchor="e",
            width=44,
        ).grid(row=0, column=1, sticky="e", padx=(10, 0))

        self.btn_open = self._btn_secondary(
            status_card, "Abrir carpeta de salida", self._open_output, width=178
        )
        self.btn_open.grid(row=0, column=2, sticky="e", padx=(0, 14), pady=10)

        # ---- Pestañas ----
        self.tabs = ctk.CTkTabview(
            main,
            fg_color=SURFACE,
            corner_radius=12,
            border_width=1,
            border_color=BORDER_SUBTLE,
            segmented_button_fg_color=SURFACE_MUTED,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_HOVER,
            segmented_button_unselected_color=SURFACE_MUTED,
            segmented_button_unselected_hover_color=INPUT_FOCUS,
            text_color=TEXT_PRIMARY,
        )
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=PAD, pady=(0, PAD))
        self.tab_summary = self.tabs.add("Resumen")
        self.tab_log = self.tabs.add("Actividad")

        self._build_summary_tab()
        self._build_log_tab()
        self.tabs.set("Resumen")

    # ---------- Pestaña Resumen ----------
    def _build_summary_tab(self) -> None:
        self.tab_summary.grid_rowconfigure(0, weight=1)
        self.tab_summary.grid_columnconfigure(0, weight=1)

        self.summary_scroll = ctk.CTkScrollableFrame(
            self.tab_summary,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
            scrollbar_fg_color=SURFACE,
            scrollbar_button_color=BORDER_STRONG,
            scrollbar_button_hover_color=TEXT_MUTED,
        )
        self.summary_scroll.grid(row=0, column=0, sticky="nsew")
        self._render_summary_empty()

    def _clear_summary(self) -> None:
        for w in self.summary_scroll.winfo_children():
            w.destroy()

    def _render_summary_empty(self) -> None:
        self._clear_summary()
        holder = ctk.CTkFrame(self.summary_scroll, fg_color="transparent")
        holder.pack(fill=X, pady=(90, 0))
        ctk.CTkLabel(
            holder, text="—", font=("Segoe UI", 34), text_color=BORDER_STRONG
        ).pack()
        ctk.CTkLabel(
            holder,
            text="Todavía no hay resultados",
            font=FONT_H2,
            text_color=TEXT_SECONDARY,
        ).pack(pady=(6, 2))
        ctk.CTkLabel(
            holder,
            text=(
                "Completá la configuración de la izquierda y pulsá «Procesar». "
                "Acá vas a ver las filas generadas por compañía y los archivos omitidos."
            ),
            font=FONT_BODY_SM,
            text_color=TEXT_MUTED,
            justify="center",
            wraplength=WRAP_MAIN,
        ).pack()

    def _kpi(self, parent, column: int, value: str, caption: str, color: str, soft: str) -> None:
        chip = ctk.CTkFrame(
            parent, fg_color=soft, corner_radius=10, border_width=1, border_color=BORDER_SUBTLE
        )
        chip.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 10, 0))
        ctk.CTkLabel(chip, text=value, font=FONT_KPI, text_color=color, anchor="w").pack(
            anchor="w", padx=14, pady=(10, 0)
        )
        ctk.CTkLabel(chip, text=caption, font=FONT_HINT, text_color=TEXT_SECONDARY, anchor="w").pack(
            anchor="w", padx=14, pady=(0, 10)
        )

    def _render_summary(self, summary: RunSummary) -> None:
        self._clear_summary()

        body = ctk.CTkFrame(self.summary_scroll, fg_color="transparent")
        body.pack(fill=X, padx=14, pady=12)
        body.grid_columnconfigure(0, weight=1)

        # ---- KPIs ----
        kpis = ctk.CTkFrame(body, fg_color="transparent")
        kpis.grid(row=0, column=0, sticky="ew")
        for c in range(4):
            kpis.grid_columnconfigure(c, weight=1, uniform="kpi")

        n_skip = len(summary.files_skipped)
        n_rej = summary.rejected_rows_count
        self._kpi(kpis, 0, f"{summary.total_rows_generated:,}".replace(",", "."),
                  "Filas generadas", TEXT_PRIMARY, ACCENT_SOFT)
        self._kpi(kpis, 1, str(len(summary.files_processed)),
                  "Archivos procesados", SUCCESS, SUCCESS_SOFT)
        self._kpi(kpis, 2, str(n_skip), "Archivos omitidos",
                  WARNING if n_skip else TEXT_MUTED,
                  WARNING_SOFT if n_skip else SURFACE_MUTED)
        self._kpi(kpis, 3, str(n_rej), "Filas rechazadas",
                  ERROR if n_rej else TEXT_MUTED,
                  ERROR_SOFT if n_rej else SURFACE_MUTED)

        # ---- Archivos omitidos (lo más accionable: va primero) ----
        if summary.files_skipped:
            skipped_card = ctk.CTkFrame(
                body, fg_color=SURFACE_MUTED, corner_radius=10,
                border_width=1, border_color=BORDER_SUBTLE,
            )
            skipped_card.grid(row=1, column=0, sticky="ew", pady=(14, 0))
            inner = ctk.CTkFrame(skipped_card, fg_color="transparent")
            inner.pack(fill=X, padx=14, pady=12)
            ctk.CTkLabel(
                inner,
                text="⚠  Archivos omitidos — revisá si falta alguna aseguradora",
                font=FONT_H2,
                text_color=WARNING,
                anchor="w",
            ).pack(anchor="w", fill=X)
            for item in summary.files_skipped:
                ctk.CTkLabel(
                    inner,
                    text=f"•  {item.get('file', '?')}  —  {item.get('reason', '')}",
                    font=FONT_BODY_SM,
                    text_color=TEXT_SECONDARY,
                    anchor="w",
                    justify="left",
                    wraplength=WRAP_MAIN,
                ).pack(anchor="w", fill=X, pady=(6, 0))

        # ---- Filas por compañía ----
        comp_card = ctk.CTkFrame(
            body, fg_color=SURFACE_MUTED, corner_radius=10,
            border_width=1, border_color=BORDER_SUBTLE,
        )
        comp_card.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        comp_in = ctk.CTkFrame(comp_card, fg_color="transparent")
        comp_in.pack(fill=X, padx=14, pady=12)
        comp_in.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            comp_in, text="Filas por compañía", font=FONT_H2, text_color=TEXT_PRIMARY, anchor="w"
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            comp_in, text=f"{len(summary.rows_by_company)} compañías",
            font=FONT_HINT, text_color=TEXT_MUTED, anchor="e",
        ).grid(row=0, column=1, sticky="e")

        for i, (comp, n) in enumerate(summary.rows_by_company.items(), start=1):
            ctk.CTkFrame(comp_in, fg_color=BORDER_SUBTLE, height=1, corner_radius=0).grid(
                row=2 * i - 1, column=0, columnspan=2, sticky="ew", pady=6
            )
            ctk.CTkLabel(
                comp_in, text=comp, font=FONT_BODY_SM, text_color=TEXT_SECONDARY, anchor="w"
            ).grid(row=2 * i, column=0, sticky="ew")
            ctk.CTkLabel(
                comp_in, text=f"{n:,}".replace(",", "."),
                font=FONT_MONO_SM, text_color=TEXT_PRIMARY, anchor="e",
            ).grid(row=2 * i, column=1, sticky="e")

    # ---------- Pestaña Actividad ----------
    def _build_log_tab(self) -> None:
        self.tab_log.grid_rowconfigure(1, weight=1)
        self.tab_log.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(self.tab_log, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=4, pady=(2, 8))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            hdr,
            text="Detalle técnico del proceso, advertencias y filas rechazadas.",
            font=FONT_HINT,
            text_color=TEXT_MUTED,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        self.btn_clear_log = self._btn_secondary(hdr, "Limpiar", self._clear_log, width=88)
        self.btn_clear_log.grid(row=0, column=1, sticky="e")

        self.log_tb = ctk.CTkTextbox(
            self.tab_log,
            font=FONT_LOG,
            fg_color=SURFACE_MUTED,
            text_color=TEXT_SECONDARY,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_SUBTLE,
            wrap="word",
            scrollbar_button_color=BORDER_STRONG,
            scrollbar_button_hover_color=TEXT_MUTED,
        )
        self.log_tb.grid(row=1, column=0, sticky="nsew", padx=2, pady=(0, 2))
        self.log_tb.configure(state="disabled")

        tb = getattr(self.log_tb, "_textbox", None)
        self._log_text_inner = tb
        if tb is not None:
            tb.tag_configure("error", foreground=ERROR)
            tb.tag_configure("warn", foreground=WARNING)
            tb.tag_configure("hint", foreground=TEXT_MUTED)

        self._append_welcome_hint()

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------
    def _append_welcome_hint(self) -> None:
        welcome = (
            "Aún no hay ejecución. Los mensajes del motor aparecerán aquí línea por línea.\n"
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
        if self._log_text_inner is not None:
            tag = None
            up = msg.upper()
            if up.startswith("ERROR") or "[ERROR]" in up:
                tag = "error"
            elif "[WARNING]" in up or up.startswith("OMITIDO"):
                tag = "warn"
            if tag:
                try:
                    line_end = self.log_tb.index(f"{start} lineend")
                    self._log_text_inner.tag_add(tag, start, line_end)
                except Exception:
                    pass
        self.log_tb.configure(state="disabled")
        self.log_tb.see("end")

    # ------------------------------------------------------------------
    # Preview de la carpeta de origen
    # ------------------------------------------------------------------
    def _refresh_input_stats(self) -> None:
        d = self.var_input.get().strip()
        if not d:
            self.var_input_stats.set("Carpeta con los archivos de cada aseguradora (Excel/PDF).")
            self.lbl_input_stats.configure(text_color=TEXT_MUTED)
            return
        p = Path(d)
        if not p.is_dir():
            self.var_input_stats.set("La carpeta no existe.")
            self.lbl_input_stats.configure(text_color=ERROR)
            return
        try:
            files = list_input_files(d)
        except Exception:
            files = []
        if not files:
            self.var_input_stats.set("No se encontraron archivos compatibles (.xlsx/.xls/.pdf).")
            self.lbl_input_stats.configure(text_color=WARNING)
            return
        unknown = [f.name for f in files if detect_parser(f.name) is None]
        if unknown:
            self.var_input_stats.set(
                f"{len(files)} archivos · {len(unknown)} sin regla de importación "
                f"(se omitirán): {', '.join(unknown[:3])}{'…' if len(unknown) > 3 else ''}"
            )
            self.lbl_input_stats.configure(text_color=WARNING)
            # Loguear el detalle una sola vez por carpeta/lista.
            key = (d, tuple(unknown))
            if key != getattr(self, "_last_unknown_logged", None):
                self._last_unknown_logged = key
                for name in unknown:
                    self._enqueue_log(f"OMITIDO (sin regla de importación): {name}")
        else:
            self.var_input_stats.set(
                f"{len(files)} archivos detectados, todos con regla de importación."
            )
            self.lbl_input_stats.configure(text_color=TEXT_SECONDARY)

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
        for ent in getattr(self, "_fx_entries", {}).values():
            ent.configure(state=s)

    def _set_status_appearance(self, mode: str) -> None:
        self._status_mode = mode
        if self._dot_id is None:
            return
        colors = {
            "idle": TEXT_MUTED,
            "running": ACCENT,
            "finished": SUCCESS,
            "error": ERROR,
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
            self._refresh_input_stats()

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
            messagebox.showerror("Revisá los datos", "La carpeta de origen no existe o el campo está vacío.")
            return
        if not output_file:
            messagebox.showerror("Revisá los datos", "Indicá la ruta del archivo Excel de salida.")
            return
        if not PERIOD_RE.match(period):
            messagebox.showerror("Revisá los datos", "El período debe tener formato AAAA-MM (ej. 2026-05).")
            return

        # Validar y persistir tipos de cambio USD (opcionales).
        fx_values: dict[str, float] = {}
        for display, key in FX_COMPANIES:
            raw = self.var_fx[key].get().strip().replace(",", ".")
            if not raw:
                continue
            try:
                v = float(raw)
            except ValueError:
                messagebox.showerror(
                    "Revisá los datos",
                    f"El tipo de cambio de {display} no es un número válido: «{raw}».",
                )
                return
            if v <= 0:
                messagebox.showerror(
                    "Revisá los datos",
                    f"El tipo de cambio de {display} debe ser mayor a 0.",
                )
                return
            fx_values[key] = v
        try:
            write_fx_config(fx_values)
        except Exception as exc:
            messagebox.showerror(
                "Tipos de cambio",
                f"No se pudo guardar config/fx.json: {exc}",
            )
            return

        self._running = True
        self._stop_pulse()
        self.btn_run.configure(state="disabled", text="Procesando…")
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
        self.tabs.set("Actividad")

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
            self.root.after(0, self._on_done_ok)
        except Exception as exc:
            self._enqueue_log(f"ERROR: {exc}")
            self.root.after(0, lambda: self._on_done_error(exc))

    def _on_done_ok(self) -> None:
        self._running = False
        self._stop_pulse()
        self.btn_run.configure(state="normal", text="Procesar")
        self._set_controls_busy(False)
        self._update_open_folder_state()
        self.progress.set(1.0)
        self.var_progress_label.set("100%")
        summary = self._last_summary
        total = summary.total_rows_generated if summary else 0
        n_skip = len(summary.files_skipped) if summary else 0
        extra = f" · {n_skip} archivos omitidos" if n_skip else ""
        self.var_status.set(f"Listo · {total} filas generadas{extra}")
        self._set_status_appearance("finished")
        if summary is not None:
            self._render_summary(summary)
            self.tabs.set("Resumen")

    def _on_done_error(self, exc: Exception) -> None:
        self._running = False
        self._stop_pulse()
        self.btn_run.configure(state="normal", text="Procesar")
        self._set_controls_busy(False)
        self._update_open_folder_state()
        self.var_progress_label.set("")
        self.var_status.set(f"Error: {exc}")
        self._set_status_appearance("error")
        self.tabs.set("Actividad")
        messagebox.showerror("Error en el proceso", str(exc))

    def _on_progress(self, current: int, total: int, label: str) -> None:
        if len(label) > 58:
            label = label[:55] + "…"

        def update():
            t = max(1, total)
            frac = min(1.0, current / t)
            self.progress.set(frac)
            pct = int(round(100 * frac))
            self.var_progress_label.set(f"{pct}%")
            self.var_status.set(f"[{current}/{total}]  {label}")
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
