"""Git execution engine for GrafGit.

Handles Git repository detection, author configuration, commit generation with
precise timestamp spoofing, push, rollback mechanisms, and scanning existing repository contributions.
"""

import os
import subprocess
from datetime import date, datetime
from typing import Callable, Dict, List, Optional, Set, Tuple


class GitEngine:
    def __init__(self, repo_dir: str):
        self.repo_dir = os.path.abspath(repo_dir)

    def _run_git(
        self,
        args: List[str],
        env: Optional[dict] = None,
        check: bool = True
    ) -> Tuple[int, str, str]:
        """Runs a git command in the repository directory."""
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        proc = subprocess.run(
            ["git"] + args,
            cwd=self.repo_dir,
            env=full_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        if check and proc.returncode != 0:
            raise RuntimeError(f"Git command failed: git {' '.join(args)}\nError: {proc.stderr.strip()}")
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def is_git_repo(self) -> bool:
        """Checks if repo_dir is a git repository."""
        code, out, _ = self._run_git(["rev-parse", "--is-inside-work-tree"], check=False)
        return code == 0 and out == "true"

    def init_repo(self, default_branch: str = "main") -> str:
        """Initializes a new git repository if not already initialized."""
        if not self.is_git_repo():
            self._run_git(["init", "-b", default_branch])
            return f"Initialized new Git repository in {self.repo_dir} with branch '{default_branch}'"
        return f"Existing Git repository detected in {self.repo_dir}"

    def get_current_branch(self) -> str:
        code, out, _ = self._run_git(["branch", "--show-current"], check=False)
        return out if code == 0 and out else "main"

    def get_author_config(self) -> Tuple[str, str]:
        """Reads user.name and user.email from git config."""
        _, name, _ = self._run_git(["config", "user.name"], check=False)
        _, email, _ = self._run_git(["config", "user.email"], check=False)
        return name, email

    def get_head_hash(self) -> Optional[str]:
        code, out, _ = self._run_git(["rev-parse", "HEAD"], check=False)
        return out if code == 0 and out else None

    def fetch_repo_contributions(
        self,
        year: Optional[int] = None,
        filter_email: Optional[str] = None
    ) -> Tuple[Dict[date, int], Set[int]]:
        """Scans commit history of the repository.

        Returns:
            Tuple of:
                - dict mapping date -> commit count for that day (filtered by year if provided)
                - set of all years that have at least one commit in the repo
        """
        if not self.is_git_repo():
            return {}, set()

        # Format: YYYY-MM-DD|author_email
        code, out, _ = self._run_git(
            ["log", "--pretty=format:%ad|%ae", "--date=short"],
            check=False
        )
        if code != 0 or not out:
            return {}, set()

        date_counts: Dict[date, int] = {}
        all_years: Set[int] = set()

        filter_email_clean = filter_email.strip().lower() if filter_email else None

        for line in out.splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            date_str, email = line.split("|", 1)
            if filter_email_clean and email.strip().lower() != filter_email_clean:
                continue

            try:
                commit_d = datetime.strptime(date_str, "%Y-%m-%d").date()
                all_years.add(commit_d.year)
                if year is None or commit_d.year == year:
                    date_counts[commit_d] = date_counts.get(commit_d, 0) + 1
            except ValueError:
                continue

        return date_counts, all_years

    def generate_commits(
        self,
        commit_plan: List[Tuple[date, int]],
        author_name: str,
        author_email: str,
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
        log_cb: Optional[Callable[[str], None]] = None,
        art_file_rel: str = ".grafgit/art.dat",
        commit_msg_template: str = "chore: update build log ({date})",
    ) -> int:
        """Generates commits across specified dates with exact timestamp manipulation.

        Args:
            commit_plan: List of (date, commit_count)
            author_name: Name of git author
            author_email: Email associated with GitHub account
            progress_cb: Callback (current, total, status_text)
            log_cb: Callback for text logging
            art_file_rel: Path to the art log file relative to repo root

        Returns:
            Total number of commits created.
        """
        if not self.is_git_repo():
            init_msg = self.init_repo()
            if log_cb:
                log_cb(init_msg)

        art_dir = os.path.join(self.repo_dir, ".grafgit")
        os.makedirs(art_dir, exist_ok=True)
        art_filepath = os.path.join(self.repo_dir, art_file_rel)

        # Save pre-art HEAD hash for safe rollback if not already stored
        current_head = self.get_head_hash()
        backup_file = os.path.join(art_dir, "pre_art_head.txt")
        if not os.path.exists(backup_file):
            target_to_save = current_head if current_head else "EMPTY_REPO"
            with open(backup_file, "w", encoding="utf-8") as f:
                f.write(target_to_save)
            if log_cb:
                if current_head:
                    log_cb(f"Saved pre-art rollback point: {current_head[:7]}")
                else:
                    log_cb("Saved pre-art rollback point: initial empty repository state")

        # Calculate total commits
        total_commits = sum(count for _, count in commit_plan)
        if total_commits == 0:
            if log_cb:
                log_cb("No active cells to commit.")
            return 0

        # Detect system local timezone offset (e.g. +0200, +0300, -0500)
        import time
        tz_offset = time.strftime("%z")
        if not tz_offset or len(tz_offset) != 5:
            tz_offset = "+0000"

        if log_cb:
            log_cb(f"Starting commit generation: {total_commits} commits across {len(commit_plan)} days...")
            log_cb(f"Author: {author_name} <{author_email}> (Timezone: {tz_offset})")

        created_commits = 0

        for day_idx, (commit_date, count) in enumerate(commit_plan, 1):
            for i in range(count):
                created_commits += 1

                # Slightly vary seconds/minutes to keep commits distinctly ordered
                sec = (i * 3) % 60
                minute = (i // 20) % 60
                timestamp_str = f"{commit_date.strftime('%Y-%m-%d')} 12:{minute:02d}:{sec:02d} {tz_offset}"

                # Update art data file
                with open(art_filepath, "a", encoding="utf-8") as f:
                    f.write(f"{timestamp_str} | commit #{created_commits}\n")

                # Git add
                self._run_git(["add", art_file_rel])

                # Commit with custom author and committer dates
                env = {
                    "GIT_AUTHOR_NAME": author_name,
                    "GIT_AUTHOR_EMAIL": author_email,
                    "GIT_COMMITTER_NAME": author_name,
                    "GIT_COMMITTER_EMAIL": author_email,
                    "GIT_AUTHOR_DATE": timestamp_str,
                    "GIT_COMMITTER_DATE": timestamp_str,
                }

                if "{date}" in commit_msg_template or "{i}" in commit_msg_template or "{count}" in commit_msg_template:
                    try:
                        msg = commit_msg_template.format(
                            date=commit_date.strftime("%Y-%m-%d"),
                            i=i + 1,
                            count=count
                        )
                    except Exception:
                        msg = f"{commit_msg_template} ({commit_date.strftime('%Y-%m-%d')} #{i + 1})"
                elif count > 1:
                    msg = f"{commit_msg_template} ({i + 1}/{count})"
                else:
                    msg = commit_msg_template

                self._run_git(["commit", "-m", msg], env=env)

                if progress_cb and (created_commits % 5 == 0 or created_commits == total_commits):
                    status_text = f"Committing: {commit_date} ({created_commits}/{total_commits})"
                    progress_cb(created_commits, total_commits, status_text)

        if log_cb:
            log_cb(f"Done! Successfully created {created_commits} commits.")
            new_head = self.get_head_hash()
            log_cb(f"New HEAD: {new_head[:7] if new_head else 'unknown'}")

        return created_commits

    def push(
        self,
        remote: str = "origin",
        branch: Optional[str] = None,
        force: bool = False,
        log_cb: Optional[Callable[[str], None]] = None
    ) -> bool:
        """Pushes current branch to remote."""
        if not branch:
            branch = self.get_current_branch()

        args = ["push", remote, branch]
        if force:
            args.insert(1, "--force")

        if log_cb:
            log_cb(f"Running: git {' '.join(args)}...")

        code, out, err = self._run_git(args, check=False)
        if log_cb:
            if out:
                log_cb(out)
            if err:
                log_cb(err)

        if code == 0:
            if log_cb:
                log_cb(f"Successfully pushed to {remote}/{branch}!")
            return True
        else:
            if log_cb:
                log_cb(f"Push failed (code {code}). Check remote configuration.")
            return False

    def rollback(self, log_cb: Optional[Callable[[str], None]] = None) -> bool:
        """Safely rolls back to pre-art HEAD if backup exists."""
        backup_file = os.path.join(self.repo_dir, ".grafgit", "pre_art_head.txt")
        if not os.path.exists(backup_file):
            if log_cb:
                log_cb("No pre-art rollback point found. You can use manual 'git reset' if needed.")
            return False

        with open(backup_file, "r", encoding="utf-8") as f:
            target_hash = f.read().strip()

        if not target_hash:
            if log_cb:
                log_cb("Rollback hash was empty.")
            return False

        if target_hash == "EMPTY_REPO":
            if log_cb:
                log_cb("Rolling back to empty repository state (pre-art initial state)...")
            branch = self.get_current_branch()
            self._run_git(["update-ref", "-d", f"refs/heads/{branch}"], check=False)
            art_file = os.path.join(self.repo_dir, ".grafgit", "art.dat")
            if os.path.exists(art_file):
                try:
                    os.remove(art_file)
                except OSError:
                    pass
            try:
                os.remove(backup_file)
            except OSError:
                pass
            if log_cb:
                log_cb("Rollback complete! Repository returned to empty initial state.")
            return True

        if log_cb:
            log_cb(f"Rolling back HEAD to pre-art commit: {target_hash[:7]}...")

        code, out, err = self._run_git(["reset", "--hard", target_hash], check=False)
        if code == 0:
            if log_cb:
                log_cb("Rollback complete! Canvas commits have been cleanly wiped from local history.")
                log_cb("To remove them from GitHub, run: git push --force origin main")
            # Remove backup file
            try:
                os.remove(backup_file)
            except OSError:
                pass
            return True
        else:
            if log_cb:
                log_cb(f"Rollback error: {err}")
            return False
