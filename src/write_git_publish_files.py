#!/usr/bin/env python3
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import re
from urllib.parse import quote, unquote

# ===== Settings =====
PRIMARY_SOURCE_DIR = Path("file/5TopLiveKeys")
FALLBACK_SOURCE_DIR = Path("file/4LiveKeys")
LEGACY_SOURCE_DIR = Path("file/3KeysFromGit")
GIT_DIR = Path("git")

VLESS_SOURCE = "vless_ping_ok.txt"
SS_SOURCE = "ss_ping_ok.txt"
VLESS_RU_SOURCE = "vless_RU_ping_ok.txt"

WHITE_KEYS_TARGET = "WhiteKeys"
RU_OTHER_TARGET = "RU_other"

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

CHANNEL_TEXT = "t.me/freekesha21"

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


def iter_links(path: Path):
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        yield line


def dedupe_keep_order(rows: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for row in rows:
        if row in seen:
            continue
        seen.add(row)
        out.append(row)
    return out


def prioritize_vless(rows: List[str]) -> List[str]:
    vless_rows = [row for row in rows if row.startswith("vless://")]
    other_rows = [row for row in rows if not row.startswith("vless://")]
    return vless_rows + other_rows


def extract_flag_from_text(text: str) -> str:
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


def rewrite_desc(line: str, idx: int, channel: str) -> str:
    row = line.strip()
    if not row:
        return ""
    if "#" in row:
        base, frag = row.split("#", 1)
    else:
        base, frag = row, ""
    flag = extract_flag_from_text(frag)
    new_desc = f"{channel} - {idx} {flag}"
    return f"{base}#{quote(new_desc, safe=' -')}"


def resolve_source_dir() -> Path:
    if PRIMARY_SOURCE_DIR.exists():
        return PRIMARY_SOURCE_DIR
    if FALLBACK_SOURCE_DIR.exists():
        print(f"[warn] {PRIMARY_SOURCE_DIR} not found, using {FALLBACK_SOURCE_DIR}")
        return FALLBACK_SOURCE_DIR
    if LEGACY_SOURCE_DIR.exists():
        print(f"[warn] {PRIMARY_SOURCE_DIR} not found, using legacy {LEGACY_SOURCE_DIR}")
        return LEGACY_SOURCE_DIR
    return PRIMARY_SOURCE_DIR


def next_day_filename(now: datetime) -> str:
    next_idx = (now.weekday() + 1) % 7
    return DAY_FILES[next_idx]


def build_header(file_title: str, updated_at: str) -> str:
    return (
        f"#announce: Обновлено: {updated_at}\n"
        "#profile-web-page-url: https://github.com/terik21/HiddifySubs-VlessKeys\n"
        f"#profile-title: {file_title}\n"
        "#support-url: https://t.me/freekesha21\n"
        "#profile-update-interval: 1\n\n\n"
    )


def write_target(path: Path, keys: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = build_header(file_title=path.name, updated_at=updated_at)
    body = "\n".join(keys)
    text = header + body + ("\n" if body else "")
    path.write_text(text, encoding="utf-8")


def load_rows(path: Path) -> List[str]:
    if not path.exists():
        print(f"[warn] source file not found: {path}")
        return []
    rows = list(iter_links(path))
    print(f"[info] loaded {path.name}: {len(rows)} keys")
    return rows


def main() -> int:
    top_dir = resolve_source_dir()
    if not top_dir.exists():
        print(f"[error] source dir not found: {top_dir}")
        return 1
    if not GIT_DIR.exists():
        print(f"[error] git dir not found: {GIT_DIR}")
        return 1

    # WhiteKeys must be built from top files (step 4 output).
    non_ru_vless = load_rows(top_dir / VLESS_SOURCE)
    ru_vless_top = load_rows(top_dir / VLESS_RU_SOURCE)

    # RU_other should contain remaining RU keys that were not selected into WhiteKeys.
    live_dir = FALLBACK_SOURCE_DIR if FALLBACK_SOURCE_DIR.exists() else top_dir
    ru_vless_live = load_rows(live_dir / VLESS_RU_SOURCE)

    ordinary_rows = dedupe_keep_order(non_ru_vless)
    white_rows = prioritize_vless(dedupe_keep_order(ru_vless_top))
    ru_pool_rows = dedupe_keep_order(ru_vless_live)
    white_set = set(white_rows)
    ru_rows_raw = [row for row in ru_pool_rows if row not in white_set]
    ru_rows = [rewrite_desc(row, i + 1, CHANNEL_TEXT) for i, row in enumerate(ru_rows_raw)]

    targets: Dict[str, Path] = {
        "ordinary": GIT_DIR / next_day_filename(datetime.now()),
        "white": GIT_DIR / WHITE_KEYS_TARGET,
        "ru": GIT_DIR / RU_OTHER_TARGET,
    }

    write_target(targets["ordinary"], ordinary_rows)
    print(f"[ok] written {targets['ordinary']} ({len(ordinary_rows)} keys)")

    write_target(targets["white"], white_rows)
    print(f"[ok] written {targets['white']} ({len(white_rows)} keys)")

    write_target(targets["ru"], ru_rows)
    print(f"[ok] written {targets['ru']} ({len(ru_rows)} keys)")

    print("[done] git files updated from top live keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
