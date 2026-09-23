"""Interactive Tkinter Canvas representing GitHub Contribution Graph with Dynamic Zoom."""

import tkinter as tk
from datetime import date
from typing import Callable, Dict, Optional, Tuple

from grafgit.core.calendar import GITHUB_LABELS, ROW_NAMES, coords_to_date, get_year_calendar_info
from grafgit.core.project import Project
from grafgit.ui.theme import (
    BG_ROOT,
    CELL_DISABLED_BG,
    CELL_DISABLED_BORDER,
    FONT_REGULAR,
    FONT_SMALL,
    LEVEL_BORDERS,
    LEVEL_COLORS,
    TEXT_MUTED,
)


class CanvasGrid(tk.Canvas):
    """53x7 Interactive Grid simulating GitHub Contribution Graph with Zoom support."""

    DEFAULT_CELL_SIZE = 15
    DEFAULT_CELL_GAP = 3

    def __init__(
        self,
        master,
        project: Project,
        cell_size: int = DEFAULT_CELL_SIZE,
        on_change: Optional[Callable[[], None]] = None,
        on_hover: Optional[Callable[[Optional[date], str, int, int, bool], None]] = None,
        **kwargs
    ):
        self.project = project
        self.on_change = on_change
        self.on_hover = on_hover

        self.cell_size = max(10, min(28, cell_size))
        self.cell_gap = max(2, int(round(self.cell_size * 0.22)))

        self.left_margin = max(34, int(self.cell_size * 2.6))
        self.top_margin = max(22, int(self.cell_size * 1.7))
        self.bottom_margin = 10
        self.right_margin = 15

        self.active_brush = 4  # Default Level 4 (Bright Green)
        self.is_drawing = False
        self.stroke_modified = False
        self.last_hover_cell: Optional[Tuple[int, int]] = None

        dims = self._calc_dimensions()

        super().__init__(
            master,
            width=dims[0],
            height=dims[1],
            bg=BG_ROOT,
            highlightthickness=0,
            scrollregion=(0, 0, dims[0], dims[1]),
            **kwargs
        )

        # Cache of canvas item IDs: (col, row) -> rect_id
        self.cell_items: Dict[Tuple[int, int], int] = {}
        self.hover_rect_id = None

        # Bindings
        self.bind("<Button-1>", self._on_b1_down)
        self.bind("<B1-Motion>", self._on_b1_motion)
        self.bind("<ButtonRelease-1>", self._on_mouse_up)

        self.bind("<Button-3>", self._on_b3_down)
        self.bind("<B3-Motion>", self._on_b3_motion)
        self.bind("<ButtonRelease-3>", self._on_mouse_up)

        self.bind("<Motion>", self._on_mouse_move)
        self.bind("<Leave>", self._on_mouse_leave)

        self.render_all()

    def _calc_dimensions(self) -> Tuple[int, int]:
        cal = get_year_calendar_info(self.project.active_year)
        total_cols = cal["total_cols"]
        width = self.left_margin + total_cols * (self.cell_size + self.cell_gap) + self.right_margin
        height = self.top_margin + 7 * (self.cell_size + self.cell_gap) + self.bottom_margin
        return width, height

    def set_cell_size(self, new_size: int):
        """Changes the scale/zoom of the canvas grid dynamically."""
        self.cell_size = max(10, min(28, new_size))
        self.cell_gap = max(2, int(round(self.cell_size * 0.22)))
        self.left_margin = max(34, int(self.cell_size * 2.6))
        self.top_margin = max(22, int(self.cell_size * 1.7))

        w, h = self._calc_dimensions()
        self.config(width=w, height=h, scrollregion=(0, 0, w, h))
        self.render_all()

    def set_active_brush(self, level: int):
        self.active_brush = max(0, min(4, level))

    def _get_cell_at_xy(self, x: int, y: int) -> Optional[Tuple[int, int]]:
        """Maps canvas pixel (x, y) to grid (col, row)."""
        c = (x - self.left_margin) // (self.cell_size + self.cell_gap)
        r = (y - self.top_margin) // (self.cell_size + self.cell_gap)

        cal = get_year_calendar_info(self.project.active_year)
        if 0 <= c < cal["total_cols"] and 0 <= r < 7:
            return int(c), int(r)
        return None

    def render_all(self):
        """Full redraw of labels and all grid cells."""
        self.delete("all")
        self.cell_items.clear()

        cal = get_year_calendar_info(self.project.active_year)
        total_cols = cal["total_cols"]

        font_to_use = FONT_REGULAR if self.cell_size >= 19 else FONT_SMALL

        # Draw Month Headers
        last_drawn_col = -5
        for month_name, col in cal["month_positions"]:
            # Ensure month labels don't visually overlap
            if col - last_drawn_col >= 3 and col < total_cols:
                x = self.left_margin + col * (self.cell_size + self.cell_gap)
                self.create_text(
                    x, self.top_margin - 12,
                    text=month_name,
                    anchor="w",
                    fill=TEXT_MUTED,
                    font=font_to_use
                )
                last_drawn_col = col

        # Draw Day Labels (Mon, Wed, Fri)
        for row_idx, label in GITHUB_LABELS.items():
            y = self.top_margin + row_idx * (self.cell_size + self.cell_gap) + (self.cell_size // 2)
            self.create_text(
                self.left_margin - 8, y,
                text=label,
                anchor="e",
                fill=TEXT_MUTED,
                font=font_to_use
            )

        # Draw Grid Cells
        for c in range(total_cols):
            for r in range(7):
                x1 = self.left_margin + c * (self.cell_size + self.cell_gap)
                y1 = self.top_margin + r * (self.cell_size + self.cell_gap)
                x2 = x1 + self.cell_size
                y2 = y1 + self.cell_size

                _, in_year = coords_to_date(self.project.active_year, c, r)

                if in_year:
                    lvl = self.project.get_pixel(c, r)
                    fill_c = LEVEL_COLORS[lvl]
                    border_c = LEVEL_BORDERS[lvl]
                else:
                    fill_c = CELL_DISABLED_BG
                    border_c = CELL_DISABLED_BORDER

                rect_id = self.create_rectangle(
                    x1, y1, x2, y2,
                    fill=fill_c,
                    outline=border_c,
                    width=1
                )
                self.cell_items[(c, r)] = rect_id

        # Create hover indicator item (initially hidden)
        self.hover_rect_id = self.create_rectangle(
            0, 0, 0, 0,
            outline="#ffffff",
            width=1.5,
            state="hidden"
        )

    def update_cell_color(self, col: int, row: int):
        """Fast update of a single cell's visual state."""
        rect_id = self.cell_items.get((col, row))
        if not rect_id:
            return

        _, in_year = coords_to_date(self.project.active_year, col, row)
        if in_year:
            lvl = self.project.get_pixel(col, row)
            fill_c = LEVEL_COLORS[lvl]
            border_c = LEVEL_BORDERS[lvl]
        else:
            fill_c = CELL_DISABLED_BG
            border_c = CELL_DISABLED_BORDER

        self.itemconfig(rect_id, fill=fill_c, outline=border_c)

    def _paint_cell(self, col: int, row: int, level: int):
        if self.project.set_pixel(col, row, level):
            self.stroke_modified = True
            self.update_cell_color(col, row)
            if self.on_change:
                self.on_change()

    def _on_b1_down(self, event):
        self.is_drawing = True
        self.project.save_state()
        self.stroke_modified = False
        coords = self._get_cell_at_xy(event.x, event.y)
        if coords:
            self._paint_cell(coords[0], coords[1], self.active_brush)

    def _on_b1_motion(self, event):
        if not self.is_drawing:
            return
        coords = self._get_cell_at_xy(event.x, event.y)
        if coords:
            self._paint_cell(coords[0], coords[1], self.active_brush)
        self._on_mouse_move(event)

    def _on_b3_down(self, event):
        """Right-click eraser."""
        self.is_drawing = True
        self.project.save_state()
        self.stroke_modified = False
        coords = self._get_cell_at_xy(event.x, event.y)
        if coords:
            self._paint_cell(coords[0], coords[1], 0)

    def _on_b3_motion(self, event):
        if not self.is_drawing:
            return
        coords = self._get_cell_at_xy(event.x, event.y)
        if coords:
            self._paint_cell(coords[0], coords[1], 0)
        self._on_mouse_move(event)

    def _on_mouse_up(self, event):
        self.is_drawing = False

    def _on_mouse_move(self, event):
        coords = self._get_cell_at_xy(event.x, event.y)
        if coords != self.last_hover_cell:
            self.last_hover_cell = coords

            if coords:
                c, r = coords
                x1 = self.left_margin + c * (self.cell_size + self.cell_gap) - 1
                y1 = self.top_margin + r * (self.cell_size + self.cell_gap) - 1
                x2 = x1 + self.cell_size + 2
                y2 = y1 + self.cell_size + 2

                self.coords(self.hover_rect_id, x1, y1, x2, y2)
                self.itemconfig(self.hover_rect_id, state="normal")
                self.tag_raise(self.hover_rect_id)

                d, in_year = coords_to_date(self.project.active_year, c, r)
                lvl = self.project.get_pixel(c, r) if in_year else 0
                commits = self.project.multipliers.get(lvl, 0)
                weekday_name = ROW_NAMES[r]

                if self.on_hover:
                    self.on_hover(d, weekday_name, commits, lvl, in_year)
            else:
                self.itemconfig(self.hover_rect_id, state="hidden")
                if self.on_hover:
                    self.on_hover(None, "", 0, 0, False)

    def _on_mouse_leave(self, event):
        self.last_hover_cell = None
        if self.hover_rect_id:
            self.itemconfig(self.hover_rect_id, state="hidden")
        if self.on_hover:
            self.on_hover(None, "", 0, 0, False)
