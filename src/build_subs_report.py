#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.error import URLError, HTTPError
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

        stats_line = cleaned[i + 1]
        m = STATS_RE.match(stats_line)
        if not m:
            raise ValueError(
                f"Неверный формат статистики после ссылки {url}: '{stats_line}'. "
                "Ожидается: 'всего - без_дубликатов - живых'"
            )

        total, unique, alive = map(int, m.groups())
        records.append(
            {
                "url": url,
                "total": total,
                "unique": unique,
                "alive": alive,
            }
        )
        i += 2

    return records


def read_top_urls(path: Path):
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line and URL_RE.match(line)]


def fetch_lines(url: str):
    try:
        with urlopen(url, timeout=30) as response:
            data = response.read()
        text = data.decode("utf-8", errors="replace")
    except Exception:
        # Fallback for environments where local CA chain is missing.
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


def extract_and_split_keys(top10_path: Path, output_dir: Path):
    urls = read_top_urls(top10_path)
    vless_keys = []
    ss_keys = []
    vless_ru_keys = []
    failed = []

    for url in urls:
        try:
            lines = fetch_lines(url)
        except (URLError, HTTPError, TimeoutError) as exc:
            failed.append((url, str(exc)))
            continue

        for line in lines:
            if line.startswith("vless://"):
                if is_ru_key(line):
                    vless_ru_keys.append(line)
                else:
                    vless_keys.append(line)
            elif line.startswith("ss://"):
                if not is_ru_key(line):
                    ss_keys.append(line)

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


def main():
    parser = argparse.ArgumentParser(
        description="Собирает JSON-отчет, топ-10 и ключи из топ-10 подписок."
    )
    parser.add_argument(
        "--input",
        default="file/1AllLinksFromGit/default.txt",
        help="Путь к исходному txt файлу (по умолчанию: file/1AllLinksFromGit/default.txt)",
    )
    parser.add_argument(
        "--output-dir",
        default="file/2TopLinksFromGit",
        help="Папка для выходных файлов (по умолчанию: file/2TopLinksFromGit)",
    )
    parser.add_argument(
        "--keys-dir",
        default="file/3KeysFromGit",
        help="Папка для файлов с ключами (по умолчанию: file/3KeysFromGit)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    if not input_path.exists():
        raise FileNotFoundError(f"Не найден входной файл: {input_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    lines = input_path.read_text(encoding="utf-8").splitlines()
    records = parse_pairs(lines)

    stamp = datetime.now().strftime("%Y-%m-%d")
    json_path = output_dir / f"{stamp}.json"
    top10_path = output_dir / f"{stamp}_top10.txt"

    json_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    top10 = sorted(records, key=lambda x: x["alive"], reverse=True)[:10]
    top10_lines = [
        f"{item['url']}"
        for item in top10
    ]
    top10_path.write_text("\n".join(top10_lines) + "\n", encoding="utf-8")

    print(f"Готово: {json_path}")
    print(f"Готово: {top10_path}")
    print(f"Обработано подписок: {len(records)}")

    keys_stats = extract_and_split_keys(top10_path, Path(args.keys_dir))
    print(f"Готово: {Path(args.keys_dir) / 'vless.txt'} ({keys_stats['vless_total']})")
    print(f"Готово: {Path(args.keys_dir) / 'ss.txt'} ({keys_stats['ss_total']})")
    print(f"Готово: {Path(args.keys_dir) / 'vless_RU.txt'} ({keys_stats['vless_ru']})")
    if keys_stats["failed"]:
        print("Не удалось скачать некоторые подписки:")
        for url, error in keys_stats["failed"]:
            print(f"- {url}: {error}")


if __name__ == "__main__":
    main()
