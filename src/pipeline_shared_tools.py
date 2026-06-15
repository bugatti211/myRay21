#!/usr/bin/env python3
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from urllib.request import urlopen

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


def read_urls_from_list_file(path: Path):
    if not path.exists():
        return set()
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return {line for line in lines if line and URL_RE.match(line)}


def fetch_lines(url: str):
    try:
        with urlopen(url, timeout=30) as response:
            text = response.read().decode("utf-8", errors="replace")
    except Exception:
        result = subprocess.run(
            ["curl", "-L", "--insecure", "--max-time", "30", url],
            check=True,
            capture_output=True,
            text=True,
        )
        text = result.stdout
    return [line.strip() for line in text.splitlines() if line.strip()]


def is_ru_key(key: str):
    decoded = unquote(key)
    if "🇷🇺" in decoded or "%F0%9F%87%B7%F0%9F%87%BA" in key.upper():
        return True
    desc = decoded.split("#", 1)[1] if "#" in decoded else ""
    return bool(RU_WORD_RE.search(desc))


def extract_keys_from_top10(
    top10_path: Path,
    output_dir: Path,
    force_ru_sources_path: Path | None = None,
    trojan_ru_sources_path: Path | None = None,
):
    urls = read_top_urls(top10_path)
    force_ru_urls = read_urls_from_pairs_file(force_ru_sources_path) if force_ru_sources_path else set()
    trojan_ru_urls = read_urls_from_list_file(trojan_ru_sources_path) if trojan_ru_sources_path else set()
    vless_keys = []
    ss_keys = []
    vless_ru_keys = []
    failed = []

    for url in urls:
        force_ru = url in force_ru_urls
        allow_trojan_ru = url in trojan_ru_urls
        try:
            lines = fetch_lines(url)
        except Exception as exc:
            failed.append((url, str(exc)))
            continue

        for line in lines:
            if line.startswith("vless://"):
                if force_ru or is_ru_key(line):
                    vless_ru_keys.append(line)
                else:
                    vless_keys.append(line)
            elif line.startswith("ss://"):
                if not (force_ru or is_ru_key(line)):
                    ss_keys.append(line)
            elif line.startswith("trojan://"):
                if allow_trojan_ru:
                    vless_ru_keys.append(line)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "vless.txt").write_text("\n".join(vless_keys) + ("\n" if vless_keys else ""), encoding="utf-8")
    (output_dir / "ss.txt").write_text("\n".join(ss_keys) + ("\n" if ss_keys else ""), encoding="utf-8")
    (output_dir / "vless_RU.txt").write_text("\n".join(vless_ru_keys) + ("\n" if vless_ru_keys else ""), encoding="utf-8")

    return {
        "urls_total": len(urls),
        "failed": failed,
        "vless_total": len(vless_keys),
        "ss_total": len(ss_keys),
        "vless_ru": len(vless_ru_keys),
    }
