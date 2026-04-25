#!/usr/bin/env python3
import subprocess
import sys
import time
from pathlib import Path


def run_step(title: str, script: Path, project_root: Path, requires_vpn: bool = False) -> int:
    if requires_vpn:
        print("[action] ВКЛЮЧИ ВПН")
        print("[wait] pause 180 seconds before Telegram step...")
        time.sleep(180)

    print(f"[step] {title}: {script}")
    result = subprocess.run([sys.executable, str(script)], cwd=str(project_root))
    if result.returncode != 0:
        print(f"[error] step failed: {title} (code={result.returncode})")
    else:
        print(f"[ok] {title}")
    return result.returncode


def main() -> int:
    base = Path(__file__).resolve().parent
    steps = [
        ("parse", base / "src" / "parse_keys.py", False),
        ("check", base / "src" / "check_keys.py", False),
        ("rank_keys", base / "src" / "rank_keys.py", False),
        ("build_desc_keys", base / "src" / "build_desc_keys.py", False),
        ("write_git_from_desc_keys", base / "src" / "write_git_from_desc_keys.py", False),
        ("send_ss_to_telegram", base / "src" / "send_ss_to_telegram.py", True),
        ("git_commit_and_notify", base / "src" / "git_commit_and_notify.py", False),
    ]

    print("[info] available steps:")
    for idx, (title, script, _) in enumerate(steps, start=1):
        print(f"  {idx}. {title} ({script.name})")

    start_idx = 0
    while True:
        raw = input(f"[input] enter step number to start with (1-{len(steps)}): ").strip()
        if not raw.isdigit():
            print("[error] please enter a valid number")
            continue
        num = int(raw)
        if 1 <= num <= len(steps):
            start_idx = num - 1
            break
        print(f"[error] number must be in range 1-{len(steps)}")

    print(f"[info] starting from step {start_idx + 1}: {steps[start_idx][0]}")

    for title, script, requires_vpn in steps[start_idx:]:
        if not script.exists():
            print(f"[error] script not found: {script}")
            return 1
        code = run_step(title, script, base, requires_vpn=requires_vpn)
        if code != 0:
            return code

    print("[done] all steps completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
