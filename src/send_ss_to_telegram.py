#!/usr/bin/env python3
import html
import json
import os
import ssl
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import certifi


# ===== Settings =====
SOURCE_DIR = Path("file/desc_keys")
FALLBACK_SOURCE_DIR = Path("file/deck_keys")
SS_FILE = "ss.txt"
ENV_FILE = Path(".env")
TELEGRAM_BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV = "TELEGRAM_CHAT_ID"
SEND_DELAY_SEC = 0.35
REQUEST_TIMEOUT_SEC = 20
INSECURE_SSL_ENV = "TELEGRAM_INSECURE_SSL"
# ====================


def iter_links(path: Path):
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        yield line


def resolve_source_dir() -> Path:
    if SOURCE_DIR.exists():
        return SOURCE_DIR
    if FALLBACK_SOURCE_DIR.exists():
        print(f"[warn] {SOURCE_DIR} not found, using {FALLBACK_SOURCE_DIR}")
        return FALLBACK_SOURCE_DIR
    return SOURCE_DIR


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


def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_notification": True,
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
        raw = json.loads(body)
        if not raw.get("ok"):
            raise RuntimeError(f"telegram error: {body}")


def build_message(day_num: int, seq_no: int, key: str) -> str:
    # Requested format:
    # #{today_day}{index}
    # `key`
    tag = f"#{day_num}{seq_no}"
    safe_key = html.escape(key, quote=False)
    return f"{tag}\n<code>{safe_key}</code>"


def main() -> int:
    dotenv_values = load_dotenv(ENV_FILE)
    token = (os.getenv(TELEGRAM_BOT_TOKEN_ENV) or dotenv_values.get(TELEGRAM_BOT_TOKEN_ENV, "")).strip()
    chat_id = (os.getenv(TELEGRAM_CHAT_ID_ENV) or dotenv_values.get(TELEGRAM_CHAT_ID_ENV, "")).strip()
    if not token or not chat_id:
        print(
            f"[error] set env vars {TELEGRAM_BOT_TOKEN_ENV} and {TELEGRAM_CHAT_ID_ENV} "
            f"or add them to {ENV_FILE}"
        )
        return 1

    source_dir = resolve_source_dir()
    ss_path = source_dir / SS_FILE
    if not ss_path.exists():
        print(f"[error] ss source file not found: {ss_path}")
        return 1

    keys: List[str] = list(iter_links(ss_path))
    if not keys:
        print(f"[info] no keys in {ss_path}")
        return 0

    day_num = datetime.now().day
    print(f"[start] sending {len(keys)} keys from {ss_path}")

    sent = 0
    for idx, key in enumerate(keys, start=1):
        text = build_message(day_num=day_num, seq_no=idx, key=key)
        try:
            send_telegram_message(token=token, chat_id=chat_id, text=text)
            sent += 1
            print(f"[ok] sent {sent}/{len(keys)}")
        except Exception as exc:
            print(f"[error] failed at #{idx}: {exc}")
        time.sleep(SEND_DELAY_SEC)

    print(f"[done] sent={sent}/{len(keys)}")
    return 0 if sent == len(keys) else 1


if __name__ == "__main__":
    raise SystemExit(main())
