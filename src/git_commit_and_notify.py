#!/usr/bin/env python3
import json
import os
import ssl
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict

import certifi

# ===== Settings =====
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GIT_DIR = PROJECT_ROOT / "git"
ENV_FILE = PROJECT_ROOT / ".env"

TELEGRAM_BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV = "TELEGRAM_CHAT_ID"
REQUEST_TIMEOUT_SEC = 20
INSECURE_SSL_ENV = "TELEGRAM_INSECURE_SSL"

REPO_RAW_BASE = "https://github.com/terik21/HiddifySubs-VlessKeys/raw/refs/heads/main"

DAY_FILES = [
    "1Mond",
    "2Tues",
    "3Wend",
    "4Thur",
    "5Frid",
    "6Satu",
    "7Sand",
]
# ====================


def load_dotenv(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def run_git(args):
    return subprocess.run(
        ["git", *args],
        cwd=str(GIT_DIR),
        capture_output=True,
        text=True,
        check=False,
    )


def next_day_filename(now: datetime) -> str:
    next_idx = (now.weekday() + 1) % 7
    return DAY_FILES[next_idx]


def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    insecure_ssl = os.getenv(INSECURE_SSL_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
    if insecure_ssl:
        ssl_ctx = ssl._create_unverified_context()
    else:
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())

    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC, context=ssl_ctx) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        result = json.loads(body)
        if not result.get("ok"):
            raise RuntimeError(f"telegram error: {body}")


def build_notify_text(updated_file: str) -> str:
    ordinary_url = f"{REPO_RAW_BASE}/{updated_file}"
    bypass_url = f"{REPO_RAW_BASE}/WhiteKeys"
    ru_url = f"{REPO_RAW_BASE}/RU_other"
    return (
        "✅ Обычная подписка обновлена\n"
        f"<code>{ordinary_url}</code>\n\n"
        "✅ Подписка для обхода обновлена\n"
        f"<code>{bypass_url}</code>\n\n"
        "✅ Подписка с РУ ключами\n"
        f"<code>{ru_url}</code>"
    )


def main() -> int:
    if not GIT_DIR.exists():
        print(f"[error] git dir not found: {GIT_DIR}")
        return 1

    dotenv_values = load_dotenv(ENV_FILE)
    token = os.getenv(TELEGRAM_BOT_TOKEN_ENV) or dotenv_values.get(TELEGRAM_BOT_TOKEN_ENV, "")
    chat_id = os.getenv(TELEGRAM_CHAT_ID_ENV) or dotenv_values.get(TELEGRAM_CHAT_ID_ENV, "")
    token = token.strip()
    chat_id = chat_id.strip()
    if not token or not chat_id:
        print(
            f"[error] telegram creds not found; set env or {ENV_FILE} "
            f"({TELEGRAM_BOT_TOKEN_ENV}, {TELEGRAM_CHAT_ID_ENV})"
        )
        return 1

    status = run_git(["status", "--porcelain"])
    if status.returncode != 0:
        print(f"[error] git status failed: {status.stderr.strip()}")
        return 1
    if not status.stdout.strip():
        print("[info] no changes in git repo, nothing to commit")
        return 0

    add_res = run_git(["add", "."])
    if add_res.returncode != 0:
        print(f"[error] git add failed: {add_res.stderr.strip()}")
        return 1

    commit_msg = f"Update subscriptions {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    commit_res = run_git(["commit", "-m", commit_msg])
    if commit_res.returncode != 0:
        print(f"[error] git commit failed: {commit_res.stderr.strip()}")
        return 1

    push_res = run_git(["push", "origin", "main"])
    if push_res.returncode != 0:
        print(f"[error] git push failed: {push_res.stderr.strip()}")
        return 1

    updated_day_file = next_day_filename(datetime.now())
    text = build_notify_text(updated_file=updated_day_file)
    try:
        send_telegram_message(token=token, chat_id=chat_id, text=text)
    except Exception as exc:
        print(f"[error] commit pushed, but telegram send failed: {exc}")
        return 1

    print("[done] commit + push + telegram notify complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
