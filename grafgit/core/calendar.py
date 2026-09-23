"""GitHub Contribution Calendar geometry and date calculations.

GitHub Contribution Graph layout:
- 7 rows: Sunday (0) to Saturday (6).
- 53 to 54 columns (weeks 0 to 52/53).
- Week 0 starts on the Sunday of or preceding January 1st.
- Days outside the selected year are inactive/disabled.
"""

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple


def get_sunday_weekday(d: date) -> int:
    """Return day of week where Sunday=0, Monday=1, ..., Saturday=6."""
    return (d.weekday() + 1) % 7


def get_year_calendar_info(year: int) -> dict:
    """Calculates calendar layout information for a given year.

    Returns:
        dict with:
            - start_sunday: date of (col=0, row=0)
            - total_cols: total number of week columns (53 or 54)
            - jan1: date(year, 1, 1)
            - dec31: date(year, 12, 31)
            - month_positions: list of (month_name, col)
    """
    jan1 = date(year, 1, 1)
    dec31 = date(year, 12, 31)

    start_sunday = jan1 - timedelta(days=get_sunday_weekday(jan1))
    total_days = (dec31 - start_sunday).days + 1
    total_cols = (total_days + 6) // 7

    # Find the column for the 1st of each month
    month_names = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    ]
    month_positions: List[Tuple[str, int]] = []
    for month_idx, name in enumerate(month_names, start=1):
        m_date = date(year, month_idx, 1)
        col = (m_date - start_sunday).days // 7
        month_positions.append((name, col))

    return {
        "year": year,
        "start_sunday": start_sunday,
        "total_cols": total_cols,
        "jan1": jan1,
        "dec31": dec31,
        "month_positions": month_positions,
    }


def coords_to_date(year: int, col: int, row: int) -> Tuple[date, bool]:
    """Convert (col, row) in a year's grid to a date and whether it belongs to that year.

    Returns:
        (date, is_in_year)
    """
    jan1 = date(year, 1, 1)
    start_sunday = jan1 - timedelta(days=get_sunday_weekday(jan1))
    cell_date = start_sunday + timedelta(days=col * 7 + row)
    return cell_date, cell_date.year == year


def date_to_coords(d: date) -> Tuple[int, int]:
    """Convert a date to (col, row) within its year grid."""
    jan1 = date(d.year, 1, 1)
    start_sunday = jan1 - timedelta(days=get_sunday_weekday(jan1))
    delta_days = (d - start_sunday).days
    return delta_days // 7, delta_days % 7


ROW_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
GITHUB_LABELS = {1: "Mon", 3: "Wed", 5: "Fri"}
