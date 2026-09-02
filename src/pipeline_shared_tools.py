#!/usr/bin/env python3
<<<<<<< HEAD
import json
import re
import subprocess
from datetime import datetime
=======
"""Shared parsing and extraction helpers for the active pipeline."""

import base64
import re
import subprocess
>>>>>>> authostart
from pathlib import Path
from urllib.parse import unquote
from urllib.request import urlopen

<<<<<<< HEAD
STATS_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*-\s*(\d+)\s*$")
URL_RE = re.compile(r"^https?://\S+$")
RU_WORD_RE = re.compile(r"\b(RU|RUS|RUSSIA)\b", re.IGNORECASE)


def parse_pairs(lines):
    cleaned = [line.strip() for line in lines if line.strip()]
    records = []
    i = 0

    while i < len(cleaned):
        url = cleaned[i]
        if not URL_RE.match(url):
            raise ValueError(f"Ожидалась ссылка в строке {i + 1}: {url}")
        if i + 1 >= len(cleaned):
            raise ValueError(f"Для ссылки нет строки со статистикой: {url}")

        m = STATS_RE.match(cleaned[i + 1])
        if not m:
            raise ValueError(
                f"Неверный формат статистики после ссылки {url}: '{cleaned[i + 1]}'. "
                "Ожидается: 'всего - без_дубликатов - живых'"
            )

        total, unique, alive = map(int, m.groups())
        records.append({"url": url, "total": total, "unique": unique, "alive": alive})
        i += 2

    return records


def build_json_and_top10(input_path: Path, output_dir: Path, name_suffix: str | None = None):
    if not input_path.exists():
        raise FileNotFoundError(f"Не найден входной файл: {input_path}")

    lines = input_path.read_text(encoding="utf-8").splitlines()
    records = parse_pairs(lines)
    output_dir.mkdir(parents=True, exist_ok=True)

    checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    base_name = name_suffix or "subs"
    json_path = output_dir / f"{base_name}.json"
    top10_path = output_dir / f"{base_name}_top10.txt"

    payload = {
        "checked_at": checked_at,
        "source_file": str(input_path),
        "subscriptions_total": len(records),
        "subscriptions": records,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    top10 = sorted(records, key=lambda x: x["alive"], reverse=True)[:10]
    top10_path.write_text("\n".join(item["url"] for item in top10) + "\n", encoding="utf-8")

    return {"json_path": json_path, "top10_path": top10_path, "records": len(records)}


def read_top_urls(path: Path):
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line and URL_RE.match(line)]


def read_urls_from_pairs_file(path: Path):
    if not path.exists():
        return set()
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    urls = set()
    for i in range(0, len(lines), 2):
        url = lines[i]
        if URL_RE.match(url):
            urls.add(url)
    return urls
=======

URL_RE = re.compile(r"^https?://\S+$")
RU_WORD_RE = re.compile(r"\b(RU|RUS|RUSSIA)\b", re.IGNORECASE)
HYSTERIA_PREFIXES = ("hysteria2://", "hy2://")
TROJAN_PREFIX = "trojan://"
KEY_PREFIXES = ("vless://", TROJAN_PREFIX, "ss://", *HYSTERIA_PREFIXES)


def read_subscription_urls(path: Path):
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return list(dict.fromkeys(line for line in lines if URL_RE.match(line)))


def parse_base64_subscription(text: str):
    compact = "".join(text.split())
    if not compact or any(prefix in text for prefix in KEY_PREFIXES):
        return None
    try:
        padded = compact + ("=" * ((4 - len(compact) % 4) % 4))
        decoded = base64.b64decode(
            padded,
            altchars=b"-_",
            validate=False,
        ).decode("utf-8", errors="replace")
    except Exception:
        return None
    return decoded if any(prefix in decoded for prefix in KEY_PREFIXES) else None


def key_endpoint(key: str) -> str:
    """Return the connection URI without its display-only fragment."""
    return key.strip().split("#", 1)[0]


def extract_key_lines(text: str):
    decoded = parse_base64_subscription(text)
    if decoded is not None:
        text = decoded

    keys = []
    seen_endpoints = set()
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line or not line.startswith(KEY_PREFIXES):
            continue
        endpoint = key_endpoint(line)
        if endpoint in seen_endpoints:
            continue
        seen_endpoints.add(endpoint)
        keys.append(line)
    return keys


def dedupe_keys_by_endpoint(keys):
    seen = set()
    unique = []
    for key in keys:
        endpoint = key_endpoint(key)
        if not endpoint or endpoint in seen:
            continue
        seen.add(endpoint)
        unique.append(key)
    return unique


def read_top_urls(path: Path):
    return read_subscription_urls(path)
>>>>>>> authostart


def fetch_lines(url: str):
    try:
        with urlopen(url, timeout=30) as response:
            text = response.read().decode("utf-8", errors="replace")
    except Exception:
        result = subprocess.run(
<<<<<<< HEAD
            ["curl", "-L", "--insecure", "--max-time", "30", url],
=======
            ["curl", "-fL", "--max-time", "30", url],
>>>>>>> authostart
            check=True,
            capture_output=True,
            text=True,
        )
        text = result.stdout
<<<<<<< HEAD
    return [line.strip() for line in text.splitlines() if line.strip()]
=======
    return extract_key_lines(text)
>>>>>>> authostart


def is_ru_key(key: str):
    decoded = unquote(key)
    if "🇷🇺" in decoded or "%F0%9F%87%B7%F0%9F%87%BA" in key.upper():
        return True
<<<<<<< HEAD
    desc = decoded.split("#", 1)[1] if "#" in decoded else ""
    return bool(RU_WORD_RE.search(desc))


def extract_keys_from_top10(top10_path: Path, output_dir: Path, force_ru_sources_path: Path | None = None):
    urls = read_top_urls(top10_path)
    force_ru_urls = read_urls_from_pairs_file(force_ru_sources_path) if force_ru_sources_path else set()
    vless_keys = []
    ss_keys = []
    vless_ru_keys = []
    ss_ru_keys = []
    failed = []

    for url in urls:
        force_ru = url in force_ru_urls
=======
    description = decoded.split("#", 1)[1] if "#" in decoded else ""
    return bool(RU_WORD_RE.search(description))


def extract_keys_from_top15(
    top15_path: Path,
    output_dir: Path,
    include_ss: bool = True,
):
    urls = read_top_urls(top15_path)
    vless_keys = []
    ss_keys = []
    vless_ru_keys = []
    trojan_keys = []
    failed = []

    for url in urls:
>>>>>>> authostart
        try:
            lines = fetch_lines(url)
        except Exception as exc:
            failed.append((url, str(exc)))
            continue

        for line in lines:
<<<<<<< HEAD
            if line.startswith("vless://"):
                if force_ru or is_ru_key(line):
                    vless_ru_keys.append(line)
                else:
                    vless_keys.append(line)
            elif line.startswith("ss://"):
                if force_ru or is_ru_key(line):
                    ss_ru_keys.append(line)
                else:
                    ss_keys.append(line)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "vless.txt").write_text("\n".join(vless_keys) + ("\n" if vless_keys else ""), encoding="utf-8")
    (output_dir / "ss.txt").write_text("\n".join(ss_keys) + ("\n" if ss_keys else ""), encoding="utf-8")
    (output_dir / "vless_RU.txt").write_text("\n".join(vless_ru_keys) + ("\n" if vless_ru_keys else ""), encoding="utf-8")
    (output_dir / "ss_RU.txt").write_text("\n".join(ss_ru_keys) + ("\n" if ss_ru_keys else ""), encoding="utf-8")
=======
            if line.startswith(("vless://", *HYSTERIA_PREFIXES)):
                if is_ru_key(line):
                    vless_ru_keys.append(line)
                else:
                    vless_keys.append(line)
            elif line.startswith(TROJAN_PREFIX):
                trojan_keys.append(line)
            elif line.startswith("ss://") and include_ss and not is_ru_key(line):
                ss_keys.append(line)

    output_dir.mkdir(parents=True, exist_ok=True)
    vless_keys = dedupe_keys_by_endpoint(vless_keys)
    ss_keys = dedupe_keys_by_endpoint(ss_keys)
    vless_ru_keys = dedupe_keys_by_endpoint(vless_ru_keys)
    trojan_keys = dedupe_keys_by_endpoint(trojan_keys)
    ru_endpoints = {key_endpoint(key) for key in vless_ru_keys}
    vless_keys = [key for key in vless_keys if key_endpoint(key) not in ru_endpoints]

    (output_dir / "vless.txt").write_text(
        "\n".join(vless_keys) + ("\n" if vless_keys else ""),
        encoding="utf-8",
    )
    ss_path = output_dir / "ss.txt"
    if include_ss:
        ss_path.write_text("\n".join(ss_keys) + ("\n" if ss_keys else ""), encoding="utf-8")
    else:
        ss_path.unlink(missing_ok=True)
    (output_dir / "vless_RU.txt").write_text(
        "\n".join(vless_ru_keys) + ("\n" if vless_ru_keys else ""),
        encoding="utf-8",
    )
    (output_dir / "trojan.txt").write_text(
        "\n".join(trojan_keys) + ("\n" if trojan_keys else ""),
        encoding="utf-8",
    )
>>>>>>> authostart

    return {
        "urls_total": len(urls),
        "failed": failed,
        "vless_total": len(vless_keys),
        "ss_total": len(ss_keys),
        "vless_ru": len(vless_ru_keys),
<<<<<<< HEAD
        "ss_ru": len(ss_ru_keys),
=======
        "trojan_total": len(trojan_keys),
>>>>>>> authostart
    }
