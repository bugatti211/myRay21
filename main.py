#!/usr/bin/env python3
from datetime import datetime
import subprocess
import sys
import time
from pathlib import Path

try:
    from src.project_config import env_int, logs_dir
except ModuleNotFoundError:
    from project_config import env_int, logs_dir

RETRY_ATTEMPTS = env_int("RAY_STEP_RETRIES", 1, minimum=0)
RETRY_SLEEP_SEC = env_int("RAY_STEP_RETRY_SLEEP_SEC", 8, minimum=0)


def run_step(title: str, script: Path, project_root: Path, log_file, requires_vpn: bool = False) -> int:
    if requires_vpn:
        print("[action] ВКЛЮЧИ ВПН")
        print("[wait] pause 180 seconds before Telegram step...")
        time.sleep(180)

    attempts = RETRY_ATTEMPTS + 1
    for attempt in range(1, attempts + 1):
        print(f"[step] {title}: {script} (attempt {attempt}/{attempts})")
        proc = subprocess.Popen(
            [sys.executable, str(script)],
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            msg = line.rstrip("\n")
            print(msg)
            log_file.write(msg + "\n")
        proc.wait()
        if proc.returncode == 0:
            print(f"[ok] {title}")
            return 0
        print(f"[error] step failed: {title} (code={proc.returncode})")
        if attempt < attempts:
            print(f"[retry] {title} after {RETRY_SLEEP_SEC}s")
            time.sleep(RETRY_SLEEP_SEC)
    return 1


def main() -> int:
    base = Path(__file__).resolve().parent
    log_dir = logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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

    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"[start] {datetime.now().isoformat()}\n")
        log_file.write(f"[info] retries={RETRY_ATTEMPTS} sleep={RETRY_SLEEP_SEC}s\n")
        for title, script, requires_vpn in steps[start_idx:]:
            if not script.exists():
                print(f"[error] script not found: {script}")
                log_file.write(f"[error] script not found: {script}\n")
                return 1
            code = run_step(title, script, base, log_file, requires_vpn=requires_vpn)
            if code != 0:
                print(f"[info] full log: {log_path}")
                return code

    print("[done] all steps completed")
    print(f"[info] full log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
