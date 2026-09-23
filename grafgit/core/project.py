"""Project state management, multi-element composition, multi-year support, and undo/redo."""

import copy
import json
import os
import uuid
from datetime import date
from typing import Dict, List, Optional, Tuple

from grafgit.core.calendar import coords_to_date, get_year_calendar_info
from grafgit.core.font7x5 import render_text
from grafgit.core.image_proc import convert_image_to_grid


class Project:
    """Manages contribution art canvas state across multiple years with element composition."""

    DEFAULT_MULTIPLIERS = {
        0: 0,
        1: 1,
        2: 3,
        3: 6,
        4: 10,
    }

    def __init__(self, initial_year: int = 2024, year: Optional[int] = None):
        self.active_year = year if year is not None else initial_year
        self.multipliers = dict(self.DEFAULT_MULTIPLIERS)

        # year -> list of element dictionaries
        self.elements: Dict[int, List[dict]] = {self.active_year: []}
        # year -> dict of freehand drawn pixels (col, row) -> level
        self.freehand_grids: Dict[int, Dict[Tuple[int, int], int]] = {self.active_year: {}}
        # year -> cached composed grid (col, row) -> level
        self.year_grids: Dict[int, Dict[Tuple[int, int], int]] = {self.active_year: {}}

        # Undo / Redo history: stores snapshots of (year, elements_dict, freehand_dict)
        self.history: List[Tuple[int, dict, dict]] = []
        self.redo_stack: List[Tuple[int, dict, dict]] = []

        self._refresh_calendar()
        self.recompute_grid()

    def _refresh_calendar(self):
        self.cal_info = get_year_calendar_info(self.active_year)
        self.total_cols = self.cal_info["total_cols"]

    @property
    def grid(self) -> Dict[Tuple[int, int], int]:
        """Returns the active year's composed grid."""
        if self.active_year not in self.year_grids:
            self.recompute_grid(self.active_year)
        return self.year_grids[self.active_year]

    def set_active_year(self, new_year: int):
        """Switches the active year while preserving all other years' drawings and elements."""
        if new_year != self.active_year:
            self.active_year = new_year
            if self.active_year not in self.elements:
                self.elements[self.active_year] = []
            if self.active_year not in self.freehand_grids:
                self.freehand_grids[self.active_year] = {}
            self._refresh_calendar()
            self.recompute_grid(new_year)

    def save_state(self):
        """Saves a deep copy of elements and freehand grids to history for undo."""
        snapshot = (
            self.active_year,
            copy.deepcopy(self.elements),
            copy.deepcopy(self.freehand_grids)
        )
        self.history.append(snapshot)
        if len(self.history) > 50:
            self.history.pop(0)
        self.redo_stack.clear()

    def undo(self) -> bool:
        if not self.history:
            return False
        # Save current to redo stack
        self.redo_stack.append((
            self.active_year,
            copy.deepcopy(self.elements),
            copy.deepcopy(self.freehand_grids)
        ))
        year, prev_elements, prev_freehand = self.history.pop()
        self.elements = prev_elements
        self.freehand_grids = prev_freehand
        self.set_active_year(year)
        self.recompute_grid(year)
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        self.history.append((
            self.active_year,
            copy.deepcopy(self.elements),
            copy.deepcopy(self.freehand_grids)
        ))
        year, next_elements, next_freehand = self.redo_stack.pop()
        self.elements = next_elements
        self.freehand_grids = next_freehand
        self.set_active_year(year)
        self.recompute_grid(year)
        return True

    # ---------------- Element Management ----------------

    def add_image_element(
        self,
        filepath: str,
        x: int = 0,
        y: int = 0,
        height: int = 7,
        sensitivity: float = 1.0,
        invert: bool = False,
        autocrop: bool = True,
        year: Optional[int] = None
    ) -> dict:
        """Adds an image element to the canvas and recomputes the grid."""
        target_year = year if year is not None else self.active_year
        if target_year not in self.elements:
            self.elements[target_year] = []

        filename = os.path.basename(filepath)
        el = {
            "id": str(uuid.uuid4())[:8],
            "type": "image",
            "name": f"Зображення: {filename}",
            "filepath": filepath,
            "x": max(-35, min(55, x)),
            "y": max(-25, min(25, y)),
            "height": max(1, min(35, height)),
            "sensitivity": sensitivity,
            "invert": invert,
            "autocrop": autocrop,
            "visible": True,
        }
        self.elements[target_year].append(el)
        self.recompute_grid(target_year)
        return el

    def add_text_element(
        self,
        text: str = "CODE",
        x: int = 2,
        y: int = 0,
        level: int = 4,
        font_size: str = "7px",
        line2: str = "",
        year: Optional[int] = None
    ) -> dict:
        """Adds a text element to the canvas and recomputes the grid."""
        target_year = year if year is not None else self.active_year
        if target_year not in self.elements:
            self.elements[target_year] = []

        display_name = f"Текст: «{text}»" if not line2 else f"Текст: «{text} / {line2}»"
        el = {
            "id": str(uuid.uuid4())[:8],
            "type": "text",
            "name": display_name,
            "text": text,
            "line2": line2,
            "font_size": font_size,
            "x": max(-35, min(55, x)),
            "y": max(-25, min(25, y)),
            "level": max(1, min(4, level)),
            "visible": True,
        }
        self.elements[target_year].append(el)
        self.recompute_grid(target_year)
        return el

    def add_template_element(
        self,
        template_key: str = "heart",
        x: int = 20,
        y: int = 0,
        level: int = 4,
        year: Optional[int] = None
    ) -> dict:
        """Adds a standard template element with dynamic position and level."""
        target_year = year if year is not None else self.active_year
        if target_year not in self.elements:
            self.elements[target_year] = []

        tmpl_names = {
            "heart": "Серце",
            "check": "Галочка",
            "wave": "Хвиля",
            "checkerboard": "Шахівниця",
            "invader": "Загарбник",
        }
        title = tmpl_names.get(template_key, template_key.capitalize())
        el = {
            "id": str(uuid.uuid4())[:8],
            "type": "template",
            "template_key": template_key,
            "name": f"Шаблон: {title}",
            "x": max(-35, min(55, x)),
            "y": max(-25, min(25, y)),
            "level": max(1, min(4, level)),
            "visible": True,
        }
        self.elements[target_year].append(el)
        self.recompute_grid(target_year)
        return el

    def update_element(self, element_id: str, updates: dict, year: Optional[int] = None):
        """Updates element attributes and recomputes grid in real-time."""
        target_year = year if year is not None else self.active_year
        for el in self.elements.get(target_year, []):
            if el["id"] == element_id:
                if "x" in updates:
                    updates["x"] = max(-35, min(55, int(updates["x"])))
                if "y" in updates:
                    updates["y"] = max(-25, min(25, int(updates["y"])))
                if "height" in updates:
                    updates["height"] = max(1, min(35, int(updates["height"])))
                el.update(updates)
                if el["type"] == "text":
                    l2 = el.get("line2", "")
                    t = el.get("text", "")
                    el["name"] = f"Текст: «{t} / {l2}»" if l2 else f"Текст: «{t}»"
                elif el["type"] == "image" and "filepath" in updates:
                    el["name"] = f"Зображення: {os.path.basename(el['filepath'])}"
                elif el["type"] == "template" and "template_key" in updates:
                    tmpl_names = {
                        "heart": "Серце",
                        "check": "Галочка",
                        "wave": "Хвиля",
                        "checkerboard": "Шахівниця",
                        "invader": "Загарбник",
                    }
                    title = tmpl_names.get(updates["template_key"], updates["template_key"].capitalize())
                    el["name"] = f"Шаблон: {title}"
                break
        self.recompute_grid(target_year)

    def duplicate_element(self, element_id: str, year: Optional[int] = None) -> Optional[dict]:
        """Duplicates an element with a small X offset."""
        target_year = year if year is not None else self.active_year
        elements = self.elements.get(target_year, [])
        for el in elements:
            if el["id"] == element_id:
                new_el = copy.deepcopy(el)
                new_el["id"] = str(uuid.uuid4())[:8]
                new_el["x"] = min(52, new_el.get("x", 0) + 2)
                new_el["name"] = f"{el.get('name', 'Елемент')} (копія)"
                elements.append(new_el)
                self.recompute_grid(target_year)
                return new_el
        return None

    def copy_year_to(self, from_year: int, to_year: int):
        """Copies elements and freehand drawing from one year to another."""
        self.save_state()
        if from_year not in self.elements:
            self.elements[from_year] = []
        if from_year not in self.freehand_grids:
            self.freehand_grids[from_year] = {}

        # Deep copy elements and re-assign new IDs
        new_elements = []
        for el in self.elements[from_year]:
            cloned = copy.deepcopy(el)
            cloned["id"] = str(uuid.uuid4())[:8]
            new_elements.append(cloned)

        self.elements[to_year] = new_elements
        self.freehand_grids[to_year] = copy.deepcopy(self.freehand_grids[from_year])
        self.recompute_grid(to_year)

    def set_multipliers(self, multipliers: Dict[int, int]):
        """Sets custom commit multipliers per brightness level."""
        self.save_state()
        for k, v in multipliers.items():
            self.multipliers[int(k)] = max(0, int(v))

    def remove_element(self, element_id: str, year: Optional[int] = None):
        """Removes an element from the canvas."""
        target_year = year if year is not None else self.active_year
        if target_year in self.elements:
            self.elements[target_year] = [
                el for el in self.elements[target_year] if el["id"] != element_id
            ]
            self.recompute_grid(target_year)

    def get_elements(self, year: Optional[int] = None) -> List[dict]:
        target_year = year if year is not None else self.active_year
        return self.elements.get(target_year, [])

    def recompute_grid(self, year: Optional[int] = None):
        """Composes freehand pixels and all active elements into the final year grid."""
        yr = year if year is not None else self.active_year
        cal = get_year_calendar_info(yr)
        total_cols = cal["total_cols"]

        # Start with a copy of freehand drawings
        freehand = self.freehand_grids.get(yr, {})
        composed: Dict[Tuple[int, int], int] = dict(freehand)

        # Render and stamp each visible element in order
        for el in self.elements.get(yr, []):
            if not el.get("visible", True):
                continue

            matrix = self._render_element_matrix(el, total_cols)
            start_x = el.get("x", 0)
            start_y = el.get("y", 0)

            for c_idx, col_data in enumerate(matrix):
                c = start_x + c_idx
                if 0 <= c < total_cols:
                    for r_idx, val in enumerate(col_data):
                        r = start_y + r_idx
                        if 0 <= r < 7:
                            _, in_year = coords_to_date(yr, c, r)
                            if in_year and val > 0:
                                composed[(c, r)] = val

        self.year_grids[yr] = composed

    def _render_element_matrix(self, el: dict, total_cols: int) -> List[List[int]]:
        """Renders an element to a 2D column matrix."""
        el_type = el.get("type")
        start_x = el.get("x", 0)
        max_w = max(1, total_cols - start_x)

        if el_type == "image":
            filepath = el.get("filepath", "")
            if not filepath or not os.path.exists(filepath):
                return []
            try:
                return convert_image_to_grid(
                    filepath,
                    invert=el.get("invert", False),
                    sensitivity=el.get("sensitivity", 1.0),
                    target_height=el.get("height", 7),
                    max_width=150,
                    autocrop=el.get("autocrop", True)
                )
            except Exception:
                return []

        elif el_type == "text":
            text = el.get("text", "")
            level = el.get("level", 4)
            font_size = el.get("font_size", "7px")
            line2 = el.get("line2", "")
            try:
                return render_text(text, level=level, font_size=font_size, line2=line2)
            except Exception:
                return []

        elif el_type == "template":
            tmpl_key = el.get("template_key", "heart")
            level = el.get("level", 4)
            return self.get_template_matrix(tmpl_key, total_cols=max_w, target_level=level)

        return []

    @staticmethod
    def get_template_matrix(name: str, total_cols: int = 53, target_level: int = 4) -> List[List[int]]:
        import math
        base: List[List[int]] = []
        if name == "heart":
            base = [
                [0, 2, 3, 3, 2, 0, 0],
                [2, 3, 4, 4, 3, 2, 0],
                [3, 4, 4, 4, 4, 3, 2],
                [0, 3, 4, 4, 4, 4, 3],
                [3, 4, 4, 4, 4, 3, 2],
                [2, 3, 4, 4, 3, 2, 0],
                [0, 2, 3, 3, 2, 0, 0],
            ]
        elif name == "check":
            base = [
                [0, 0, 0, 0, 3, 0, 0],
                [0, 0, 0, 0, 0, 4, 0],
                [0, 0, 0, 0, 3, 0, 0],
                [0, 0, 0, 3, 0, 0, 0],
                [0, 0, 4, 0, 0, 0, 0],
                [0, 3, 0, 0, 0, 0, 0],
            ]
        elif name == "wave":
            for c in range(min(53, total_cols)):
                col_data = [0] * 7
                r = int(round(3 + 2.5 * math.sin(c * 0.4)))
                if 0 <= r < 7:
                    col_data[r] = 4
                    if r > 0:
                        col_data[r - 1] = 2
                    if r < 6:
                        col_data[r + 1] = 2
                base.append(col_data)
        elif name == "checkerboard":
            for c in range(min(53, total_cols)):
                col_data = [(2 if (c + r) % 2 == 0 else 0) for r in range(7)]
                base.append(col_data)
        elif name in ("invader", "alien"):
            # 11x7 Space Invader (exact 7-row fit for GitHub graph!)
            base = [
                [0, 0, 0, 4, 4, 4, 0],
                [0, 0, 4, 4, 0, 0, 0],
                [4, 4, 4, 4, 4, 4, 0],
                [0, 4, 0, 4, 4, 0, 4],
                [0, 4, 4, 4, 4, 0, 4],
                [0, 4, 4, 4, 4, 0, 0],
                [0, 4, 4, 4, 4, 0, 4],
                [0, 4, 0, 4, 4, 0, 4],
                [4, 4, 4, 4, 4, 4, 0],
                [0, 0, 4, 4, 0, 0, 0],
                [0, 0, 0, 4, 4, 4, 0],
            ]

        if target_level != 4 and base:
            scaled: List[List[int]] = []
            for col in base:
                scaled_col = [
                    min(target_level, max(1, int(round(v * target_level / 4.0)))) if v > 0 else 0
                    for v in col
                ]
                scaled.append(scaled_col)
            return scaled
        return base

    # ---------------- Freehand Brush & Pixel Access ----------------

    def set_pixel(self, col: int, row: int, level: int, year: Optional[int] = None) -> bool:
        """Sets pixel value in freehand grid and updates composed grid."""
        target_year = year if year is not None else self.active_year
        if target_year not in self.freehand_grids:
            self.freehand_grids[target_year] = {}

        cal = get_year_calendar_info(target_year)
        if not (0 <= col < cal["total_cols"] and 0 <= row < 7):
            return False

        _, in_year = coords_to_date(target_year, col, row)
        if not in_year:
            return False

        freehand = self.freehand_grids[target_year]
        current = freehand.get((col, row), 0)
        if current != level:
            if level == 0:
                freehand.pop((col, row), None)
            else:
                freehand[(col, row)] = level
            self.recompute_grid(target_year)
            return True
        return False

    def get_pixel(self, col: int, row: int, year: Optional[int] = None) -> int:
        target_year = year if year is not None else self.active_year
        if target_year not in self.year_grids:
            self.recompute_grid(target_year)
        return self.year_grids.get(target_year, {}).get((col, row), 0)

    def clear(self, year: Optional[int] = None):
        """Clears active year (elements and freehand pixels)."""
        target_year = year if year is not None else self.active_year
        self.save_state()
        if target_year in self.elements:
            self.elements[target_year].clear()
        if target_year in self.freehand_grids:
            self.freehand_grids[target_year].clear()
        if target_year in self.year_grids:
            self.year_grids[target_year].clear()
        self.recompute_grid(target_year)

    def clear_all_years(self):
        self.save_state()
        self.elements = {self.active_year: []}
        self.freehand_grids = {self.active_year: {}}
        self.year_grids = {self.active_year: {}}
        self.recompute_grid(self.active_year)

    def invert(self):
        """Inverts freehand pixels in the active year."""
        self.save_state()
        cal = get_year_calendar_info(self.active_year)
        new_freehand = {}
        for c in range(cal["total_cols"]):
            for r in range(7):
                _, in_year = coords_to_date(self.active_year, c, r)
                if in_year:
                    lvl = self.get_pixel(c, r)
                    new_lvl = 4 - lvl
                    if new_lvl > 0:
                        new_freehand[(c, r)] = new_lvl
        self.freehand_grids[self.active_year] = new_freehand
        self.recompute_grid(self.active_year)

    def shift(self, dx: int = 0, dy: int = 0):
        """Shifts active year elements and freehand grid horizontally (dx) and vertically (dy)."""
        if dx == 0 and dy == 0:
            return
        self.save_state()
        cal = get_year_calendar_info(self.active_year)

        # Shift elements
        for el in self.elements.get(self.active_year, []):
            el["x"] = max(0, min(cal["total_cols"] - 1, el.get("x", 0) + dx))
            el["y"] = max(0, min(6, el.get("y", 0) + dy))

        # Shift freehand pixels
        new_freehand = {}
        for (c, r), lvl in self.freehand_grids.get(self.active_year, {}).items():
            nc = c + dx
            nr = r + dy
            if 0 <= nc < cal["total_cols"] and 0 <= nr < 7:
                _, in_year = coords_to_date(self.active_year, nc, nr)
                if in_year:
                    new_freehand[(nc, nr)] = lvl
        self.freehand_grids[self.active_year] = new_freehand
        self.recompute_grid(self.active_year)

    def stamp_matrix(
        self,
        matrix: List[List[int]],
        start_col: int = 0,
        start_row: int = 0,
        overwrite_zeros: bool = False
    ):
        """Stamps a 2D matrix directly into freehand pixels."""
        self.save_state()
        cal = get_year_calendar_info(self.active_year)
        freehand = self.freehand_grids.setdefault(self.active_year, {})

        for c_idx, col_data in enumerate(matrix):
            c = start_col + c_idx
            if 0 <= c < cal["total_cols"]:
                for r_idx, val in enumerate(col_data):
                    r = start_row + r_idx
                    if 0 <= r < 7:
                        _, in_year = coords_to_date(self.active_year, c, r)
                        if in_year:
                            if val > 0 or overwrite_zeros:
                                if val > 0:
                                    freehand[(c, r)] = val
                                else:
                                    freehand.pop((c, r), None)
        self.recompute_grid(self.active_year)

    def load_existing_contributions(self, year: int, date_counts: Dict[date, int]):
        """Populates freehand grid from scanned Git contributions for a specific year."""
        self.save_state()
        if year not in self.freehand_grids:
            self.freehand_grids[year] = {}
        if year not in self.elements:
            self.elements[year] = []

        freehand = self.freehand_grids[year]
        freehand.clear()

        max_commits = max(date_counts.values()) if date_counts else 1

        for d, count in date_counts.items():
            if d.year != year:
                continue
            from grafgit.core.calendar import date_to_coords
            c, r = date_to_coords(d)

            if count <= 0:
                lvl = 0
            elif count == 1:
                lvl = 1
            elif count <= max(2, max_commits // 4):
                lvl = 1
            elif count <= max(4, max_commits // 2):
                lvl = 2
            elif count <= max(8, (3 * max_commits) // 4):
                lvl = 3
            else:
                lvl = 4

            if lvl > 0:
                freehand[(c, r)] = lvl

        self.recompute_grid(year)

    def get_stats(self, year: Optional[int] = None) -> dict:
        target_year = year if year is not None else self.active_year
        if target_year not in self.year_grids:
            self.recompute_grid(target_year)

        grid = self.year_grids.get(target_year, {})
        cal = get_year_calendar_info(target_year)

        total_commits = 0
        active_days = 0
        level_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}

        for c in range(cal["total_cols"]):
            for r in range(7):
                _, in_year = coords_to_date(target_year, c, r)
                if in_year:
                    lvl = grid.get((c, r), 0)
                    level_counts[lvl] += 1
                    if lvl > 0:
                        active_days += 1
                        total_commits += self.multipliers.get(lvl, 1)

        return {
            "year": target_year,
            "total_commits": total_commits,
            "active_days": active_days,
            "level_counts": level_counts,
        }

    def get_commit_plan(self, year: Optional[int] = None) -> List[Tuple[date, int]]:
        """Returns sorted list of (date, commit_count) for the year (or all years if year=None)."""
        years_to_process = [year] if year is not None else sorted(
            set(list(self.year_grids.keys()) + list(self.elements.keys()) + list(self.freehand_grids.keys()))
        )
        plan: List[Tuple[date, int]] = []

        for yr in years_to_process:
            self.recompute_grid(yr)
            grid = self.year_grids.get(yr, {})
            cal = get_year_calendar_info(yr)
            for c in range(cal["total_cols"]):
                for r in range(7):
                    d, in_year = coords_to_date(yr, c, r)
                    if in_year:
                        lvl = grid.get((c, r), 0)
                        if lvl > 0:
                            commits = self.multipliers.get(lvl, 1)
                            if commits > 0:
                                plan.append((d, commits))

        plan.sort(key=lambda x: x[0])
        return plan

    def to_dict(self) -> dict:
        years_pixels = {}
        years_elements = {}

        all_years = set(list(self.year_grids.keys()) + list(self.elements.keys()) + list(self.freehand_grids.keys()))
        for yr in all_years:
            fh = self.freehand_grids.get(yr, {})
            if fh:
                years_pixels[str(yr)] = {f"{c},{r}": lvl for (c, r), lvl in fh.items()}
            els = self.elements.get(yr, [])
            if els:
                years_elements[str(yr)] = els

        return {
            "version": 3,
            "active_year": self.active_year,
            "multipliers": self.multipliers,
            "freehand": years_pixels,
            "elements": years_elements,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        active_year = data.get("active_year", data.get("year", 2024))
        proj = cls(initial_year=active_year)
        if "multipliers" in data:
            proj.multipliers = {int(k): int(v) for k, v in data["multipliers"].items()}

        proj.elements.clear()
        proj.freehand_grids.clear()

        # Load elements if present (v3)
        if "elements" in data:
            for yr_str, els in data["elements"].items():
                proj.elements[int(yr_str)] = els

        # Load freehand pixels
        pixels_source = data.get("freehand", data.get("years", {}))
        if pixels_source:
            for yr_str, pixels in pixels_source.items():
                yr = int(yr_str)
                proj.freehand_grids[yr] = {}
                for k, v in pixels.items():
                    parts = k.split(",")
                    if len(parts) == 2:
                        proj.freehand_grids[yr][(int(parts[0]), int(parts[1]))] = int(v)
        elif "pixels" in data:
            # v1 backwards compatibility
            proj.freehand_grids[active_year] = {}
            for k, v in data["pixels"].items():
                parts = k.split(",")
                if len(parts) == 2:
                    proj.freehand_grids[active_year][(int(parts[0]), int(parts[1]))] = int(v)

        proj._refresh_calendar()
        proj.recompute_grid(active_year)
        return proj

    def save_file(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_file(cls, filepath: str) -> "Project":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
