#!/usr/bin/env python3
import argparse
import re
from pathlib import Path
from urllib.parse import quote, unquote

FLAG_PAIR_RE = re.compile(r"[\U0001F1E6-\U0001F1FF]{2}")
CODE_RE = re.compile(r"\b([A-Z]{2})\b")

COUNTRY_TO_FLAG = {
    "US": "🇺🇸",
    "RU": "🇷🇺",
    "NL": "🇳🇱",
    "TW": "🇹🇼",
    "OM": "🇴🇲",
    "IN": "🇮🇳",
    "ZA": "🇿🇦",
    "GB": "🇬🇧",
    "UK": "🇬🇧",
    "IE": "🇮🇪",
    "DE": "🇩🇪",
    "FR": "🇫🇷",
    "CA": "🇨🇦",
    "AU": "🇦🇺",
    "JP": "🇯🇵",
    "KR": "🇰🇷",
    "SG": "🇸🇬",
    "HK": "🇭🇰",
    "TR": "🇹🇷",
    "AE": "🇦🇪",
}

WORD_TO_FLAG = {
    "UNITED STATES": "🇺🇸",
    "USA": "🇺🇸",
    "RUSSIA": "🇷🇺",
    "RUS": "🇷🇺",
    "NETHERLANDS": "🇳🇱",
    "TAIWAN": "🇹🇼",
    "OMAN": "🇴🇲",
    "INDIA": "🇮🇳",
    "SOUTH AFRICA": "🇿🇦",
    "UNITED KINGDOM": "🇬🇧",
    "IRELAND": "🇮🇪",
    "UNKNOWN": "🏳️",
}


def extract_flag_from_text(text: str):
    decoded = unquote(text or "")

    m = FLAG_PAIR_RE.search(decoded)
    if m:
        return m.group(0)

    upper = decoded.upper()
    for word, flag in WORD_TO_FLAG.items():
        if word in upper:
            return flag

    for code in CODE_RE.findall(upper):
        flag = COUNTRY_TO_FLAG.get(code)
        if flag:
            return flag

    return "🏳️"


def rewrite_line(line: str, idx: int, channel: str):
    line = line.strip()
    if not line:
        return ""

    if "#" in line:
        base, frag = line.split("#", 1)
    else:
        base, frag = line, ""

    flag = extract_flag_from_text(frag)
    new_desc = f"{channel} - {idx} {flag}"
    return f"{base}#{quote(new_desc, safe=' -')}"


def process_file(path: Path, channel: str):
    lines = [x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    out = [rewrite_line(line, i + 1, channel) for i, line in enumerate(lines)]
    path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    print(f"Обновлен: {path} ({len(out)} ключей)")


def main():
    parser = argparse.ArgumentParser(
        description="Переписывает описания ключей: канал + номер + нормализованный флаг."
    )
    parser.add_argument("--dir", default="file/5TopLiveKeys", help="Папка с txt файлами")
    parser.add_argument("--glob", default="*_ping_ok.txt", help="Маска файлов")
    parser.add_argument("--channel", default="t.me/freekesha21", help="Текст канала в описании")
    args = parser.parse_args()

    root = Path(args.dir)
    files = sorted(root.glob(args.glob))
    if not files:
        print("Файлы не найдены")
        return

    for path in files:
        process_file(path, args.channel)


if __name__ == "__main__":
    main()
