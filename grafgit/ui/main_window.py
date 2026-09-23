"""Main application window for GrafGit — Unified Multi-Element Studio with Real-time Live Sliders."""

import os
import sys
import threading
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk
from typing import Optional

# Enable crisp DPI scaling on Windows before any Tk calls
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

from grafgit.core.calendar import ROW_NAMES, coords_to_date, get_year_calendar_info
from grafgit.core.export_png import export_project_to_image
from grafgit.core.font7x5 import render_text
from grafgit.core.git_engine import GitEngine
from grafgit.core.image_proc import convert_image_to_grid, get_image_info
from grafgit.core.project import Project
from grafgit.ui.canvas_grid import CanvasGrid
from grafgit.ui.theme import (
    ACCENT_BLUE,
    ACCENT_GREEN,
    BG_CARD,
    BG_INPUT,
    BG_PANEL,
    BG_ROOT,
    BORDER_COLOR,
    BORDER_SUBTLE,
    BTN_DANGER_BG,
    BTN_DANGER_FG,
    BTN_DANGER_HOVER,
    BTN_PRIMARY_BG,
    BTN_PRIMARY_FG,
    BTN_PRIMARY_HOVER,
    BTN_SECONDARY_BG,
    BTN_SECONDARY_FG,
    BTN_SECONDARY_HOVER,
    DANGER_RED,
    FONT_BOLD,
    FONT_HEADING,
    FONT_MONO,
    FONT_MONO_SMALL,
    FONT_REGULAR,
    FONT_SMALL,
    FONT_TITLE,
    LEVEL_BORDERS,
    LEVEL_COLORS,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_WHITE,
)


class MainWindow(tk.Tk):
    def __init__(self, target_dir: Optional[str] = None):
        super().__init__()
        self.title("GrafGit — GitHub Contribution Studio")
        self.geometry("1240x880")
        self.minsize(1020, 700)
        self.configure(bg=BG_ROOT)
        self.current_zoom = 15

        # Set default working repository
        self.target_dir = os.path.abspath(target_dir or os.getcwd())
        self.git_engine = GitEngine(self.target_dir)

        # Detect Git config author
        default_name, default_email = self.git_engine.get_author_config()
        self.author_name_var = tk.StringVar(value=default_name or "GrafGit Artist")
        self.author_email_var = tk.StringVar(value=default_email or "")

        # Current project state
        self.project = Project(initial_year=2024)
        self.current_filepath: Optional[str] = None

        # Inspector state
        self.selected_element_id: Optional[str] = None
        self._suppress_inspector_updates = False

        self._init_ttk_styles()
        self._build_ui()
        self._bind_global_shortcuts()
        self._refresh_stats()

        # Log initial status
        self.log(f"GrafGit initialized. Target directory: {self.target_dir}")
        if self.git_engine.is_git_repo():
            self.log(f"Git repository detected. Current branch: {self.git_engine.get_current_branch()}")
            if default_email:
                self.log(f"Git author detected: {default_name} <{default_email}>")
            else:
                self.log("WARNING: git user.email is not set! Please enter your GitHub email.")
        else:
            self.log("Notice: Target directory is not yet a Git repository. It will be initialized on commit.")

    def _bind_global_shortcuts(self):
        """Global undo / redo shortcuts."""
        self.bind("<Control-z>", lambda e: self._on_undo())
        self.bind("<Control-Z>", lambda e: self._on_undo())
        self.bind("<Control-y>", lambda e: self._on_redo())
        self.bind("<Control-Y>", lambda e: self._on_redo())
        self.bind("<Control-Shift-Z>", lambda e: self._on_redo())
        self.bind("<Control-Shift-z>", lambda e: self._on_redo())

    def _init_ttk_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")

        self.style.configure(".", background=BG_PANEL, foreground=TEXT_PRIMARY, font=FONT_REGULAR)
        self.style.configure("TNotebook", background=BG_PANEL, borderwidth=0)
        self.style.configure(
            "TNotebook.Tab",
            background=BG_CARD,
            foreground=TEXT_MUTED,
            padding=[14, 6],
            font=FONT_BOLD,
            borderwidth=0
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", BG_PANEL)],
            foreground=[("selected", TEXT_WHITE)],
        )

        self.style.configure(
            "TCombobox",
            fieldbackground=BG_INPUT,
            background=BG_CARD,
            foreground=TEXT_PRIMARY,
            bordercolor=BORDER_COLOR,
            arrowcolor=TEXT_PRIMARY
        )

    def _build_ui(self):
        # 1. Top Navbar
        self.top_nav = tk.Frame(self, bg=BG_PANEL, height=45, bd=1, highlightbackground=BORDER_COLOR, highlightthickness=1)
        self.top_nav.pack(fill="x", side="top")

        brand_lbl = tk.Label(
            self.top_nav,
            text="GrafGit",
            bg=BG_PANEL,
            fg=ACCENT_GREEN,
            font=("Segoe UI", 12, "bold")
        )
        brand_lbl.pack(side="left", padx=(14, 8), pady=8)

        ver_lbl = tk.Label(self.top_nav, text="v1.3", bg=BG_PANEL, fg=TEXT_MUTED, font=FONT_SMALL)
        ver_lbl.pack(side="left", pady=8)

        # File actions
        btn_frame = tk.Frame(self.top_nav, bg=BG_PANEL)
        btn_frame.pack(side="left", padx=16)

        self._create_header_btn(btn_frame, "Новий", self._on_new_file)
        self._create_header_btn(btn_frame, "Відкрити...", self._on_open_file)
        self._create_header_btn(btn_frame, "Зберегти", self._on_save_file)
        self._create_header_btn(btn_frame, "Зберегти як...", self._on_save_as_file)

        # Undo / Redo
        self._create_header_btn(btn_frame, "Відмінити", self._on_undo)
        self._create_header_btn(btn_frame, "Повторити", self._on_redo)

        # Advanced tools
        self._create_header_btn(btn_frame, "Експорт PNG", self._on_export_png)
        self._create_header_btn(btn_frame, "Копіювати в рік...", self._on_copy_year_dialog)
        self._create_header_btn(btn_frame, "Рівні...", self._on_config_multipliers)

        top_clear_btn = tk.Button(
            btn_frame,
            text="Очистити рік",
            bg=BG_CARD,
            fg="#f85149",
            activebackground=BTN_DANGER_HOVER,
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
            font=FONT_BOLD,
            cursor="hand2",
            command=self._on_clear_year
        )
        top_clear_btn.pack(side="left", padx=4)

        # 2. Main Body Container
        self.body = tk.Frame(self, bg=BG_ROOT)
        self.body.pack(fill="both", expand=True, padx=14, pady=10)

        # Contribution Header
        self.contrib_header = tk.Frame(self.body, bg=BG_ROOT)
        self.contrib_header.pack(fill="x", pady=(0, 6))

        self.contrib_count_lbl = tk.Label(
            self.contrib_header,
            text="0 contributions in 2024",
            bg=BG_ROOT,
            fg=TEXT_WHITE,
            font=("Segoe UI", 13, "bold")
        )
        self.contrib_count_lbl.pack(side="left")

        # Year selector buttons
        self.year_pills_frame = tk.Frame(self.contrib_header, bg=BG_ROOT)
        self.year_pills_frame.pack(side="right")

        self.year_buttons: dict[int, tk.Button] = {}
        self._rebuild_year_pills()

        # Zoom controls (Cell Size Scaler)
        zoom_frame = tk.Frame(self.contrib_header, bg=BG_ROOT)
        zoom_frame.pack(side="right", padx=(0, 16))

        tk.Label(zoom_frame, text="Масштаб:", bg=BG_ROOT, fg=TEXT_MUTED, font=FONT_SMALL).pack(side="left", padx=(0, 3))

        zoom_out_btn = tk.Button(
            zoom_frame, text=" − ", bg=BG_CARD, fg=TEXT_PRIMARY,
            activebackground=BG_PANEL, activeforeground=TEXT_WHITE,
            relief="flat", bd=0, padx=5, pady=1, font=FONT_BOLD,
            cursor="hand2",
            command=self._on_zoom_out
        )
        zoom_out_btn.pack(side="left", padx=1)

        self.zoom_lbl = tk.Label(zoom_frame, text=f"{self.current_zoom}px", bg=BG_ROOT, fg=ACCENT_GREEN, font=FONT_BOLD, width=5)
        self.zoom_lbl.pack(side="left")

        zoom_in_btn = tk.Button(
            zoom_frame, text=" + ", bg=BG_CARD, fg=TEXT_PRIMARY,
            activebackground=BG_PANEL, activeforeground=TEXT_WHITE,
            relief="flat", bd=0, padx=5, pady=1, font=FONT_BOLD,
            cursor="hand2",
            command=self._on_zoom_in
        )
        zoom_in_btn.pack(side="left", padx=1)

        for sz, lbl in [(15, "15px"), (20, "20px")]:
            btn = tk.Button(
                zoom_frame, text=lbl, bg=BG_CARD, fg=TEXT_PRIMARY,
                activebackground=BG_PANEL, activeforeground=TEXT_WHITE,
                relief="flat", bd=0, padx=4, pady=1, font=FONT_SMALL,
                cursor="hand2",
                command=lambda s=sz: self._set_zoom(s)
            )
            btn.pack(side="left", padx=1)

        # 3. Canvas Card Container
        self.canvas_card = tk.Frame(
            self.body,
            bg=BG_PANEL,
            bd=1,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1
        )
        self.canvas_card.pack(fill="x", pady=(0, 6))
        self.canvas_card.bind("<Configure>", lambda e: self._check_canvas_scroll())

        canvas_viewport = tk.Frame(self.canvas_card, bg=BG_PANEL)
        canvas_viewport.pack(fill="x", padx=10, pady=(8, 2))

        self.grid_scroll_x = tk.Scrollbar(self.canvas_card, orient="horizontal")

        self.grid_widget = CanvasGrid(
            canvas_viewport,
            project=self.project,
            cell_size=self.current_zoom,
            on_change=self._on_canvas_modified,
            on_hover=self._on_canvas_hover,
            xscrollcommand=self.grid_scroll_x.set
        )
        self.grid_scroll_x.config(command=self.grid_widget.xview)
        self.grid_widget.pack(anchor="center")

        # Bottom of canvas card: hover status and Legend
        canvas_footer = tk.Frame(self.canvas_card, bg=BG_PANEL)
        canvas_footer.pack(fill="x", padx=14, pady=(2, 8))

        self.hover_lbl = tk.Label(
            canvas_footer,
            text="Наведіть курсор на клітинку для перегляду дати...",
            bg=BG_PANEL,
            fg=TEXT_MUTED,
            font=FONT_SMALL
        )
        self.hover_lbl.pack(side="left")

        legend_frame = tk.Frame(canvas_footer, bg=BG_PANEL)
        legend_frame.pack(side="right")

        tk.Label(legend_frame, text="Less", bg=BG_PANEL, fg=TEXT_MUTED, font=FONT_SMALL).pack(side="left", padx=(0, 4))
        for lvl in range(5):
            box = tk.Label(
                legend_frame,
                bg=LEVEL_COLORS[lvl],
                width=2,
                height=1,
                relief="solid",
                bd=1,
                highlightbackground=LEVEL_BORDERS[lvl],
                highlightthickness=1
            )
            box.pack(side="left", padx=1)
        tk.Label(legend_frame, text="More", bg=BG_PANEL, fg=TEXT_MUTED, font=FONT_SMALL).pack(side="left", padx=(4, 4))

        # 4. Resizable Workspace Layout using PanedWindow
        # Vertical divider: allows resizing Middle panels vs Bottom Console
        self.v_paned = tk.PanedWindow(
            self.body,
            orient="vertical",
            sashrelief="groove",
            bg=BORDER_COLOR,
            bd=0,
            sashwidth=6,
            sashpad=2,
            opaqueresize=True
        )
        self.v_paned.pack(fill="both", expand=True, pady=(0, 4))

        # Horizontal divider: allows resizing Tools panel vs Git panel
        self.h_paned = tk.PanedWindow(
            self.v_paned,
            orient="horizontal",
            sashrelief="groove",
            bg=BORDER_COLOR,
            bd=0,
            sashwidth=6,
            sashpad=2,
            opaqueresize=True
        )

        # Panel A: Unified Composer & Tools
        tools_card = tk.LabelFrame(
            self.h_paned,
            text=" Інструменти та шари ",
            bg=BG_PANEL,
            fg=TEXT_PRIMARY,
            font=FONT_HEADING,
            bd=1,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1
        )
        self._build_tools_panel(tools_card)

        # Panel B: Git Operations & Config
        git_card = tk.LabelFrame(
            self.h_paned,
            text=" Керування Git та пуш ",
            bg=BG_PANEL,
            fg=TEXT_PRIMARY,
            font=FONT_HEADING,
            bd=1,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1
        )
        self._build_git_panel(git_card)

        # Add panels to horizontal paned window with comfortable minimum widths
        self.h_paned.add(tools_card, minsize=420, stretch="always")
        self.h_paned.add(git_card, minsize=320, stretch="always")

        # 5. Bottom Console Area
        console_frame = tk.Frame(self.v_paned, bg=BG_PANEL, bd=1, highlightbackground=BORDER_COLOR, highlightthickness=1)

        console_header = tk.Frame(console_frame, bg=BG_CARD)
        console_header.pack(fill="x")

        tk.Label(
            console_header,
            text="Журнал виконання операцій (Git Output)",
            bg=BG_CARD,
            fg=TEXT_MUTED,
            font=FONT_SMALL
        ).pack(side="left", padx=8, pady=3)

        tk.Button(
            console_header,
            text="Очистити",
            bg=BG_CARD,
            fg=TEXT_MUTED,
            activebackground=BG_PANEL,
            activeforeground=TEXT_WHITE,
            font=FONT_SMALL,
            relief="flat",
            bd=0,
            command=self._clear_log
        ).pack(side="right", padx=6, pady=2)

        self.log_text = tk.Text(
            console_frame,
            bg=BG_INPUT,
            fg=TEXT_PRIMARY,
            font=FONT_MONO_SMALL,
            height=4,
            relief="flat",
            wrap="word",
            padx=8,
            pady=4
        )
        self.log_text.pack(fill="both", expand=True)

        self.v_paned.add(self.h_paned, minsize=240, stretch="always")
        self.v_paned.add(console_frame, minsize=80, stretch="never")

    def _create_header_btn(self, parent, text, command):
        btn = tk.Button(
            parent,
            text=text,
            bg=BTN_SECONDARY_BG,
            fg=BTN_SECONDARY_FG,
            activebackground=BTN_SECONDARY_HOVER,
            activeforeground=TEXT_WHITE,
            relief="flat",
            bd=0,
            padx=6,
            pady=2,
            font=FONT_SMALL,
            cursor="hand2",
            command=command
        )
        btn.pack(side="left", padx=2)
        return btn

    def _rebuild_year_pills(self):
        for widget in self.year_pills_frame.winfo_children():
            widget.destroy()
        self.year_buttons.clear()

        tk.Label(self.year_pills_frame, text="Рік:", bg=BG_ROOT, fg=TEXT_MUTED, font=FONT_SMALL).pack(side="left", padx=4)

        prev_btn = tk.Button(
            self.year_pills_frame, text="◀", bg=BG_CARD, fg=TEXT_PRIMARY,
            relief="flat", bd=0, padx=4, pady=1, font=FONT_SMALL,
            command=lambda: self._select_year(self.project.active_year - 1)
        )
        prev_btn.pack(side="left", padx=1)

        displayed_years = sorted(list({2023, 2024, 2025, 2026, self.project.active_year}))

        for yr in displayed_years:
            is_active = (yr == self.project.active_year)
            bg_col = "#1f6feb" if is_active else BG_CARD
            fg_col = "#ffffff" if is_active else TEXT_PRIMARY

            btn = tk.Button(
                self.year_pills_frame,
                text=str(yr),
                bg=bg_col,
                fg=fg_col,
                activebackground="#388bfd",
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                padx=8,
                pady=2,
                font=FONT_BOLD if is_active else FONT_REGULAR,
                cursor="hand2",
                command=lambda y=yr: self._select_year(y)
            )
            btn.pack(side="left", padx=2)
            self.year_buttons[yr] = btn

        next_btn = tk.Button(
            self.year_pills_frame, text="▶", bg=BG_CARD, fg=TEXT_PRIMARY,
            relief="flat", bd=0, padx=4, pady=1, font=FONT_SMALL,
            command=lambda: self._select_year(self.project.active_year + 1)
        )
        next_btn.pack(side="left", padx=1)

    def _select_year(self, year: int):
        if year < 2008 or year > 2040:
            return
        self.project.set_active_year(year)
        self.selected_element_id = None
        self._rebuild_year_pills()
        self._refresh_elements_listbox()
        self.grid_widget.render_all()
        self._refresh_stats()
        self.log(f"Switched active year to {year}. Total weeks: {self.project.total_cols}")

    # ==================== COMPOSER & TOOLS PANEL ====================
    def _build_tools_panel(self, parent):
        notebook = ttk.Notebook(parent)
        notebook.pack(fill="both", expand=True, padx=8, pady=6)

        # TAB 1: ЕЛЕМЕНТИ (Unified Layer Composer with real-time smooth sliders)
        composer_tab = tk.Frame(notebook, bg=BG_PANEL)
        notebook.add(composer_tab, text="Шари")

        # Left / Right Split
        split_frame = tk.Frame(composer_tab, bg=BG_PANEL)
        split_frame.pack(fill="both", expand=True, padx=4, pady=4)

        # Left: Elements List & Actions
        left_col = tk.Frame(split_frame, bg=BG_PANEL, width=240)
        left_col.pack(side="left", fill="both", padx=(0, 8))

        list_btn_bar = tk.Frame(left_col, bg=BG_PANEL)
        list_btn_bar.pack(fill="x", pady=(0, 4))

        add_img_btn = tk.Button(
            list_btn_bar,
            text="+ Зображення",
            bg=BTN_PRIMARY_BG,
            fg=BTN_PRIMARY_FG,
            activebackground=BTN_PRIMARY_HOVER,
            relief="flat",
            font=FONT_BOLD,
            cursor="hand2",
            padx=6,
            pady=2,
            command=self._on_add_image_dialog
        )
        add_img_btn.pack(side="left", padx=1)

        add_txt_btn = tk.Button(
            list_btn_bar,
            text="+ Текст",
            bg=BTN_SECONDARY_BG,
            fg=BTN_SECONDARY_FG,
            activebackground=BTN_SECONDARY_HOVER,
            relief="flat",
            font=FONT_BOLD,
            cursor="hand2",
            padx=6,
            pady=2,
            command=self._on_add_text_dialog
        )
        add_txt_btn.pack(side="left", padx=1)

        add_tmpl_btn = tk.Button(
            list_btn_bar,
            text="+ Шаблон",
            bg=BG_CARD,
            fg=ACCENT_BLUE,
            activebackground=BTN_SECONDARY_HOVER,
            relief="flat",
            font=FONT_BOLD,
            cursor="hand2",
            padx=6,
            pady=2,
            command=self._on_add_template_menu
        )
        add_tmpl_btn.pack(side="left", padx=1)

        dup_btn = tk.Button(
            list_btn_bar,
            text="Дублювати",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            activebackground=BTN_SECONDARY_HOVER,
            activeforeground=TEXT_WHITE,
            relief="flat",
            font=FONT_SMALL,
            cursor="hand2",
            padx=4,
            pady=2,
            command=self._on_duplicate_selected_element
        )
        dup_btn.pack(side="left", padx=1)

        del_btn = tk.Button(
            list_btn_bar,
            text="Видалити",
            bg=BG_CARD,
            fg="#f85149",
            activebackground=BTN_DANGER_HOVER,
            activeforeground="#ffffff",
            relief="flat",
            font=FONT_SMALL,
            cursor="hand2",
            padx=4,
            pady=2,
            command=self._on_delete_selected_element
        )
        del_btn.pack(side="right", padx=1)

        # Listbox for elements
        self.elements_listbox = tk.Listbox(
            left_col,
            bg=BG_INPUT,
            fg=TEXT_PRIMARY,
            selectbackground="#1f6feb",
            selectforeground="#ffffff",
            font=FONT_SMALL,
            height=6,
            relief="flat",
            bd=1,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1
        )
        self.elements_listbox.pack(fill="both", expand=True)
        self.elements_listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

        # Right: Real-time Inspector with Smooth Sliders
        self.inspector_frame = tk.Frame(
            split_frame,
            bg=BG_CARD,
            bd=1,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1
        )
        self.inspector_frame.pack(side="left", fill="both", expand=True)

        self._build_inspector_widgets(self.inspector_frame)

        # TAB 2: ПЕНЗЛІ (Freehand Palette)
        brush_tab = tk.Frame(notebook, bg=BG_PANEL)
        notebook.add(brush_tab, text="Пензель")

        pal_frame = tk.Frame(brush_tab, bg=BG_PANEL)
        pal_frame.pack(fill="x", padx=6, pady=6)

        tk.Label(pal_frame, text="Рівень пензля:", bg=BG_PANEL, fg=TEXT_MUTED, font=FONT_SMALL).pack(side="left", padx=(0, 6))

        self.brush_var = tk.IntVar(value=4)
        labels = ["0: Гумка", "1: Світлий", "2: Середній", "3: Темний", "4: Яскравий"]
        for lvl in range(5):
            b = tk.Radiobutton(
                pal_frame,
                text=labels[lvl],
                variable=self.brush_var,
                value=lvl,
                indicatoron=0,
                bg=LEVEL_COLORS[lvl],
                fg=TEXT_WHITE if lvl > 0 else TEXT_MUTED,
                selectcolor="#238636" if lvl > 0 else "#30363d",
                activebackground=LEVEL_BORDERS[lvl],
                activeforeground=TEXT_WHITE,
                font=FONT_SMALL,
                padx=6,
                pady=3,
                command=lambda l=lvl: self._on_select_brush(l)
            )
            b.pack(side="left", padx=2)

        trans_frame = tk.Frame(brush_tab, bg=BG_PANEL)
        trans_frame.pack(fill="x", padx=6, pady=6)

        self._create_header_btn(trans_frame, "◀ Вліво", lambda: self._on_shift(-1, 0))
        self._create_header_btn(trans_frame, "Вправо ▶", lambda: self._on_shift(1, 0))
        self._create_header_btn(trans_frame, "▲ Вгору", lambda: self._on_shift(0, -1))
        self._create_header_btn(trans_frame, "▼ Вниз", lambda: self._on_shift(0, 1))
        self._create_header_btn(trans_frame, "Інвертувати", self._on_invert)
        self._create_header_btn(trans_frame, "Очистити", self._on_clear_year)

        # TAB 3: ШАБЛОНИ (Templates)
        tmpl_tab = tk.Frame(notebook, bg=BG_PANEL)
        notebook.add(tmpl_tab, text="Шаблони")

        tmpl_row1 = tk.Frame(tmpl_tab, bg=BG_PANEL)
        tmpl_row1.pack(fill="x", padx=6, pady=(6, 2))

        tk.Label(tmpl_row1, text="Додати шаблон:", bg=BG_PANEL, fg=TEXT_MUTED, font=FONT_SMALL).pack(side="left", padx=(0, 6))
        self._create_header_btn(tmpl_row1, "+ Серце", lambda: self._apply_template("heart"))
        self._create_header_btn(tmpl_row1, "+ Галочка", lambda: self._apply_template("check"))
        self._create_header_btn(tmpl_row1, "+ Хвиля", lambda: self._apply_template("wave"))
        self._create_header_btn(tmpl_row1, "+ Шахівниця", lambda: self._apply_template("checkerboard"))

        tmpl_row2 = tk.Frame(tmpl_tab, bg=BG_PANEL)
        tmpl_row2.pack(fill="x", padx=6, pady=(4, 6))

        tk.Label(tmpl_row2, text="Зсув поля / шаблонів:", bg=BG_PANEL, fg=TEXT_MUTED, font=FONT_SMALL).pack(side="left", padx=(0, 6))
        self._create_header_btn(tmpl_row2, "◀ Вліво", lambda: self._on_shift(-1, 0))
        self._create_header_btn(tmpl_row2, "Вправо ▶", lambda: self._on_shift(1, 0))
        self._create_header_btn(tmpl_row2, "▲ Вгору", lambda: self._on_shift(0, -1))
        self._create_header_btn(tmpl_row2, "▼ Вниз", lambda: self._on_shift(0, 1))

        info_lbl = tk.Label(
            tmpl_tab,
            text="💡 Шаблони додаються як інтерактивні шари — їх можна вільно переміщати повзунками X / Y у вкладці «Шари».",
            bg=BG_PANEL,
            fg=TEXT_MUTED,
            font=FONT_SMALL,
            anchor="w"
        )
        info_lbl.pack(fill="x", padx=8, pady=(2, 4))

    def _build_inspector_widgets(self, parent):
        """Builds controls inside the Element Inspector using smooth sliders."""
        self.inspector_header = tk.Label(
            parent,
            text="Оберіть або додайте елемент зі списку ліворуч",
            bg=BG_CARD,
            fg=ACCENT_BLUE,
            font=FONT_HEADING
        )
        self.inspector_header.pack(anchor="w", padx=10, pady=(6, 4))

        # Common Sliders Frame (X and Y position with smooth Scales!)
        pos_frame = tk.Frame(parent, bg=BG_CARD)
        pos_frame.pack(fill="x", padx=10, pady=2)

        # X Slider (0..52 weeks)
        x_row = tk.Frame(pos_frame, bg=BG_CARD)
        x_row.pack(fill="x", pady=1)

        tk.Label(x_row, text="Зсув X (тиждень):", bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_SMALL, width=14, anchor="w").pack(side="left")
        self.x_scale = tk.Scale(
            x_row,
            from_=0,
            to=52,
            orient="horizontal",
            length=220,
            bg=BG_CARD,
            fg=TEXT_WHITE,
            troughcolor=BG_INPUT,
            activebackground=ACCENT_GREEN,
            highlightthickness=0,
            showvalue=0,
            command=self._on_inspector_slider_change
        )
        self.x_scale.pack(side="left", padx=4)
        self.x_val_lbl = tk.Label(x_row, text="тиждень 0", bg=BG_CARD, fg=ACCENT_GREEN, font=FONT_BOLD, width=11, anchor="w")
        self.x_val_lbl.pack(side="left", padx=4)

        # Y Slider (0..6 rows)
        y_row = tk.Frame(pos_frame, bg=BG_CARD)
        y_row.pack(fill="x", pady=1)

        tk.Label(y_row, text="Зсув Y (рядок):", bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_SMALL, width=14, anchor="w").pack(side="left")
        self.y_scale = tk.Scale(
            y_row,
            from_=0,
            to=6,
            orient="horizontal",
            length=220,
            bg=BG_CARD,
            fg=TEXT_WHITE,
            troughcolor=BG_INPUT,
            activebackground=ACCENT_GREEN,
            highlightthickness=0,
            showvalue=0,
            command=self._on_inspector_slider_change
        )
        self.y_scale.pack(side="left", padx=4)
        self.y_val_lbl = tk.Label(y_row, text="рядок 0", bg=BG_CARD, fg=ACCENT_GREEN, font=FONT_BOLD, width=11, anchor="w")
        self.y_val_lbl.pack(side="left", padx=4)

        # Dynamic Content Container (Swapped depending on Image vs Text)
        self.type_specific_frame = tk.Frame(parent, bg=BG_CARD)
        self.type_specific_frame.pack(fill="both", expand=True, padx=10, pady=(2, 6))

    def _build_image_inspector(self, parent, el: dict):
        for w in parent.winfo_children():
            w.destroy()

        # Row 1: File & Change button
        f_row = tk.Frame(parent, bg=BG_CARD)
        f_row.pack(fill="x", pady=2)

        tk.Label(f_row, text="Файл:", bg=BG_CARD, fg=TEXT_MUTED, font=FONT_SMALL, width=14, anchor="w").pack(side="left")
        fname = os.path.basename(el.get("filepath", ""))
        self.cur_img_lbl = tk.Label(f_row, text=fname, bg=BG_CARD, fg=ACCENT_BLUE, font=FONT_BOLD, anchor="w")
        self.cur_img_lbl.pack(side="left", fill="x", expand=True, padx=4)

        tk.Button(
            f_row,
            text="Змінити файл...",
            bg=BG_PANEL,
            fg=TEXT_PRIMARY,
            relief="flat",
            bd=0,
            font=FONT_SMALL,
            command=self._on_change_element_image
        ).pack(side="right")

        # Row 2: Sensitivity Slider (0.2x .. 3.0x)
        sens_row = tk.Frame(parent, bg=BG_CARD)
        sens_row.pack(fill="x", pady=2)

        tk.Label(sens_row, text="Сила виділення:", bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_SMALL, width=14, anchor="w").pack(side="left")
        self.sens_scale = tk.Scale(
            sens_row,
            from_=0.2,
            to=3.0,
            resolution=0.1,
            orient="horizontal",
            length=220,
            bg=BG_CARD,
            fg=TEXT_WHITE,
            troughcolor=BG_INPUT,
            activebackground=ACCENT_GREEN,
            highlightthickness=0,
            showvalue=0,
            command=self._on_inspector_slider_change
        )
        self.sens_scale.set(el.get("sensitivity", 1.0))
        self.sens_scale.pack(side="left", padx=4)

        self.sens_val_lbl = tk.Label(
            sens_row,
            text=f"{el.get('sensitivity', 1.0):.1f}x",
            bg=BG_CARD,
            fg=ACCENT_GREEN,
            font=FONT_BOLD,
            width=11,
            anchor="w"
        )
        self.sens_val_lbl.pack(side="left", padx=4)

        # Row 3: Height & Invert Checkbox
        opt_row = tk.Frame(parent, bg=BG_CARD)
        opt_row.pack(fill="x", pady=2)

        tk.Label(opt_row, text="Висота (px):", bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_SMALL, width=14, anchor="w").pack(side="left")
        self.h_scale = tk.Scale(
            opt_row,
            from_=1,
            to=7,
            orient="horizontal",
            length=120,
            bg=BG_CARD,
            fg=TEXT_WHITE,
            troughcolor=BG_INPUT,
            activebackground=ACCENT_GREEN,
            highlightthickness=0,
            showvalue=0,
            command=self._on_inspector_slider_change
        )
        self.h_scale.set(el.get("height", 7))
        self.h_scale.pack(side="left", padx=4)

        self.h_val_lbl = tk.Label(opt_row, text=f"{el.get('height', 7)} px", bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_SMALL, width=6, anchor="w")
        self.h_val_lbl.pack(side="left", padx=2)

        self.invert_var = tk.BooleanVar(value=el.get("invert", False))
        inv_chk = tk.Checkbutton(
            opt_row,
            text="Інвертувати чорне/біле",
            variable=self.invert_var,
            command=self._on_inspector_slider_change,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            selectcolor=BG_INPUT,
            font=FONT_SMALL
        )
        inv_chk.pack(side="left", padx=10)

    def _build_text_inspector(self, parent, el: dict):
        for w in parent.winfo_children():
            w.destroy()

        # Row 1: Live Text Input
        t_row = tk.Frame(parent, bg=BG_CARD)
        t_row.pack(fill="x", pady=2)

        tk.Label(t_row, text="Текст:", bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_SMALL, width=14, anchor="w").pack(side="left")
        self.live_text_var = tk.StringVar(value=el.get("text", "CODE"))
        self.live_text_var.trace_add("write", lambda *a: self._on_live_text_change())

        t_entry = tk.Entry(
            t_row,
            textvariable=self.live_text_var,
            bg=BG_INPUT,
            fg=TEXT_WHITE,
            insertbackground=TEXT_WHITE,
            font=FONT_BOLD,
            width=20
        )
        t_entry.pack(side="left", padx=4)

        tk.Label(t_row, text="(динамічне оновлення)", bg=BG_CARD, fg=TEXT_MUTED, font=FONT_SMALL).pack(side="left", padx=6)

        # Row 2: Level Selection
        lvl_row = tk.Frame(parent, bg=BG_CARD)
        lvl_row.pack(fill="x", pady=2)

        tk.Label(lvl_row, text="Яскравість (Рівень):", bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_SMALL, width=14, anchor="w").pack(side="left")
        self.text_lvl_var = tk.IntVar(value=el.get("level", 4))

        for l in range(1, 5):
            b = tk.Radiobutton(
                lvl_row,
                text=f"Рівень {l}",
                variable=self.text_lvl_var,
                value=l,
                indicatoron=0,
                bg=LEVEL_COLORS[l],
                fg=TEXT_WHITE,
                selectcolor="#238636",
                activebackground=LEVEL_BORDERS[l],
                font=FONT_SMALL,
                padx=8,
                pady=2,
                command=self._on_inspector_slider_change
            )
            b.pack(side="left", padx=2)

    def _refresh_elements_listbox(self):
        """Populates elements listbox with current year's items."""
        self.elements_listbox.delete(0, "end")
        elements = self.project.get_elements()
        selected_idx = None

        for idx, el in enumerate(elements):
            text = f"{el.get('name', 'Елемент')}  [X:{el.get('x', 0)}]"
            self.elements_listbox.insert("end", text)
            if el["id"] == self.selected_element_id:
                selected_idx = idx

        if selected_idx is not None:
            self.elements_listbox.selection_set(selected_idx)
            self.elements_listbox.activate(selected_idx)
        elif elements:
            self.elements_listbox.selection_set(0)
            self.selected_element_id = elements[0]["id"]
            self._load_element_into_inspector(elements[0])
        else:
            self.selected_element_id = None
            self.inspector_header.config(text="Немає активних елементів. Додайте картинку чи текст!")
            for w in self.type_specific_frame.winfo_children():
                w.destroy()

    def _on_listbox_select(self, event):
        sel = self.elements_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        elements = self.project.get_elements()
        if 0 <= idx < len(elements):
            el = elements[idx]
            self.selected_element_id = el["id"]
            self._load_element_into_inspector(el)

    def _load_element_into_inspector(self, el: dict):
        self._suppress_inspector_updates = True
        try:
            self.inspector_header.config(text=f"Налаштування: {el.get('name', 'Елемент')}")

            x = el.get("x", 0)
            y = el.get("y", 0)
            self.x_scale.set(x)
            self.x_val_lbl.config(text=f"тиждень {x}")
            self.y_scale.set(y)
            self.y_val_lbl.config(text=f"рядок {y}")

            if el["type"] == "image":
                self._build_image_inspector(self.type_specific_frame, el)
            elif el["type"] == "text":
                self._build_text_inspector(self.type_specific_frame, el)
            elif el["type"] == "template":
                self._build_template_inspector(self.type_specific_frame, el)
        finally:
            self._suppress_inspector_updates = False

    def _on_inspector_slider_change(self, *args):
        """Real-time live callback whenever any slider moves!"""
        if self._suppress_inspector_updates or not self.selected_element_id:
            return

        x = int(self.x_scale.get())
        y = int(self.y_scale.get())
        self.x_val_lbl.config(text=f"тиждень {x}")
        self.y_val_lbl.config(text=f"рядок {y}")

        updates = {"x": x, "y": y}

        # Check if image inspector is active
        if hasattr(self, "sens_scale") and self.sens_scale.winfo_exists():
            sens = float(self.sens_scale.get())
            self.sens_val_lbl.config(text=f"{sens:.1f}x")
            h = int(self.h_scale.get())
            self.h_val_lbl.config(text=f"{h} px")
            inv = self.invert_var.get()
            updates.update({"sensitivity": sens, "height": h, "invert": inv})

        # Check if text level is active
        if hasattr(self, "text_lvl_var"):
            updates["level"] = self.text_lvl_var.get()

        # Check if template level is active
        if hasattr(self, "tmpl_lvl_var"):
            updates["level"] = self.tmpl_lvl_var.get()

        self.project.update_element(self.selected_element_id, updates)
        self.grid_widget.render_all()
        self._refresh_stats()

    def _build_template_inspector(self, parent, el: dict):
        for w in parent.winfo_children():
            w.destroy()

        # Row 1: Template Type Selection
        t_row = tk.Frame(parent, bg=BG_CARD)
        t_row.pack(fill="x", pady=2)

        tk.Label(t_row, text="Тип шаблону:", bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_SMALL, width=14, anchor="w").pack(side="left")

        self.template_key_var = tk.StringVar(value=el.get("template_key", "heart"))
        tmpl_choices = [("heart", "Серце"), ("check", "Галочка"), ("wave", "Хвиля"), ("checkerboard", "Шахівниця")]

        for key, title in tmpl_choices:
            b = tk.Radiobutton(
                t_row,
                text=title,
                variable=self.template_key_var,
                value=key,
                bg=BG_CARD,
                fg=TEXT_WHITE,
                selectcolor="#1f6feb",
                activebackground=BTN_SECONDARY_HOVER,
                font=FONT_SMALL,
                command=self._on_template_type_change
            )
            b.pack(side="left", padx=4)

        # Row 2: Level Selection
        lvl_row = tk.Frame(parent, bg=BG_CARD)
        lvl_row.pack(fill="x", pady=2)

        tk.Label(lvl_row, text="Яскравість (Рівень):", bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_SMALL, width=14, anchor="w").pack(side="left")
        self.tmpl_lvl_var = tk.IntVar(value=el.get("level", 4))

        for l in range(1, 5):
            b = tk.Radiobutton(
                lvl_row,
                text=f"Рівень {l}",
                variable=self.tmpl_lvl_var,
                value=l,
                indicatoron=0,
                bg=LEVEL_COLORS[l],
                fg=TEXT_WHITE,
                selectcolor="#238636",
                activebackground=LEVEL_BORDERS[l],
                font=FONT_SMALL,
                padx=8,
                pady=2,
                command=self._on_template_level_change
            )
            b.pack(side="left", padx=2)

    def _on_template_type_change(self):
        if not self.selected_element_id:
            return
        new_key = self.template_key_var.get()
        self.project.update_element(self.selected_element_id, {"template_key": new_key})
        self._refresh_elements_listbox()
        self.grid_widget.render_all()
        self._refresh_stats()

    def _on_template_level_change(self):
        if not self.selected_element_id:
            return
        new_lvl = self.tmpl_lvl_var.get()
        self.project.update_element(self.selected_element_id, {"level": new_lvl})
        self.grid_widget.render_all()
        self._refresh_stats()

    def _on_add_template_menu(self):
        menu = tk.Menu(self, tearoff=0, bg=BG_CARD, fg=TEXT_WHITE, activebackground="#1f6feb", font=FONT_REGULAR)
        menu.add_command(label="Серце", command=lambda: self._apply_template("heart"))
        menu.add_command(label="Галочка", command=lambda: self._apply_template("check"))
        menu.add_command(label="Хвиля", command=lambda: self._apply_template("wave"))
        menu.add_command(label="Шахівниця", command=lambda: self._apply_template("checkerboard"))
        try:
            x = self.winfo_pointerx()
            y = self.winfo_pointery()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _on_live_text_change(self):
        if self._suppress_inspector_updates or not self.selected_element_id:
            return
        new_text = self.live_text_var.get()
        self.project.update_element(self.selected_element_id, {"text": new_text})
        self.grid_widget.render_all()
        self._refresh_stats()

        # Update name in listbox
        sel = self.elements_listbox.curselection()
        if sel:
            x = int(self.x_scale.get())
            self.elements_listbox.delete(sel[0])
            self.elements_listbox.insert(sel[0], f"Текст: «{new_text}»  [X:{x}]")
            self.elements_listbox.selection_set(sel[0])

    def _on_add_image_dialog(self):
        filetypes = [("Image files", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")]
        filepath = filedialog.askopenfilename(title="Вибрати зображення для додавання", filetypes=filetypes)
        if filepath:
            self.project.save_state()
            # Calculate next smart position
            existing = self.project.get_elements()
            next_x = 0
            if existing:
                last_el = existing[-1]
                next_x = min(46, last_el.get("x", 0) + 12)

            el = self.project.add_image_element(filepath=filepath, x=next_x, y=0, height=7, sensitivity=1.0)
            self.selected_element_id = el["id"]
            self._refresh_elements_listbox()
            self._load_element_into_inspector(el)
            self.grid_widget.render_all()
            self._refresh_stats()
            self.log(f"Added image element: {os.path.basename(filepath)} at week {next_x}")

    def _on_change_element_image(self):
        if not self.selected_element_id:
            return
        filetypes = [("Image files", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")]
        filepath = filedialog.askopenfilename(title="Замінити файл зображення", filetypes=filetypes)
        if filepath:
            self.project.save_state()
            self.project.update_element(self.selected_element_id, {"filepath": filepath})
            self.cur_img_lbl.config(text=os.path.basename(filepath))
            self._refresh_elements_listbox()
            self.grid_widget.render_all()
            self._refresh_stats()
            self.log(f"Updated element image: {os.path.basename(filepath)}")

    def _on_add_text_dialog(self):
        self.project.save_state()
        existing = self.project.get_elements()
        next_x = 0
        if existing:
            last_el = existing[-1]
            next_x = min(46, last_el.get("x", 0) + 12)

        el = self.project.add_text_element(text="CODE", x=next_x, y=0, level=4)
        self.selected_element_id = el["id"]
        self._refresh_elements_listbox()
        self._load_element_into_inspector(el)
        self.grid_widget.render_all()
        self._refresh_stats()
        self.log(f"Added text element 'CODE' at week {next_x}")

    def _on_delete_selected_element(self):
        if not self.selected_element_id:
            return
        self.project.save_state()
        self.project.remove_element(self.selected_element_id)
        self.selected_element_id = None
        self._refresh_elements_listbox()
        self.grid_widget.render_all()
        self._refresh_stats()
        self.log("Deleted selected element.")

    # ==================== GIT PANEL ====================
    def _build_git_panel(self, parent):
        dir_frame = tk.Frame(parent, bg=BG_PANEL)
        dir_frame.pack(fill="x", padx=8, pady=(4, 2))

        tk.Label(dir_frame, text="Репозиторій:", bg=BG_PANEL, fg=TEXT_MUTED, font=FONT_SMALL).pack(side="left")
        self.dir_lbl = tk.Label(
            dir_frame,
            text=self.target_dir,
            bg=BG_PANEL,
            fg=ACCENT_BLUE,
            font=FONT_MONO_SMALL,
            anchor="w"
        )
        self.dir_lbl.pack(side="left", fill="x", expand=True, padx=6)

        browse_btn = tk.Button(
            dir_frame,
            text="Огляд...",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            relief="flat",
            bd=0,
            font=FONT_SMALL,
            command=self._on_browse_repo
        )
        browse_btn.pack(side="right", padx=(2, 0))

        scan_btn = tk.Button(
            dir_frame,
            text="Сканувати Git",
            bg="#1f6feb",
            fg="#ffffff",
            activebackground="#388bfd",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            font=FONT_BOLD,
            cursor="hand2",
            padx=8,
            pady=2,
            command=self._on_scan_repo
        )
        scan_btn.pack(side="right", padx=(4, 2))

        # Branch & GitHub default branch info
        branch_frame = tk.Frame(parent, bg=BG_PANEL)
        branch_frame.pack(fill="x", padx=8, pady=(1, 2))

        cur_br = self.git_engine.get_current_branch()
        self.branch_lbl = tk.Label(
            branch_frame,
            text=f"Гілка: {cur_br}",
            bg=BG_PANEL,
            fg=ACCENT_GREEN,
            font=FONT_BOLD
        )
        self.branch_lbl.pack(side="left")

        tk.Label(
            branch_frame,
            text="• GitHub рахує внески лише в гілці за замовчуванням (main)",
            bg=BG_PANEL,
            fg=TEXT_MUTED,
            font=FONT_SMALL
        ).pack(side="left", padx=8)

        author_frame = tk.Frame(parent, bg=BG_PANEL)
        author_frame.pack(fill="x", padx=8, pady=2)

        tk.Label(author_frame, text="GitHub Email:", bg=BG_PANEL, fg=TEXT_MUTED, font=FONT_SMALL).pack(side="left")
        email_entry = tk.Entry(
            author_frame,
            textvariable=self.author_email_var,
            bg=BG_INPUT,
            fg=TEXT_WHITE,
            insertbackground=TEXT_WHITE,
            font=FONT_REGULAR,
            width=26
        )
        email_entry.pack(side="left", padx=6)

        msg_frame = tk.Frame(parent, bg=BG_PANEL)
        msg_frame.pack(fill="x", padx=8, pady=2)

        tk.Label(msg_frame, text="Шаблон коміту:", bg=BG_PANEL, fg=TEXT_MUTED, font=FONT_SMALL).pack(side="left")
        self.commit_msg_var = tk.StringVar(value="chore: update build log ({date})")
        msg_entry = tk.Entry(
            msg_frame,
            textvariable=self.commit_msg_var,
            bg=BG_INPUT,
            fg=TEXT_WHITE,
            insertbackground=TEXT_WHITE,
            font=FONT_REGULAR,
            width=28
        )
        msg_entry.pack(side="left", padx=6)
        tk.Label(msg_frame, text="(підтримує {date}, {i})", bg=BG_PANEL, fg=TEXT_MUTED, font=FONT_SMALL).pack(side="left")

        scope_frame = tk.Frame(parent, bg=BG_PANEL)
        scope_frame.pack(fill="x", padx=8, pady=4)

        self.commit_scope_var = tk.StringVar(value="current")
        rb1 = tk.Radiobutton(
            scope_frame,
            text="Тільки поточний рік",
            variable=self.commit_scope_var,
            value="current",
            bg=BG_PANEL,
            fg=TEXT_PRIMARY,
            selectcolor=BG_INPUT,
            font=FONT_SMALL
        )
        rb1.pack(side="left", padx=(0, 8))

        rb2 = tk.Radiobutton(
            scope_frame,
            text="Всі роки з малюнками",
            variable=self.commit_scope_var,
            value="all",
            bg=BG_PANEL,
            fg=TEXT_PRIMARY,
            selectcolor=BG_INPUT,
            font=FONT_SMALL
        )
        rb2.pack(side="left")

        btn_grid = tk.Frame(parent, bg=BG_PANEL)
        btn_grid.pack(fill="x", padx=8, pady=(4, 6))
        btn_grid.columnconfigure(0, weight=1)
        btn_grid.columnconfigure(1, weight=1)

        dry_run_btn = tk.Button(
            btn_grid,
            text="Попередній перегляд",
            bg=BTN_SECONDARY_BG,
            fg=BTN_SECONDARY_FG,
            activebackground=BTN_SECONDARY_HOVER,
            relief="flat",
            font=FONT_BOLD,
            cursor="hand2",
            padx=6,
            pady=4,
            command=self._on_dry_run
        )
        dry_run_btn.grid(row=0, column=0, sticky="ew", padx=2, pady=2)

        apply_btn = tk.Button(
            btn_grid,
            text="Створити коміти",
            bg=BTN_PRIMARY_BG,
            fg=BTN_PRIMARY_FG,
            activebackground=BTN_PRIMARY_HOVER,
            relief="flat",
            font=FONT_BOLD,
            cursor="hand2",
            padx=6,
            pady=4,
            command=self._on_apply_commits
        )
        apply_btn.grid(row=0, column=1, sticky="ew", padx=2, pady=2)

        push_btn = tk.Button(
            btn_grid,
            text="Пуш в GitHub",
            bg="#1f6feb",
            fg="#ffffff",
            activebackground="#388bfd",
            relief="flat",
            font=FONT_BOLD,
            cursor="hand2",
            padx=6,
            pady=4,
            command=self._on_push
        )
        push_btn.grid(row=1, column=0, sticky="ew", padx=2, pady=2)

        wipe_btn = tk.Button(
            btn_grid,
            text="Скинути історію",
            bg=BTN_DANGER_BG,
            fg=BTN_DANGER_FG,
            activebackground=BTN_DANGER_HOVER,
            activeforeground="#ffffff",
            relief="flat",
            font=FONT_SMALL,
            cursor="hand2",
            padx=6,
            pady=4,
            command=self._on_wipe_art
        )
        wipe_btn.grid(row=1, column=1, sticky="ew", padx=2, pady=2)

        self.git_action_buttons = [dry_run_btn, apply_btn, push_btn, wipe_btn]

        # Live Commit Generation Progress Bar
        self.progress_frame = tk.Frame(parent, bg=BG_PANEL)
        self.progress_frame.pack(fill="x", padx=8, pady=(0, 6))

        self.progress_bar = ttk.Progressbar(self.progress_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.progress_lbl = tk.Label(
            self.progress_frame,
            text="Готово",
            bg=BG_PANEL,
            fg=TEXT_MUTED,
            font=FONT_SMALL,
            width=20,
            anchor="w"
        )
        self.progress_lbl.pack(side="right")
        self.progress_frame.pack_forget()

    # ==================== EVENT HANDLERS ====================
    def _on_zoom_in(self):
        self._set_zoom(self.current_zoom + 2)

    def _on_zoom_out(self):
        self._set_zoom(self.current_zoom - 2)

    def _set_zoom(self, size: int):
        size = max(10, min(28, size))
        if size == self.current_zoom:
            return
        self.current_zoom = size
        self.zoom_lbl.config(text=f"{size}px")
        self.grid_widget.set_cell_size(size)
        self._check_canvas_scroll()

    def _check_canvas_scroll(self):
        """Show or hide horizontal scrollbar depending on whether canvas overflows viewport."""
        try:
            viewport_w = self.canvas_card.winfo_width()
            grid_w = self.grid_widget.winfo_reqwidth()
            if viewport_w > 1 and grid_w > (viewport_w - 20):
                if not self.grid_scroll_x.winfo_ismapped():
                    self.grid_scroll_x.pack(side="bottom", fill="x", padx=10, pady=(0, 4))
            else:
                if self.grid_scroll_x.winfo_ismapped():
                    self.grid_scroll_x.pack_forget()
        except Exception:
            pass

    def _on_select_brush(self, level: int):
        self.grid_widget.set_active_brush(level)

    def _on_canvas_modified(self):
        self._refresh_stats()

    def _on_canvas_hover(self, cell_date: Optional[date], weekday: str, commits: int, level: int, in_year: bool):
        if not cell_date or not in_year:
            self.hover_lbl.config(text="Наведіть курсор на клітинку для перегляду дати...")
            return

        date_formatted = cell_date.strftime("%d.%m.%Y")
        ukr_days = {
            "Sun": "Неділя",
            "Mon": "Понеділок",
            "Tue": "Вівторок",
            "Wed": "Середа",
            "Thu": "Четвер",
            "Fri": "П'ятниця",
            "Sat": "Субота"
        }
        day_ukr = ukr_days.get(weekday, weekday)
        self.hover_lbl.config(
            text=f"{day_ukr}, {date_formatted}  •  {commits} комітів (Рівень {level})"
        )

    def _refresh_stats(self):
        stats = self.project.get_stats(self.project.active_year)
        total = stats["total_commits"]
        active = stats["active_days"]
        year = stats["year"]

        if total == 1:
            text = f"1 contribution in {year}"
        else:
            text = f"{total} contributions in {year}"

        if active > 0:
            text += f" ({active} активних днів)"

        self.contrib_count_lbl.config(text=text)

    def _on_shift(self, dx: int = 0, dy: int = 0):
        self.project.shift(dx=dx, dy=dy)
        if self.selected_element_id:
            for el in self.project.get_elements():
                if el["id"] == self.selected_element_id:
                    self._suppress_inspector_updates = True
                    try:
                        self.x_scale.set(el.get("x", 0))
                        self.y_scale.set(el.get("y", 0))
                        self.x_val_lbl.config(text=f"тиждень {el.get('x', 0)}")
                        self.y_val_lbl.config(text=f"рядок {el.get('y', 0)}")
                    finally:
                        self._suppress_inspector_updates = False
                    break
        self._refresh_elements_listbox()
        self.grid_widget.render_all()
        self._refresh_stats()

    def _on_invert(self):
        self.project.invert()
        self.grid_widget.render_all()
        self._refresh_stats()

    def _on_clear_year(self):
        if messagebox.askyesno("Очищення", f"Очистити всі малюнки та елементи за {self.project.active_year} рік?"):
            self.project.clear()
            self.selected_element_id = None
            self._refresh_elements_listbox()
            self.grid_widget.render_all()
            self._refresh_stats()
            self.log(f"Cleared year {self.project.active_year}")

    def _on_undo(self):
        if self.project.undo():
            self._rebuild_year_pills()
            self._refresh_elements_listbox()
            self.grid_widget.render_all()
            self._refresh_stats()
            self.log("Відмінено дію (Undo)")

    def _on_redo(self):
        if self.project.redo():
            self._rebuild_year_pills()
            self._refresh_elements_listbox()
            self.grid_widget.render_all()
            self._refresh_stats()
            self.log("Повторено дію (Redo)")

    def _apply_template(self, name: str):
        self.project.save_state()
        existing = self.project.get_elements()
        next_x = 20
        if existing:
            last_el = existing[-1]
            next_x = min(46, last_el.get("x", 0) + 8)

        el = self.project.add_template_element(template_key=name, x=next_x, y=0, level=4)
        self.selected_element_id = el["id"]
        self._refresh_elements_listbox()
        self._load_element_into_inspector(el)
        self.grid_widget.render_all()
        self._refresh_stats()
        self.log(f"Додано шаблон '{el['name']}' на тиждень {next_x}. Використовуйте повзунки або стрілки для переміщення.")

    def _on_scan_repo(self):
        email_filter = self.author_email_var.get().strip() or None
        self.log(f"Сканування репозиторію {self.target_dir}...")

        date_counts, all_years = self.git_engine.fetch_repo_contributions(
            year=self.project.active_year,
            filter_email=email_filter
        )

        count = len(date_counts)
        total_commits = sum(date_counts.values())

        if total_commits > 0:
            self.log(f"Знайдено {total_commits} комітів за {count} днів у {self.project.active_year} році.")
            self.project.load_existing_contributions(self.project.active_year, date_counts)
            self.grid_widget.render_all()
            self._refresh_stats()
            self.log("Поточні коміти репозиторію успішно відображено на полотні!")
        else:
            if all_years:
                other_years = sorted(list(all_years))
                self.log(f"У {self.project.active_year} році комітів не знайдено. В історії є коміти за: {', '.join(map(str, other_years))}.")
                if messagebox.askyesno(
                    "Перемкнути рік?",
                    f"У {self.project.active_year} році комітів не знайдено.\n\nВ історії репозиторію є коміти за {other_years[-1]} рік.\nПеремкнути активний рік на {other_years[-1]} та показати їх?"
                ):
                    self._select_year(other_years[-1])
                    self._on_scan_repo()
                    return
            else:
                self.log(f"У репозиторії {self.target_dir} комітів не знайдено (або він ще не містить історії).")
                self.log("Підказка: створіть бажаний малюнок або напис та натисніть «Створити коміти».")

    def _on_browse_repo(self):
        directory = filedialog.askdirectory(title="Вибрати цільовий Git-репозиторій", initialdir=self.target_dir)
        if directory:
            self.target_dir = os.path.abspath(directory)
            self.dir_lbl.config(text=self.target_dir)
            self.git_engine = GitEngine(self.target_dir)
            if hasattr(self, "branch_lbl"):
                self.branch_lbl.config(text=f"Гілка: {self.git_engine.get_current_branch()}")
            name, email = self.git_engine.get_author_config()
            if email and not self.author_email_var.get():
                self.author_email_var.set(email)
            if name and not self.author_name_var.get():
                self.author_name_var.set(name)
            self.log(f"Target repository changed to: {self.target_dir}")

    def _get_target_plan(self):
        scope = self.commit_scope_var.get()
        target_year = self.project.active_year if scope == "current" else None
        return self.project.get_commit_plan(year=target_year)

    def _on_dry_run(self):
        email = self.author_email_var.get().strip()
        name = self.author_name_var.get().strip()
        plan = self._get_target_plan()

        if not plan:
            messagebox.showinfo("Dry Run", "Немає активних клітинок для комітів у вибраному режимі.")
            return

        total_commits = sum(cnt for _, cnt in plan)
        min_date = plan[0][0]
        max_date = plan[-1][0]

        self.log("=" * 50)
        self.log("DRY RUN (Попередній перегляд комітів):")
        self.log(f"  Цільовий репозиторій: {self.target_dir}")
        self.log(f"  Автор: {name} <{email}>")
        self.log(f"  Кількість днів з комітами: {len(plan)}")
        self.log(f"  Загальна кількість комітів: {total_commits}")
        self.log(f"  Діапазон дат: {min_date} — {max_date}")
        self.log("Жодних змін до Git внесено НЕ було.")
        self.log("=" * 50)

        messagebox.showinfo(
            "Dry Run Завершено",
            f"План комітів готовий:\n\n"
            f"• Всього комітів: {total_commits}\n"
            f"• Активних днів: {len(plan)}\n"
            f"• Період: {min_date} — {max_date}\n\n"
            f"Натисніть 'Створити коміти', щоб записати їх у Git."
        )

    def _set_git_buttons_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for btn in getattr(self, "git_action_buttons", []):
            try:
                btn.config(state=state)
            except Exception:
                pass

    def _update_commit_progress(self, cur: int, tot: int, pct: int, msg: str):
        self.progress_bar["value"] = cur
        self.progress_lbl.config(text=f"{cur} / {tot} ({pct}%)")
        self.log(msg)

    def _finish_commit_progress(self, created: int):
        self._set_git_buttons_enabled(True)
        self.progress_lbl.config(text="Готово!")
        messagebox.showinfo(
            "Успішно",
            f"Створено {created} комітів у локальному репозиторії!\n\n"
            "Тепер натисніть '⬆ Пуш в GitHub', щоб відправити їх."
        )

    def _fail_commit_progress(self, err_msg: str):
        self._set_git_buttons_enabled(True)
        self.progress_lbl.config(text="Помилка")
        messagebox.showerror("Помилка Git", err_msg)

    def _on_apply_commits(self):
        email = self.author_email_var.get().strip()
        name = self.author_name_var.get().strip()

        if not email or "@" not in email or "." not in email:
            messagebox.showerror(
                "Некоректний Email",
                "Будь ласка, вкажіть дійсний GitHub Email (наприклад, user@example.com або noreply-email)!\n\n"
                "GitHub зараховує внески у профіль ТІЛЬКИ якщо email автора точно збігається з доданим у ваш акаунт GitHub."
            )
            return

        cur_branch = self.git_engine.get_current_branch()
        if cur_branch not in ("main", "master"):
            if not messagebox.askyesno(
                "Попередження про гілку",
                f"Ви створюєте коміти в гілці '{cur_branch}'.\n\n"
                "GitHub зараховує графіку активності ТІЛЬКИ у гілці за замовчуванням (зазвичай 'main' або 'master').\n\n"
                "Продовжити?"
            ):
                return

        plan = self._get_target_plan()
        if not plan:
            messagebox.showinfo("Інфо", "Немає активних клітинок для комітів.")
            return

        total_commits = sum(cnt for _, cnt in plan)
        if not messagebox.askyesno(
            "Підтвердження створення комітів",
            f"Створити {total_commits} комітів у локальному репозиторії?\n\n"
            f"Репозиторій: {self.target_dir}\n"
            f"Гілка: {cur_branch}\n"
            f"Автор: {name} <{email}>"
        ):
            return

        self._set_git_buttons_enabled(False)
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = total_commits
        self.progress_lbl.config(text=f"0 / {total_commits} (0%)")
        self.progress_frame.pack(fill="x", padx=8, pady=(0, 6))

        def worker():
            try:
                commit_msg = self.commit_msg_var.get().strip() or "chore: update build log ({date})"
                self.log(f"Starting commit generation ({total_commits} commits)...")
                created = self.git_engine.generate_commits(
                    commit_plan=plan,
                    author_name=name,
                    author_email=email,
                    commit_msg_template=commit_msg,
                    progress_cb=lambda cur, tot, msg: self.after(
                        0, lambda: self._update_commit_progress(cur, tot, int((cur / tot) * 100) if tot > 0 else 0, msg)
                    ),
                    log_cb=lambda msg: self.after(0, lambda: self.log(msg))
                )
                self.after(0, lambda: self._finish_commit_progress(created))
            except Exception as e:
                self.after(0, lambda: self._fail_commit_progress(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_push(self):
        branch = self.git_engine.get_current_branch()
        if not messagebox.askyesno("Підтвердження пушу", f"Відправити зміни у віддалений репозиторій origin/{branch}?"):
            return

        self._set_git_buttons_enabled(False)

        def worker():
            try:
                success = self.git_engine.push(log_cb=lambda msg: self.after(0, lambda: self.log(msg)))
                if success:
                    self.after(0, lambda: messagebox.showinfo("Пуш успішний", f"Зміни успішно надіслано в origin/{branch}!\n\nПеревірте ваш профіль GitHub через 5-10 хвилин."))
                else:
                    self.after(0, lambda: messagebox.showerror("Помилка пушу", "Не вдалося виконати пуш. Перевірте лог у консолі."))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Помилка пушу", str(e)))
            finally:
                self.after(0, lambda: self._set_git_buttons_enabled(True))

        threading.Thread(target=worker, daemon=True).start()

    def _run_force_push(self):
        branch = self.git_engine.get_current_branch()
        self._set_git_buttons_enabled(False)

        def worker():
            try:
                self.log("Starting force push to remove art from GitHub...")
                success = self.git_engine.push(force=True, log_cb=lambda msg: self.after(0, lambda: self.log(msg)))
                if success:
                    self.after(0, lambda: messagebox.showinfo("Очищено на GitHub", f"Force push успішно виконано в origin/{branch}!\n\nГрафіку видалено з GitHub."))
                else:
                    self.after(0, lambda: messagebox.showwarning("Force push не вдався", "Перевірте налаштування remote у консолі."))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Помилка", str(e)))
            finally:
                self.after(0, lambda: self._set_git_buttons_enabled(True))

        threading.Thread(target=worker, daemon=True).start()

    def _on_wipe_art(self):
        if not messagebox.askyesno(
            "Очищення історії",
            "Ви дійсно бажаєте відкотити всі створені коміти малюнка до стану перед початком малювання?\n\n"
            "Ця дія безпечно поверне локальний репозиторій до початкового коміту."
        ):
            return

        success = self.git_engine.rollback(log_cb=self.log)
        if success:
            if messagebox.askyesno(
                "Очищено локально",
                "Історію малюнка успішно відкочено локально!\n\n"
                "Бажаєте також зробити force push на GitHub ('git push --force'),\n"
                "щоб негайно стерти графіку і з вашого профілю?"
            ):
                self._run_force_push()
            else:
                messagebox.showinfo("Очищено", "Історію малюнка локально відкочено.\nЗа потреби зробіть 'git push --force' пізніше.")
        else:
            messagebox.showwarning("Увага", "Автоматична точка відкату не знайдена. Перевірте лог.")

    def _on_duplicate_selected_element(self):
        if not self.selected_element_id:
            messagebox.showinfo("Інфо", "Оберіть елемент для копіювання зі списку.")
            return
        self.project.save_state()
        new_el = self.project.duplicate_element(self.selected_element_id)
        if new_el:
            self.selected_element_id = new_el["id"]
            self._refresh_elements_listbox()
            self._load_element_into_inspector(new_el)
            self.grid_widget.render_all()
            self._refresh_stats()
            self.log(f"Duplicated element: {new_el['name']}")

    def _on_copy_year_dialog(self):
        cur_year = self.project.active_year
        dialog = tk.Toplevel(self)
        dialog.title("Копіювання малюнка в інший рік")
        dialog.geometry("380x200")
        dialog.configure(bg=BG_CARD)
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(
            dialog,
            text=f"Скопіювати малюнок з {cur_year} року:",
            bg=BG_CARD,
            fg=TEXT_WHITE,
            font=FONT_HEADING
        ).pack(anchor="w", padx=16, pady=(16, 8))

        row = tk.Frame(dialog, bg=BG_CARD)
        row.pack(fill="x", padx=16, pady=6)

        tk.Label(row, text="Цільовий рік:", bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_REGULAR).pack(side="left")
        target_var = tk.IntVar(value=cur_year + 1)
        spin = tk.Spinbox(row, from_=2008, to=2040, textvariable=target_var, width=8, bg=BG_INPUT, fg=TEXT_WHITE, font=FONT_BOLD)
        spin.pack(side="left", padx=8)

        def do_copy():
            to_y = target_var.get()
            if to_y == cur_year:
                messagebox.showwarning("Увага", "Цільовий рік повинен відрізнятися від поточного.")
                return
            self.project.copy_year_to(cur_year, to_y)
            dialog.destroy()
            self._select_year(to_y)
            self.log(f"Copied art from {cur_year} to {to_y} and switched to {to_y}")
            messagebox.showinfo("Успіх", f"Малюнок успішно скопійовано у {to_y} рік!")

        btn_box = tk.Frame(dialog, bg=BG_CARD)
        btn_box.pack(fill="x", padx=16, pady=(16, 8))

        tk.Button(
            btn_box,
            text="Скопіювати",
            bg=BTN_PRIMARY_BG,
            fg=BTN_PRIMARY_FG,
            activebackground=BTN_PRIMARY_HOVER,
            relief="flat",
            font=FONT_BOLD,
            padx=10,
            pady=4,
            command=do_copy
        ).pack(side="right", padx=4)

        tk.Button(
            btn_box,
            text="Скасувати",
            bg=BG_PANEL,
            fg=TEXT_PRIMARY,
            relief="flat",
            padx=10,
            pady=4,
            command=dialog.destroy
        ).pack(side="right", padx=4)

    def _on_config_multipliers(self):
        dialog = tk.Toplevel(self)
        dialog.title("Вага рівнів (комітів на день)")
        dialog.geometry("440x360")
        dialog.configure(bg=BG_CARD)
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(
            dialog,
            text="Кількість комітів для кожного рівня:",
            bg=BG_CARD,
            fg=TEXT_WHITE,
            font=FONT_HEADING
        ).pack(anchor="w", padx=16, pady=(14, 6))

        tk.Label(
            dialog,
            text="GitHub автоматично розраховує градації зеленого за формулою\n"
                 "відносно найбільш активного дня за рік. Якщо у вас вже є дні\n"
                 "з багатьма комітами, збільшіть кількість для Рівня 4.",
            bg=BG_CARD,
            fg=TEXT_MUTED,
            font=FONT_SMALL,
            justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 10))

        vars_map = {}
        labels = [
            (1, "Рівень 1 (світло-зелений):", LEVEL_COLORS[1]),
            (2, "Рівень 2 (середній зелений):", LEVEL_COLORS[2]),
            (3, "Рівень 3 (темно-зелений):", LEVEL_COLORS[3]),
            (4, "Рівень 4 (найяскравіший):", LEVEL_COLORS[4]),
        ]

        for lvl, name, col in labels:
            row = tk.Frame(dialog, bg=BG_CARD)
            row.pack(fill="x", padx=16, pady=3)

            lbl_box = tk.Label(row, bg=col, width=2, height=1, relief="solid", bd=1)
            lbl_box.pack(side="left", padx=(0, 8))

            tk.Label(row, text=name, bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_REGULAR, width=24, anchor="w").pack(side="left")

            cur_val = self.project.multipliers.get(lvl, lvl * 2)
            v = tk.IntVar(value=cur_val)
            vars_map[lvl] = v

            sp = tk.Spinbox(row, from_=1, to=100, textvariable=v, width=6, bg=BG_INPUT, fg=TEXT_WHITE, font=FONT_BOLD)
            sp.pack(side="left", padx=6)
            tk.Label(row, text="комітів", bg=BG_CARD, fg=TEXT_MUTED, font=FONT_SMALL).pack(side="left")

        def save_multipliers():
            new_m = {lvl: max(1, v.get()) for lvl, v in vars_map.items()}
            new_m[0] = 0
            self.project.set_multipliers(new_m)
            self._refresh_stats()
            self.grid_widget.render_all()
            self.log(f"Updated commit multipliers: {new_m}")
            dialog.destroy()
            messagebox.showinfo("Збережено", "Налаштування ваги рівнів оновлено!")

        btn_box = tk.Frame(dialog, bg=BG_CARD)
        btn_box.pack(fill="x", padx=16, pady=(16, 8))

        tk.Button(
            btn_box,
            text="Зберегти",
            bg=BTN_PRIMARY_BG,
            fg=BTN_PRIMARY_FG,
            activebackground=BTN_PRIMARY_HOVER,
            relief="flat",
            font=FONT_BOLD,
            padx=12,
            pady=4,
            command=save_multipliers
        ).pack(side="right", padx=4)

        tk.Button(
            btn_box,
            text="Скасувати",
            bg=BG_PANEL,
            fg=TEXT_PRIMARY,
            relief="flat",
            padx=10,
            pady=4,
            command=dialog.destroy
        ).pack(side="right", padx=4)

    def _on_export_png(self):
        filetypes = [("PNG Image", "*.png"), ("All Files", "*.*")]
        filepath = filedialog.asksaveasfilename(
            title="Експорт графіка у PNG",
            defaultextension=".png",
            filetypes=filetypes,
            initialfile=f"github_art_{self.project.active_year}.png"
        )
        if filepath:
            try:
                img = export_project_to_image(self.project, self.project.active_year, scale=2)
                img.save(filepath, "PNG")
                self.log(f"Exported PNG image to: {filepath}")
                messagebox.showinfo("Успіх", f"Зображення графіка успішно збережено в:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Помилка експорту", str(e))

    # Project File handling
    def _on_new_file(self):
        if messagebox.askyesno("Новий проект", "Очистити поточне полотно і почати новий проект?"):
            self.project = Project(initial_year=self.project.active_year)
            self.current_filepath = None
            self.selected_element_id = None
            self.grid_widget.project = self.project
            self._refresh_elements_listbox()
            self.grid_widget.render_all()
            self._refresh_stats()
            self.log("Created new empty project.")

    def _on_open_file(self):
        filetypes = [("GrafGit Project", "*.grafgit *.json"), ("All Files", "*.*")]
        filepath = filedialog.askopenfilename(title="Відкрити проект", filetypes=filetypes)
        if filepath:
            try:
                self.project = Project.load_file(filepath)
                self.current_filepath = filepath
                self.selected_element_id = None
                self.grid_widget.project = self.project
                self._rebuild_year_pills()
                self._refresh_elements_listbox()
                self.grid_widget.render_all()
                self._refresh_stats()
                self.log(f"Loaded project: {filepath}")
            except Exception as e:
                messagebox.showerror("Помилка", f"Не вдалося завантажити файл:\n{e}")

    def _on_save_file(self):
        if self.current_filepath:
            try:
                self.project.save_file(self.current_filepath)
                self.log(f"Saved project: {self.current_filepath}")
            except Exception as e:
                messagebox.showerror("Помилка", f"Не вдалося зберегти файл:\n{e}")
        else:
            self._on_save_as_file()

    def _on_save_as_file(self):
        filetypes = [("GrafGit Project", "*.grafgit"), ("JSON", "*.json"), ("All Files", "*.*")]
        filepath = filedialog.asksaveasfilename(
            title="Зберегти проект як",
            defaultextension=".grafgit",
            filetypes=filetypes,
            initialfile=f"art_{self.project.active_year}.grafgit"
        )
        if filepath:
            try:
                self.project.save_file(filepath)
                self.current_filepath = filepath
                self.log(f"Saved project as: {filepath}")
            except Exception as e:
                messagebox.showerror("Помилка", f"Не вдалося зберегти файл:\n{e}")

    def log(self, text: str):
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")

    def _clear_log(self):
        self.log_text.delete("1.0", "end")
