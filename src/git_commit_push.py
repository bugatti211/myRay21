#!/usr/bin/env python3
import subprocess
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GIT_DIR = PROJECT_ROOT / "git"


def run_git(args):
    return subprocess.run(
        ["git", *args],
        cwd=str(GIT_DIR),
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    if not (GIT_DIR / ".git").exists():
        print(f"[error] git repository not found: {GIT_DIR}")
        return 1

    status = run_git(["status", "--porcelain"])
    if status.returncode != 0:
        print(f"[error] git status failed: {status.stderr.strip()}")
        return 1
    if not status.stdout.strip():
        print("[info] no changes in git repo, nothing to commit")
        return 0

    add_result = run_git(["add", "."])
    if add_result.returncode != 0:
        print(f"[error] git add failed: {add_result.stderr.strip()}")
        return 1

    commit_message = f"Update VLESS/Hysteria 2/Trojan subscriptions {datetime.now():%Y-%m-%d %H:%M:%S}"
    commit_result = run_git(["commit", "-m", commit_message])
    if commit_result.returncode != 0:
        print(f"[error] git commit failed: {commit_result.stderr.strip()}")
        return 1

    push_result = run_git(["push", "origin", "main"])
    if push_result.returncode != 0:
        print(f"[error] git push failed: {push_result.stderr.strip()}")
        return 1

    print("[done] commit + push complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
