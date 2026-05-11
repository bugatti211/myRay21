#!/usr/bin/env python3
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# ===== Settings =====
PRIMARY_SOURCE_DIR = Path("file/5TopLiveKeys")
FALLBACK_SOURCE_DIR = Path("file/4LiveKeys")
LEGACY_SOURCE_DIR = Path("file/3KeysFromGit")
GIT_DIR = Path("git")

VLESS_SOURCE = "vless_ping_ok.txt"
SS_SOURCE = "ss_ping_ok.txt"
VLESS_RU_SOURCE = "vless_RU_ping_ok.txt"
SS_RU_SOURCE = "ss_RU_ping_ok.txt"

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
    source_dir = resolve_source_dir()
    if not source_dir.exists():
        print(f"[error] source dir not found: {source_dir}")
        return 1
    if not GIT_DIR.exists():
        print(f"[error] git dir not found: {GIT_DIR}")
        return 1

    non_ru_vless = load_rows(source_dir / VLESS_SOURCE)
    non_ru_ss = load_rows(source_dir / SS_SOURCE)
    ru_vless = load_rows(source_dir / VLESS_RU_SOURCE)
    ru_ss = load_rows(source_dir / SS_RU_SOURCE)

    ordinary_rows = dedupe_keep_order(non_ru_vless)
    white_rows = dedupe_keep_order(ru_vless)
    ru_rows = dedupe_keep_order(ru_vless + ru_ss)

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
