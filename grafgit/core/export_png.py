"""Export GitHub Contribution Graph canvas to a high-resolution PNG image."""

from datetime import date
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

from grafgit.core.calendar import GITHUB_LABELS, coords_to_date, get_year_calendar_info
from grafgit.core.project import Project
from grafgit.ui.theme import (
    BG_ROOT,
    CELL_DISABLED_BG,
    CELL_DISABLED_BORDER,
    LEVEL_BORDERS,
    LEVEL_COLORS,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_WHITE,
)


def export_project_to_image(project: Project, year: Optional[int] = None, scale: int = 2) -> Image.Image:
    """Renders the contribution graph for a given year to a PIL Image.

    Args:
        project: Project instance
        year: Target year (defaults to project.active_year)
        scale: Integer scale multiplier for high-res output (default: 2 for 2x crispness)

    Returns:
        PIL Image object
    """
    target_year = year if year is not None else project.active_year
    cal = get_year_calendar_info(target_year)
    total_cols = cal["total_cols"]

    # Base metrics at 1x
    cell_size = 12
    cell_gap = 3
    left_margin = 44
    right_margin = 24
    top_margin = 54
    bottom_margin = 38

    w_1x = left_margin + total_cols * (cell_size + cell_gap) + right_margin
    h_1x = top_margin + 7 * (cell_size + cell_gap) + bottom_margin

    # Scaled metrics
    width = w_1x * scale
    height = h_1x * scale
    cs = cell_size * scale
    cg = cell_gap * scale
    lm = left_margin * scale
    tm = top_margin * scale

    img = Image.new("RGB", (width, height), color=BG_ROOT)
    draw = ImageDraw.Draw(img)

    # Try to load a nice font, or use default
    font_small = None
    font_bold = None
    try:
        font_small = ImageFont.truetype("segoeui.ttf", 10 * scale)
        font_bold = ImageFont.truetype("segoeuib.ttf", 12 * scale)
    except Exception:
        font_small = ImageFont.load_default()
        font_bold = ImageFont.load_default()

    # Draw Title & Stats
    stats = project.get_stats(target_year)
    total_commits = stats["total_commits"]
    active_days = stats["active_days"]
    title_text = f"{total_commits} contributions in {target_year}"
    if active_days > 0:
        title_text += f"  ({active_days} active days)"

    draw.text((lm, 16 * scale), title_text, fill=TEXT_WHITE, font=font_bold)

    # Draw Month Labels
    last_drawn_col = -5
    for month_name, col in cal["month_positions"]:
        if col - last_drawn_col >= 3 and col < total_cols:
            x = lm + col * (cs + cg)
            draw.text((x, tm - 18 * scale), month_name, fill=TEXT_MUTED, font=font_small)
            last_drawn_col = col

    # Draw Day Labels (Mon, Wed, Fri)
    for row_idx, label in GITHUB_LABELS.items():
        y = tm + row_idx * (cs + cg) + (cs // 4)
        draw.text((lm - 30 * scale, y), label, fill=TEXT_MUTED, font=font_small)

    # Draw Cells
    grid = project.year_grids.get(target_year, {})
    for c in range(total_cols):
        for r in range(7):
            x1 = lm + c * (cs + cg)
            y1 = tm + r * (cs + cg)
            x2 = x1 + cs
            y2 = y1 + cs

            _, in_year = coords_to_date(target_year, c, r)

            if in_year:
                lvl = grid.get((c, r), 0)
                fill_c = LEVEL_COLORS[lvl]
                border_c = LEVEL_BORDERS[lvl]
            else:
                fill_c = CELL_DISABLED_BG
                border_c = CELL_DISABLED_BORDER

            # Draw cell rectangle
            draw.rectangle([x1, y1, x2, y2], fill=fill_c, outline=border_c, width=max(1, scale))

    # Draw Legend at bottom right
    legend_y = height - 24 * scale
    legend_right = width - right_margin * scale
    legend_box_size = 10 * scale
    legend_gap = 3 * scale

    draw.text((legend_right - 140 * scale, legend_y), "Less", fill=TEXT_MUTED, font=font_small)

    cur_x = legend_right - 110 * scale
    for lvl in range(5):
        draw.rectangle(
            [cur_x, legend_y + 1 * scale, cur_x + legend_box_size, legend_y + 1 * scale + legend_box_size],
            fill=LEVEL_COLORS[lvl],
            outline=LEVEL_BORDERS[lvl],
            width=1 * scale
        )
        cur_x += legend_box_size + legend_gap

    draw.text((cur_x + 4 * scale, legend_y), "More", fill=TEXT_MUTED, font=font_small)

    # Brand watermark at bottom left
    draw.text((lm, legend_y), "GrafGit", fill="#30363d", font=font_small)

    return img
