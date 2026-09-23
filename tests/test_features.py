"""Comprehensive integration tests for GrafGit features:
- Multi-year canvas persistence
- Git contribution scanning and visualization
- Text stamping
- Image conversion and thresholding
"""

import os
import shutil
import tempfile
import unittest
from datetime import date
from PIL import Image

from grafgit.core.font7x5 import render_text
from grafgit.core.git_engine import GitEngine
from grafgit.core.image_proc import convert_image_to_grid
from grafgit.core.project import Project


class TestFeatures(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_multi_year_canvas_persistence(self):
        proj = Project(initial_year=2024)

        # Draw a pixel in 2024
        proj.set_pixel(10, 3, 4, year=2024)
        self.assertEqual(proj.get_pixel(10, 3, year=2024), 4)

        # Switch to 2025 and draw different pixel
        proj.set_active_year(2025)
        self.assertEqual(proj.get_pixel(10, 3, year=2025), 0)  # should be empty in 2025
        proj.set_pixel(15, 2, 2, year=2025)
        self.assertEqual(proj.get_pixel(15, 2, year=2025), 2)

        # Switch back to 2024 and verify pixel is still there
        proj.set_active_year(2024)
        self.assertEqual(proj.get_pixel(10, 3, year=2024), 4)

        # Save and reload file
        save_path = os.path.join(self.temp_dir, "test_multi.grafgit")
        proj.save_file(save_path)

        loaded = Project.load_file(save_path)
        self.assertEqual(loaded.get_pixel(10, 3, year=2024), 4)
        self.assertEqual(loaded.get_pixel(15, 2, year=2025), 2)

    def test_git_scan_contributions(self):
        engine = GitEngine(self.temp_dir)
        engine.init_repo(default_branch="main")

        # Generate commits across 2 different years (2024 and 2025)
        plan_2024 = [(date(2024, 9, 13), 1)]  # matches user's screenshot date!
        plan_2025 = [(date(2025, 3, 10), 3)]

        engine.generate_commits(
            commit_plan=plan_2024 + plan_2025,
            author_name="Artist",
            author_email="art@example.com"
        )

        # Scan for 2024 contributions
        counts_2024, all_years = engine.fetch_repo_contributions(year=2024)
        self.assertIn(2024, all_years)
        self.assertIn(2025, all_years)
        self.assertEqual(counts_2024.get(date(2024, 9, 13)), 1)
        self.assertIsNone(counts_2024.get(date(2025, 3, 10)))  # filtered by year

        # Load into project
        proj = Project(initial_year=2024)
        proj.load_existing_contributions(2024, counts_2024)
        stats = proj.get_stats(2024)
        self.assertEqual(stats["active_days"], 1)
        self.assertEqual(stats["total_commits"], 1)

    def test_image_conversion(self):
        # Create a small dummy image: 14x14 pixels with black and white blocks
        test_img_path = os.path.join(self.temp_dir, "sample.png")
        img = Image.new("RGB", (28, 14), color=(0, 0, 0))
        # Draw white square
        for x in range(14):
            for y in range(14):
                img.putpixel((x, y), (255, 255, 255))
        img.save(test_img_path)

        grid = convert_image_to_grid(test_img_path, invert=False, max_width=53)
        self.assertGreater(len(grid), 0)
        self.assertEqual(len(grid[0]), 7)
        # First half should be bright (level 4)
        self.assertEqual(grid[0][0], 4)
        # Second half should be dark (level 0)
        self.assertEqual(grid[-1][0], 0)

    def test_text_stamping_on_project(self):
        proj = Project(initial_year=2024)
        matrix = render_text("HI", level=3)
        proj.stamp_matrix(matrix, start_col=5, start_row=0)
        stats = proj.get_stats(2024)
        self.assertGreater(stats["active_days"], 0)

    def test_duplicate_element(self):
        proj = Project(initial_year=2024)
        el = proj.add_text_element("TEST", x=5, y=1, level=4)
        dup = proj.duplicate_element(el["id"])
        self.assertIsNotNone(dup)
        self.assertNotEqual(dup["id"], el["id"])
        self.assertEqual(dup["x"], 7)  # +2 offset
        self.assertEqual(len(proj.get_elements()), 2)

    def test_copy_year_to(self):
        proj = Project(initial_year=2024)
        proj.add_text_element("ART", x=10, y=0, level=4)
        proj.set_pixel(1, 1, 3, year=2024)

        proj.copy_year_to(2024, 2025)
        proj.set_active_year(2025)

        els_2025 = proj.get_elements(2025)
        self.assertEqual(len(els_2025), 1)
        self.assertEqual(els_2025[0]["text"], "ART")
        self.assertEqual(proj.get_pixel(1, 1, year=2025), 3)

    def test_custom_multipliers(self):
        proj = Project(initial_year=2024)
        proj.set_pixel(5, 2, 4)
        # Default level 4 is 10 commits
        plan_default = proj.get_commit_plan(2024)
        self.assertEqual(plan_default[0][1], 10)

        # Update multipliers: level 4 -> 25 commits
        proj.set_multipliers({1: 2, 2: 5, 3: 12, 4: 25})
        plan_custom = proj.get_commit_plan(2024)
        self.assertEqual(plan_custom[0][1], 25)

    def test_export_project_to_image(self):
        from grafgit.core.export_png import export_project_to_image
        proj = Project(initial_year=2024)
        proj.add_text_element("OK", x=4, y=0, level=4)
        img = export_project_to_image(proj, year=2024, scale=2)
        self.assertIsNotNone(img)
        self.assertGreater(img.width, 1000)
        self.assertGreater(img.height, 200)

    def test_empty_repo_rollback(self):
        engine = GitEngine(self.temp_dir)
        engine.init_repo(default_branch="main")
        plan = [(date(2024, 1, 1), 2)]
        engine.generate_commits(plan, author_name="Artist", author_email="a@b.com")

        # Rollback should cleanly return to initial empty state without failing
        success = engine.rollback()
        self.assertTrue(success)
        self.assertIsNone(engine.get_head_hash())

    def test_custom_commit_message_template(self):
        engine = GitEngine(self.temp_dir)
        engine.init_repo(default_branch="main")
        plan = [(date(2024, 5, 20), 2)]
        engine.generate_commits(
            plan,
            author_name="Dev",
            author_email="dev@example.com",
            commit_msg_template="docs: update spec ({date} #{i})"
        )

        _, log_out, _ = engine._run_git(["log", "-1", "--pretty=%s"])
        self.assertIn("docs: update spec (2024-05-20 #2)", log_out)


    def test_template_element(self):
        proj = Project(initial_year=2024)
        el = proj.add_template_element("heart", x=15, y=0, level=4)
        self.assertIsNotNone(el)
        self.assertEqual(el["type"], "template")
        self.assertEqual(el["x"], 15)

        stats = proj.get_stats(2024)
        self.assertGreater(stats["active_days"], 0)

        # Move template element with X/Y updates
        proj.update_element(el["id"], {"x": 20, "y": 0, "template_key": "check"})
        elements = proj.get_elements(2024)
        self.assertEqual(elements[0]["x"], 20)
        self.assertEqual(elements[0]["name"], "Шаблон: Галочка")

    def test_2d_shift(self):
        proj = Project(initial_year=2024)
        el = proj.add_template_element("heart", x=10, y=0, level=4)
        proj.set_pixel(10, 0, 3)

        # Shift right by 3 and down by 1
        proj.shift(dx=3, dy=1)

        elements = proj.get_elements(2024)
        self.assertEqual(elements[0]["x"], 13)
        self.assertEqual(elements[0]["y"], 1)

        # Freehand pixel (10, 0) should now be at (13, 1)
        self.assertEqual(proj.get_pixel(13, 1), 3)


if __name__ == "__main__":
    unittest.main()

