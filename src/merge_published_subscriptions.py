#!/usr/bin/env python3
import argparse
import subprocess
from pathlib import Path
from typing import Callable, Iterable, List, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from pipeline_shared_tools import dedupe_keys_by_endpoint, extract_key_lines, key_endpoint
import write_git_publish_files as publisher


DEFAULT_REMOTE_BASE = (
    "https://raw.githubusercontent.com/terik21/"
    "HiddifySubs-VlessKeys/main"
)
DEFAULT_KEYS_DIR = Path("file/3KeysFromGit")
DEFAULT_LOCAL_GIT_DIR = Path("git")

MAIN_TARGET = "main"
WHITE_KEYS_TARGET = "WhiteKeys"
WHITE_KEYS_2_TARGET = "WhiteKeys2"
LEGACY_DAY_TARGETS = (
    "1Mond",
    "2Tues",
    "3Wend",
    "4Thur",
    "5Frid",
    "6Satu",
    "7Sand",
)
LEGACY_WHITE_KEYS_2_TARGET = "RU_other"

PUBLISHED_MAIN_FILE = "published_main.txt"
PUBLISHED_WHITE_KEYS_FILE = "published_WhiteKeys.txt"
PUBLISHED_WHITE_KEYS_2_FILE = "published_WhiteKeys2.txt"

VLESS_PREFIXES = ("vless://", "hysteria2://", "hy2://")
RU_PREFIXES = ("vless://", "hysteria2://", "hy2://")

TextFetcher = Callable[[str, float], str]


def fetch_url_text(url: str, timeout: float) -> str:
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError):
        result = subprocess.run(
            ["curl", "-fLsS", "--max-time", str(timeout), url],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or f"curl exit code {result.returncode}"
            raise RuntimeError(message)
        return result.stdout


def filter_protocols(keys: Iterable[str], prefixes: Sequence[str]) -> List[str]:
    return dedupe_keys_by_endpoint(
        [key for key in keys if key.startswith(tuple(prefixes))]
    )


def read_local_subscription(path: Path, prefixes: Sequence[str]) -> List[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    return filter_protocols(extract_key_lines(text), prefixes)


def read_subscription_rows(path: Path) -> List[str]:
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(
            encoding="utf-8",
            errors="ignore",
        ).splitlines()
        if line.strip() and not line.startswith("#")
    ]


def normalize_local_target(path: Path, rows: Sequence[str]) -> bool:
    normalized = dedupe_keys_by_endpoint(rows)
    if read_subscription_rows(path) == normalized:
        return False
    publisher.write_target(path, normalized)
    return True


def migrate_local_subscription_names(local_git_dir: Path) -> dict:
    """Rename legacy publications locally without dropping any stored keys."""
    created = []
    removed = []
    normalized = []

    main_path = local_git_dir / MAIN_TARGET
    day_paths = [local_git_dir / name for name in LEGACY_DAY_TARGETS]
    if not main_path.exists():
        main_rows: List[str] = []
        for path in day_paths:
            main_rows.extend(read_local_subscription(path, VLESS_PREFIXES))
        main_rows = dedupe_keys_by_endpoint(main_rows)
        if main_rows:
            publisher.write_target(main_path, main_rows)
            created.append(MAIN_TARGET)

    if main_path.exists() and read_local_subscription(main_path, VLESS_PREFIXES):
        for path in day_paths:
            if path.exists():
                path.unlink()
                removed.append(path.name)

    white2_path = local_git_dir / WHITE_KEYS_2_TARGET
    legacy_white2_path = local_git_dir / LEGACY_WHITE_KEYS_2_TARGET
    if not white2_path.exists():
        white2_rows = read_local_subscription(
            legacy_white2_path,
            RU_PREFIXES,
        )
        if white2_rows:
            publisher.write_target(white2_path, white2_rows)
            created.append(WHITE_KEYS_2_TARGET)

    if (
        white2_path.exists()
        and read_local_subscription(white2_path, RU_PREFIXES)
        and legacy_white2_path.exists()
    ):
        legacy_white2_path.unlink()
        removed.append(LEGACY_WHITE_KEYS_2_TARGET)

    white_path = local_git_dir / WHITE_KEYS_TARGET
    white_rows = read_local_subscription(white_path, RU_PREFIXES)
    if white_path.exists() and normalize_local_target(white_path, white_rows):
        normalized.append(WHITE_KEYS_TARGET)

    white_ids = {key_endpoint(key) for key in white_rows}
    white2_rows = [
        key
        for key in read_local_subscription(white2_path, RU_PREFIXES)
        if key_endpoint(key) not in white_ids
    ]
    if white2_path.exists() and normalize_local_target(white2_path, white2_rows):
        normalized.append(WHITE_KEYS_2_TARGET)

    ru_ids = white_ids | {key_endpoint(key) for key in white2_rows}
    main_rows = [
        key
        for key in read_local_subscription(main_path, VLESS_PREFIXES)
        if key_endpoint(key) not in ru_ids
    ]
    if main_path.exists() and normalize_local_target(main_path, main_rows):
        normalized.append(MAIN_TARGET)

    if created:
        print(f"[migration] created local subscriptions: {', '.join(created)}")
    if removed:
        print(f"[migration] removed legacy files: {', '.join(removed)}")
    if normalized:
        print(
            f"[migration] normalized local subscriptions: "
            f"{', '.join(normalized)}"
        )
    return {
        "created": created,
        "removed": removed,
        "normalized": normalized,
    }


def download_subscription(
    remote_base: str,
    name: str,
    prefixes: Sequence[str],
    timeout: float,
    fetcher: TextFetcher,
) -> List[str]:
    url = f"{remote_base.rstrip('/')}/{name}"
    try:
        keys = filter_protocols(extract_key_lines(fetcher(url, timeout)), prefixes)
    except Exception as exc:
        print(f"[warn] cannot download {url}: {exc}")
        return []
    if keys:
        print(f"[download] {name}: {len(keys)} keys")
    else:
        print(f"[warn] downloaded subscription has no supported keys: {url}")
    return keys


def load_published_group(
    remote_base: str,
    primary_names: Sequence[str],
    legacy_names: Sequence[str],
    local_git_dir: Path,
    prefixes: Sequence[str],
    timeout: float,
    fetcher: TextFetcher,
) -> List[str]:
    primary_rows: List[str] = []
    for name in primary_names:
        primary_rows.extend(
            download_subscription(
                remote_base,
                name,
                prefixes,
                timeout,
                fetcher,
            )
        )
    primary_rows = dedupe_keys_by_endpoint(primary_rows)
    if primary_rows:
        return primary_rows

    local_primary_rows: List[str] = []
    for name in primary_names:
        local_primary_rows.extend(
            read_local_subscription(local_git_dir / name, prefixes)
        )
    local_primary_rows = dedupe_keys_by_endpoint(local_primary_rows)
    if local_primary_rows:
        print(
            f"[fallback] using current local published files from "
            f"{local_git_dir}"
        )
        return local_primary_rows

    legacy_rows: List[str] = []
    for name in legacy_names:
        legacy_rows.extend(
            download_subscription(
                remote_base,
                name,
                prefixes,
                timeout,
                fetcher,
            )
        )
    legacy_rows = dedupe_keys_by_endpoint(legacy_rows)
    if legacy_rows:
        print(
            f"[migration] using legacy published files: "
            f"{', '.join(legacy_names)}"
        )
        return legacy_rows

    local_legacy_rows: List[str] = []
    for name in legacy_names:
        local_legacy_rows.extend(
            read_local_subscription(local_git_dir / name, prefixes)
        )
    local_legacy_rows = dedupe_keys_by_endpoint(local_legacy_rows)
    if local_legacy_rows:
        print(
            f"[fallback] using legacy local published files from "
            f"{local_git_dir}"
        )
        return local_legacy_rows

    raise RuntimeError(
        "cannot load published subscription from remote or local files: "
        + ", ".join((*primary_names, *legacy_names))
    )


def write_keys(path: Path, keys: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(keys) + ("\n" if keys else ""),
        encoding="utf-8",
    )


def read_generated_keys(path: Path, prefixes: Sequence[str]) -> List[str]:
    if not path.exists():
        return []
    return filter_protocols(
        [
            line.strip()
            for line in path.read_text(
                encoding="utf-8",
                errors="ignore",
            ).splitlines()
            if line.strip()
        ],
        prefixes,
    )


def refresh_published_subscriptions(
    remote_base: str = DEFAULT_REMOTE_BASE,
    keys_dir: Path = DEFAULT_KEYS_DIR,
    local_git_dir: Path = DEFAULT_LOCAL_GIT_DIR,
    timeout: float = 30.0,
    fetcher: TextFetcher = fetch_url_text,
) -> dict:
    migrate_local_subscription_names(local_git_dir)

    previous_main = load_published_group(
        remote_base,
        (MAIN_TARGET,),
        LEGACY_DAY_TARGETS,
        local_git_dir,
        VLESS_PREFIXES,
        timeout,
        fetcher,
    )
    previous_white = load_published_group(
        remote_base,
        (WHITE_KEYS_TARGET,),
        (),
        local_git_dir,
        RU_PREFIXES,
        timeout,
        fetcher,
    )
    previous_white2 = load_published_group(
        remote_base,
        (WHITE_KEYS_2_TARGET,),
        (LEGACY_WHITE_KEYS_2_TARGET,),
        local_git_dir,
        RU_PREFIXES,
        timeout,
        fetcher,
    )

    white_ids = {key_endpoint(key) for key in previous_white}
    previous_white2 = [
        key for key in previous_white2 if key_endpoint(key) not in white_ids
    ]
    ru_previous = dedupe_keys_by_endpoint(previous_white + previous_white2)
    ru_ids = {key_endpoint(key) for key in ru_previous}
    previous_main = [
        key for key in previous_main if key_endpoint(key) not in ru_ids
    ]

    new_main = read_generated_keys(keys_dir / "vless.txt", VLESS_PREFIXES)
    new_ru = read_generated_keys(keys_dir / "vless_RU.txt", RU_PREFIXES)

    merged_ru = dedupe_keys_by_endpoint(ru_previous + new_ru)
    merged_ru_ids = {key_endpoint(key) for key in merged_ru}
    merged_main = dedupe_keys_by_endpoint(
        previous_main
        + [
            key
            for key in new_main
            if key_endpoint(key) not in merged_ru_ids
        ]
    )

    write_keys(keys_dir / PUBLISHED_MAIN_FILE, previous_main)
    write_keys(keys_dir / PUBLISHED_WHITE_KEYS_FILE, previous_white)
    write_keys(keys_dir / PUBLISHED_WHITE_KEYS_2_FILE, previous_white2)
    write_keys(keys_dir / "vless.txt", merged_main)
    write_keys(keys_dir / "vless_RU.txt", merged_ru)

    print(
        f"[carry-forward] main: old={len(previous_main)}, "
        f"merged={len(merged_main)}"
    )
    print(
        f"[carry-forward] WhiteKeys: old={len(previous_white)}, "
        f"WhiteKeys2: old={len(previous_white2)}, "
        f"RU merged={len(merged_ru)}"
    )
    return {
        "previous_main": len(previous_main),
        "previous_white": len(previous_white),
        "previous_white2": len(previous_white2),
        "merged_main": len(merged_main),
        "merged_ru": len(merged_ru),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download currently published subscriptions and prepend their "
            "keys to the next Xray check."
        )
    )
    parser.add_argument("--remote-base", default=DEFAULT_REMOTE_BASE)
    parser.add_argument("--keys-dir", type=Path, default=DEFAULT_KEYS_DIR)
    parser.add_argument(
        "--local-git-dir",
        type=Path,
        default=DEFAULT_LOCAL_GIT_DIR,
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        refresh_published_subscriptions(
            remote_base=args.remote_base,
            keys_dir=args.keys_dir,
            local_git_dir=args.local_git_dir,
            timeout=args.timeout,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"[error] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
