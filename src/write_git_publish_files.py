#!/usr/bin/env python3
from datetime import datetime
from pathlib import Path
<<<<<<< HEAD
from typing import Dict, List
=======
from typing import Dict, List, Sequence
>>>>>>> authostart
import re
from urllib.parse import quote, unquote

# ===== Settings =====
PRIMARY_SOURCE_DIR = Path("file/5TopLiveKeys")
FALLBACK_SOURCE_DIR = Path("file/4LiveKeys")
LEGACY_SOURCE_DIR = Path("file/3KeysFromGit")
GIT_DIR = Path("git")

VLESS_SOURCE = "vless_ping_ok.txt"
<<<<<<< HEAD
SS_SOURCE = "ss_ping_ok.txt"
VLESS_RU_SOURCE = "vless_RU_ping_ok.txt"
SS_RU_SOURCE = "ss_RU_ping_ok.txt"

WHITE_KEYS_TARGET = "WhiteKeys"
RU_OTHER_TARGET = "RU_other"

DAY_FILES = [
=======
VLESS_RU_SOURCE = "vless_RU_ping_ok.txt"

MAIN_TARGET = "main"
WHITE_KEYS_TARGET = "WhiteKeys"
WHITE_KEYS_2_TARGET = "WhiteKeys2"
LEGACY_TARGETS = (
>>>>>>> authostart
    "1Mond",
    "2Tues",
    "3Wend",
    "4Thur",
    "5Frid",
    "6Satu",
    "7Sand",
<<<<<<< HEAD
]
=======
    "RU_other",
)

PUBLISHED_MAIN_SOURCE = "published_main.txt"
PUBLISHED_WHITE_KEYS_SOURCE = "published_WhiteKeys.txt"

MAIN_PREFIXES = ("vless://", "hysteria2://", "hy2://")
RU_PREFIXES = ("vless://", "hysteria2://", "hy2://")
>>>>>>> authostart
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
<<<<<<< HEAD
        if row in seen:
            continue
        seen.add(row)
=======
        endpoint = connection_id(row)
        if not endpoint or endpoint in seen:
            continue
        seen.add(endpoint)
>>>>>>> authostart
        out.append(row)
    return out


<<<<<<< HEAD
=======
def connection_id(row: str) -> str:
    return row.strip().split("#", 1)[0]


def prioritize_vless(rows: List[str]) -> List[str]:
    vless_rows = [row for row in rows if row.startswith("vless://")]
    other_rows = [row for row in rows if not row.startswith("vless://")]
    return vless_rows + other_rows


def filter_protocols(rows: Sequence[str], prefixes: Sequence[str]) -> List[str]:
    return [row for row in rows if row.startswith(tuple(prefixes))]


def live_published_rows(
    published_path: Path,
    live_rows: Sequence[str],
) -> List[str]:
    if not published_path.exists():
        return []
    live_by_id = {
        connection_id(row): row
        for row in live_rows
        if connection_id(row)
    }
    retained = []
    for row in iter_links(published_path):
        endpoint = connection_id(row)
        live_row = live_by_id.get(endpoint)
        if live_row is not None:
            retained.append(live_row)
    return dedupe_keep_order(retained)


>>>>>>> authostart
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


<<<<<<< HEAD
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
=======
def resolve_source_file(filename: str, legacy_filename: str) -> Path:
    candidates = [
        PRIMARY_SOURCE_DIR / filename,
        FALLBACK_SOURCE_DIR / filename,
        LEGACY_SOURCE_DIR / legacy_filename,
    ]
    first_existing = None
    for candidate in candidates:
        if not candidate.exists():
            continue
        if first_existing is None:
            first_existing = candidate
        if any(iter_links(candidate)):
            if candidate != candidates[0]:
                print(f"[warn] using fallback source: {candidate}")
            return candidate
    return first_existing or candidates[0]
>>>>>>> authostart


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
<<<<<<< HEAD
    top_dir = resolve_source_dir()
    if not top_dir.exists():
        print(f"[error] source dir not found: {top_dir}")
        return 1
=======
>>>>>>> authostart
    if not GIT_DIR.exists():
        print(f"[error] git dir not found: {GIT_DIR}")
        return 1

<<<<<<< HEAD
    # WhiteKeys must be built from top files (step 4 output).
    non_ru_vless = load_rows(top_dir / VLESS_SOURCE)
    ru_vless_top = load_rows(top_dir / VLESS_RU_SOURCE)

    # RU_other should contain remaining RU keys that were not selected into WhiteKeys.
    live_dir = FALLBACK_SOURCE_DIR if FALLBACK_SOURCE_DIR.exists() else top_dir
    ru_vless_live = load_rows(live_dir / VLESS_RU_SOURCE)
    ru_ss_live = load_rows(live_dir / SS_RU_SOURCE)

    ordinary_rows = dedupe_keep_order(non_ru_vless)
    white_rows = dedupe_keep_order(ru_vless_top)
    ru_pool_rows = dedupe_keep_order(ru_vless_live + ru_ss_live)
    white_set = set(white_rows)
    ru_rows_raw = [row for row in ru_pool_rows if row not in white_set]
    ru_rows = [rewrite_desc(row, i + 1, CHANNEL_TEXT) for i, row in enumerate(ru_rows_raw)]

    targets: Dict[str, Path] = {
        "ordinary": GIT_DIR / next_day_filename(datetime.now()),
        "white": GIT_DIR / WHITE_KEYS_TARGET,
        "ru": GIT_DIR / RU_OTHER_TARGET,
=======
    non_ru_source = resolve_source_file(VLESS_SOURCE, "vless.txt")
    ru_top_source = resolve_source_file(VLESS_RU_SOURCE, "vless_RU.txt")
    non_ru_vless = load_rows(non_ru_source)
    ru_vless_top = load_rows(ru_top_source)

    ordinary_live_source = FALLBACK_SOURCE_DIR / VLESS_SOURCE
    if not ordinary_live_source.exists() or not any(iter_links(ordinary_live_source)):
        print(f"[warn] live main source unavailable, using {non_ru_source}")
        ordinary_live_source = non_ru_source
    ordinary_live = load_rows(ordinary_live_source)

    # WhiteKeys2 contains remaining RU keys that were not selected into WhiteKeys.
    ru_live_source = FALLBACK_SOURCE_DIR / VLESS_RU_SOURCE
    if not ru_live_source.exists() or not any(iter_links(ru_live_source)):
        print(f"[warn] live RU source unavailable, using {ru_top_source}")
        ru_live_source = ru_top_source
    ru_vless_live = load_rows(ru_live_source)

    ordinary_top_rows = dedupe_keep_order(
        filter_protocols(non_ru_vless, MAIN_PREFIXES)
    )
    ordinary_live_rows = dedupe_keep_order(
        filter_protocols(ordinary_live, MAIN_PREFIXES)
    )
    retained_main_rows = live_published_rows(
        LEGACY_SOURCE_DIR / PUBLISHED_MAIN_SOURCE,
        ordinary_live_rows,
    )
    ordinary_rows = dedupe_keep_order(ordinary_top_rows + retained_main_rows)

    white_top_rows = dedupe_keep_order(
        filter_protocols(ru_vless_top, RU_PREFIXES)
    )
    ru_pool_rows = dedupe_keep_order(
        filter_protocols(ru_vless_live, RU_PREFIXES)
    )
    retained_white_rows = live_published_rows(
        LEGACY_SOURCE_DIR / PUBLISHED_WHITE_KEYS_SOURCE,
        ru_pool_rows,
    )
    white_rows = prioritize_vless(
        dedupe_keep_order(white_top_rows + retained_white_rows)
    )
    white_set = {connection_id(row) for row in white_rows}
    white2_rows_raw = [
        row
        for row in ru_pool_rows
        if connection_id(row) not in white_set
    ]
    white2_rows = [
        rewrite_desc(row, i + 1, CHANNEL_TEXT)
        for i, row in enumerate(white2_rows_raw)
    ]

    if not ordinary_rows:
        print(f"[error] no ordinary VLESS keys in {non_ru_source}; refusing to overwrite published files")
        return 1
    if not white_rows:
        print(f"[error] no RU VLESS/Hysteria 2 keys in {ru_top_source}; refusing to overwrite published files")
        return 1

    targets: Dict[str, Path] = {
        "ordinary": GIT_DIR / MAIN_TARGET,
        "white": GIT_DIR / WHITE_KEYS_TARGET,
        "white2": GIT_DIR / WHITE_KEYS_2_TARGET,
>>>>>>> authostart
    }

    write_target(targets["ordinary"], ordinary_rows)
    print(f"[ok] written {targets['ordinary']} ({len(ordinary_rows)} keys)")

    write_target(targets["white"], white_rows)
    print(f"[ok] written {targets['white']} ({len(white_rows)} keys)")

<<<<<<< HEAD
    write_target(targets["ru"], ru_rows)
    print(f"[ok] written {targets['ru']} ({len(ru_rows)} keys)")

    print("[done] git files updated from top live keys")
=======
    write_target(targets["white2"], white2_rows)
    print(f"[ok] written {targets['white2']} ({len(white2_rows)} keys)")

    for legacy_name in LEGACY_TARGETS:
        legacy_path = GIT_DIR / legacy_name
        if legacy_path.exists():
            legacy_path.unlink()
            print(f"[migration] removed legacy subscription: {legacy_path}")

    print("[done] main, WhiteKeys and WhiteKeys2 updated from live keys")
>>>>>>> authostart
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
