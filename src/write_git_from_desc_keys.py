#!/usr/bin/env python3
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# ===== Settings =====
SOURCE_DIR = Path("file/desc_keys")
FALLBACK_SOURCE_DIR = Path("file/deck_keys")
GIT_DIR = Path("git")

VLESS_SOURCE = "vless.txt"
KEYS_SOURCE = "keys.txt"
RU_SOURCE = "RU_keys.txt"

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


def resolve_source_dir() -> Path:
    if SOURCE_DIR.exists():
        return SOURCE_DIR
    if FALLBACK_SOURCE_DIR.exists():
        print(f"[warn] {SOURCE_DIR} not found, using {FALLBACK_SOURCE_DIR}")
        return FALLBACK_SOURCE_DIR
    return SOURCE_DIR


def next_day_filename(now: datetime) -> str:
    # Python: Monday=0 ... Sunday=6
    # Need file for NEXT day.
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


def main() -> int:
    source_dir = resolve_source_dir()
    if not source_dir.exists():
        print(f"[error] source dir not found: {source_dir}")
        return 1
    if not GIT_DIR.exists():
        print(f"[error] git dir not found: {GIT_DIR}")
        return 1

    now = datetime.now()
    targets: Dict[str, Path] = {
        "vless": GIT_DIR / next_day_filename(now),
        "keys": GIT_DIR / WHITE_KEYS_TARGET,
        "ru": GIT_DIR / RU_OTHER_TARGET,
    }

    sources: Dict[str, Path] = {
        "vless": source_dir / VLESS_SOURCE,
        "keys": source_dir / KEYS_SOURCE,
        "ru": source_dir / RU_SOURCE,
    }

    loaded: Dict[str, List[str]] = {}
    for name, src in sources.items():
        if not src.exists():
            print(f"[warn] source file not found: {src}")
            loaded[name] = []
            continue
        loaded[name] = list(iter_links(src))
        print(f"[info] loaded {name}: {len(loaded[name])} keys")

    for name in ("vless", "keys", "ru"):
        dst = targets[name]
        write_target(dst, loaded[name])
        print(f"[ok] written {dst} ({len(loaded[name])} keys)")

    print("[done] git files updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
