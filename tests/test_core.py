"""Automated unit tests for GrafGit core logic."""

import os
import shutil
import tempfile
import unittest
from datetime import date

from grafgit.core.calendar import (
    coords_to_date,
    date_to_coords,
    get_sunday_weekday,
    get_year_calendar_info,
)
from grafgit.core.font7x5 import render_text
from grafgit.core.git_engine import GitEngine
from grafgit.core.project import Project


class TestCalendar(unittest.TestCase):
    def test_sunday_weekday(self):
        # 2024-01-01 was a Monday
        d_mon = date(2024, 1, 1)
        self.assertEqual(get_sunday_weekday(d_mon), 1)

        # 2023-12-31 was a Sunday
        d_sun = date(2023, 12, 31)
        self.assertEqual(get_sunday_weekday(d_sun), 0)

    def test_2024_calendar(self):
        info = get_year_calendar_info(2024)
        self.assertEqual(info["year"], 2024)
        self.assertIn(info["total_cols"], (53, 54))

        # Check (0, 1) is Jan 1, 2024
        d, in_year = coords_to_date(2024, 0, 1)
        self.assertTrue(in_year)
        self.assertEqual(d, date(2024, 1, 1))

        # Check (0, 0) is Dec 31, 2023 (not in 2024)
        d_prev, in_year_prev = coords_to_date(2024, 0, 0)
        self.assertFalse(in_year_prev)
        self.assertEqual(d_prev, date(2023, 12, 31))

        # Check roundtrip date_to_coords
        col, row = date_to_coords(date(2024, 1, 1))
        self.assertEqual((col, row), (0, 1))

    def test_month_positions(self):
        info = get_year_calendar_info(2024)
        months = [col for _, col in info["month_positions"]]
        self.assertEqual(len(months), 12)
        # Months should appear in strictly non-decreasing column order
        for i in range(len(months) - 1):
            self.assertLessEqual(months[i], months[i + 1])


class TestFont(unittest.TestCase):
    def test_render_letter(self):
        mat = render_text("A", level=4)
        self.assertEqual(len(mat), 5)  # 'A' glyph width is 5
        for col in mat:
            self.assertEqual(len(col), 7)
        # Check some pixel is on
        self.assertTrue(any(val == 4 for col in mat for val in col))

    def test_render_multi_char(self):
        mat = render_text("GO", level=3)
        # G (5) + space (1) + O (5) = 11 columns
        self.assertEqual(len(mat), 11)
        # Middle column should be space (all 0s)
        self.assertEqual(mat[5], [0] * 7)


class TestProject(unittest.TestCase):
    def test_pixel_manipulation_and_undo(self):
        proj = Project(year=2024)
        # Set pixel at (0, 1) -> Jan 1, 2024
        res = proj.set_pixel(0, 1, 3)
        self.assertTrue(res)
        self.assertEqual(proj.get_pixel(0, 1), 3)

        # Set pixel on inactive day (0, 0) -> Dec 31, 2023
        res_inactive = proj.set_pixel(0, 0, 3)
        self.assertFalse(res_inactive)

        # Undo test
        proj.save_state()
        proj.set_pixel(1, 1, 4)
        self.assertEqual(proj.get_pixel(1, 1), 4)
        proj.undo()
        self.assertEqual(proj.get_pixel(1, 1), 0)
        self.assertEqual(proj.get_pixel(0, 1), 3)

    def test_shift_and_invert(self):
        proj = Project(year=2024)
        proj.set_pixel(1, 1, 2)
        proj.shift(2)
        self.assertEqual(proj.get_pixel(1, 1), 0)
        self.assertEqual(proj.get_pixel(3, 1), 2)

    def test_commit_plan(self):
        proj = Project(year=2024)
        proj.set_pixel(0, 1, 1)  # level 1 = 1 commit
        proj.set_pixel(0, 2, 2)  # level 2 = 3 commits
        plan = proj.get_commit_plan()
        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0], (date(2024, 1, 1), 1))
        self.assertEqual(plan[1], (date(2024, 1, 2), 3))


class TestGitEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_git_commit_generation(self):
        engine = GitEngine(self.temp_dir)
        engine.init_repo(default_branch="main")
        self.assertTrue(engine.is_git_repo())

        plan = [(date(2024, 5, 1), 1), (date(2024, 5, 2), 2)]
        total = engine.generate_commits(
            commit_plan=plan,
            author_name="GrafGit Test",
            author_email="test@grafgit.dev",
        )
        self.assertEqual(total, 3)

        # Verify git log dates
        code, out, _ = engine._run_git(["log", "--pretty=format:%ad", "--date=short"])
        self.assertEqual(code, 0)
        dates = out.strip().split("\n")
        self.assertEqual(len(dates), 3)
        self.assertEqual(dates[0], "2024-05-02")
        self.assertEqual(dates[1], "2024-05-02")
        self.assertEqual(dates[2], "2024-05-01")


if __name__ == "__main__":
    unittest.main()
