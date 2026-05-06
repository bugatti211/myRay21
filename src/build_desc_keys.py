#!/usr/bin/env python3
import concurrent.futures
import json
import os
import re
import subprocess
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urldefrag

try:
    from check_keys import XRAY_BIN_PATH, canonicalize_link, iter_links, make_config, parse_link, reserve_port
except ModuleNotFoundError:
    from src.check_keys import XRAY_BIN_PATH, canonicalize_link, iter_links, make_config, parse_link, reserve_port
try:
    from project_config import env_float, env_int
except ModuleNotFoundError:
    from src.project_config import env_float, env_int

# ===== Settings (edit here) =====
INPUT_DIR = Path("file/valid_keys")
OUTPUT_DIR = Path("file/desc_keys")
SOURCE_FILES = {
    "ss": INPUT_DIR / "ss.txt",
    "vless": INPUT_DIR / "vless.txt",
    "keys": INPUT_DIR / "keys.txt",
}
OUTPUT_FILES = {
    "ss": OUTPUT_DIR / "ss.txt",
    "vless": OUTPUT_DIR / "vless.txt",
    "keys": OUTPUT_DIR / "keys.txt",
    "ru": OUTPUT_DIR / "RU_keys.txt",
}
OUTPUT_LIMITS = {
    "ss": 10,
    "vless": 200,
    "keys": 200,
}
GEO_EXTRA_SCAN = {
    "ss": 25,
    "vless": 120,
    "keys": 80,
}
MAX_WORKERS = env_int("RAY_GEO_WORKERS", 40, minimum=1)
COUNTRY_TIMEOUT_SEC = env_float("RAY_GEO_TIMEOUT_SEC", 5.0, minimum=0.5)
DESCRIPTION_PREFIX = "t.me@freekesha21"

COUNTRY_CACHE_PATH = Path("file/cache/country_cache.json")
COUNTRY_CACHE_TTL_SEC = env_int("RAY_GEO_CACHE_TTL_SEC", 7 * 24 * 3600, minimum=60)
# ================================

FLAG_RE = re.compile(r"[\U0001F1E6-\U0001F1FF]{2}")


@dataclass
class LinkCountry:
    source: str
    link: str
    country_code: str


def load_country_cache(path: Path) -> Dict[str, Dict[str, object]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, object]] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, dict):
            out[key] = value
    return out


def save_country_cache(path: Path, cache: Dict[str, Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
        json.dump(cache, tmp, ensure_ascii=False)
        tmp.flush()
        tmp_name = tmp.name
    os.replace(tmp_name, path)


def get_cached_country(cache: Dict[str, Dict[str, object]], link: str, now_ts: float) -> Optional[str]:
    key = canonicalize_link(link)
    if not key:
        return None
    row = cache.get(key)
    if not row:
        return None
    checked_at = float(row.get("checked_at", 0.0))
    if now_ts - checked_at > COUNTRY_CACHE_TTL_SEC:
        return None
    code = str(row.get("country_code", "")).upper()
    if len(code) == 2 and code.isalpha():
        return code
    return None


def put_cached_country(cache: Dict[str, Dict[str, object]], link: str, country_code: str, now_ts: float) -> None:
    key = canonicalize_link(link)
    if not key:
        return
    code = (country_code or "ZZ").strip().upper()
    if len(code) != 2 or not code.isalpha():
        code = "ZZ"
    cache[key] = {
        "country_code": code,
        "checked_at": float(now_ts),
    }


def country_to_flag(country_code: str) -> str:
    code = (country_code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return "🏳️"
    return chr(127397 + ord(code[0])) + chr(127397 + ord(code[1]))


def extract_flag_from_link_description(link: str) -> Optional[str]:
    _, fragment = urldefrag((link or "").strip())
    if not fragment:
        return None
    desc = unquote(fragment)
    match = FLAG_RE.search(desc)
    if not match:
        return None
    return match.group(0)


def flag_to_country_code(flag: str) -> Optional[str]:
    if not flag or len(flag) != 2:
        return None
    a, b = ord(flag[0]), ord(flag[1])
    base = 127397
    start = ord("A")
    if not (127462 <= a <= 127487 and 127462 <= b <= 127487):
        return None
    return chr(a - base + start) + chr(b - base + start)


def with_description(link: str, seq_no: int, country_code: str) -> str:
    flag = extract_flag_from_link_description(link) or country_to_flag(country_code)
    flag_encoded = quote(flag + " ", safe="")
    clean_link, _ = urldefrag(link.strip())
    return f"{clean_link}#{DESCRIPTION_PREFIX} - {seq_no} {flag_encoded}"


def probe_country_via_socks(socks_port: int, timeout: float) -> str:
    proxy = f"socks5h://127.0.0.1:{socks_port}"
    commands = [
        [
            "curl",
            "--silent",
            "--show-error",
            "--max-time",
            str(timeout),
            "--proxy",
            proxy,
            "https://ipapi.co/country/",
        ],
        [
            "curl",
            "--silent",
            "--show-error",
            "--max-time",
            str(timeout),
            "--proxy",
            proxy,
            "https://ifconfig.co/country-iso",
        ],
        [
            "curl",
            "--silent",
            "--show-error",
            "--max-time",
            str(timeout),
            "--proxy",
            proxy,
            "https://ipwho.is/?fields=country_code",
        ],
    ]

    hits: List[str] = []
    for cmd in commands:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            continue
        raw = (result.stdout or "").strip()
        if raw.startswith("{"):
            try:
                data = json.loads(raw)
                raw = str(data.get("country_code", "")).strip()
            except Exception:
                raw = ""
        code = raw.upper()
        if len(code) == 2 and code.isalpha():
            hits.append(code)

    if not hits:
        return "ZZ"

    top_code, top_count = Counter(hits).most_common(1)[0]
    if top_count >= 2:
        return top_code

    # If providers disagree, keep first successful result to avoid dropping all geo labels.
    return hits[0]


def detect_country_for_link(link: str, xray_bin: Path, timeout: float, xray_workdir: Path) -> str:
    parsed = parse_link(link)
    socks_port = reserve_port()
    config = make_config(parsed.outbound, socks_port)

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        json.dump(config, tmp, ensure_ascii=False)
        tmp.flush()
        config_path = tmp.name

    proc: Optional[subprocess.Popen] = None
    try:
        proc = subprocess.Popen(
            [str(xray_bin), "run", "-c", config_path],
            cwd=str(xray_workdir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        boot_deadline = time.time() + min(3.0, timeout)
        while time.time() < boot_deadline:
            if proc.poll() is not None:
                return "ZZ"
            try:
                import socket

                with socket.create_connection(("127.0.0.1", socks_port), timeout=0.15):
                    break
            except OSError:
                time.sleep(0.08)
        else:
            return "ZZ"

        return probe_country_via_socks(socks_port=socks_port, timeout=timeout)
    except Exception:
        return "ZZ"
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.2)
            except subprocess.TimeoutExpired:
                proc.kill()
        try:
            os.unlink(config_path)
        except OSError:
            pass


def detect_country_worker(source: str, link: str, xray_bin: Path, timeout: float, xray_workdir: Path) -> LinkCountry:
    country_code = detect_country_for_link(
        link=link,
        xray_bin=xray_bin,
        timeout=timeout,
        xray_workdir=xray_workdir,
    )
    return LinkCountry(source=source, link=link, country_code=country_code)


def write_deck_file(path: Path, rows: List[LinkCountry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out_lines = [with_description(row.link, idx, row.country_code) for idx, row in enumerate(rows, start=1)]
    path.write_text("\n".join(out_lines), encoding="utf-8")


def build_scan_and_tail(links_by_source: Dict[str, List[str]]) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    scan_links: Dict[str, List[str]] = {}
    tail_links: Dict[str, List[str]] = {}

    for source, links in links_by_source.items():
        limit = OUTPUT_LIMITS.get(source, len(links))
        extra = GEO_EXTRA_SCAN.get(source, 0)
        scan_limit = min(len(links), limit + extra)
        scan_links[source] = links[:scan_limit]
        tail_links[source] = links[scan_limit:]

    return scan_links, tail_links


def main() -> int:
    xray_bin = XRAY_BIN_PATH
    if not xray_bin.exists():
        print(f"[error] Xray binary not found: {xray_bin}")
        return 1

    xray_bin_abs = xray_bin.resolve()
    xray_workdir = xray_bin_abs.parent

    links_by_source: Dict[str, List[str]] = {}
    for source, file_path in SOURCE_FILES.items():
        if not file_path.exists():
            print(f"[warn] missing input file: {file_path}")
            links_by_source[source] = []
            continue
        links_by_source[source] = list(iter_links(file_path))

    scan_links, tail_links = build_scan_and_tail(links_by_source)
    total_scan = sum(len(v) for v in scan_links.values())
    total_input = sum(len(v) for v in links_by_source.values())
    print(f"[info] total keys={total_input}, geodetect subset={total_scan}")

    country_cache = load_country_cache(COUNTRY_CACHE_PATH)
    now_ts = time.time()

    ordered_results: Dict[str, Dict[int, LinkCountry]] = {"ss": {}, "vless": {}, "keys": {}}
    run_dedupe: Dict[str, str] = {}
    stats = {"cache_hit": 0, "run_dedupe_hit": 0, "geo_detect": 0}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_meta = {}

        for source, links in scan_links.items():
            for idx, link in enumerate(links):
                existing_flag = extract_flag_from_link_description(link)
                if existing_flag:
                    existing_code = flag_to_country_code(existing_flag) or "ZZ"
                    ordered_results[source][idx] = LinkCountry(
                        source=source,
                        link=link,
                        country_code=existing_code,
                    )
                    normalized = canonicalize_link(link)
                    if normalized:
                        run_dedupe[normalized] = existing_code
                        put_cached_country(
                            country_cache,
                            link=link,
                            country_code=existing_code,
                            now_ts=now_ts,
                        )
                    continue

                normalized = canonicalize_link(link)
                if normalized and normalized in run_dedupe:
                    ordered_results[source][idx] = LinkCountry(
                        source=source,
                        link=link,
                        country_code=run_dedupe[normalized],
                    )
                    stats["run_dedupe_hit"] += 1
                    continue

                cached_code = get_cached_country(country_cache, link=link, now_ts=now_ts)
                if cached_code is not None:
                    ordered_results[source][idx] = LinkCountry(source=source, link=link, country_code=cached_code)
                    if normalized:
                        run_dedupe[normalized] = cached_code
                    stats["cache_hit"] += 1
                    continue

                future = executor.submit(
                    detect_country_worker,
                    source,
                    link,
                    xray_bin_abs,
                    COUNTRY_TIMEOUT_SEC,
                    xray_workdir,
                )
                future_to_meta[future] = (source, idx, link)
                stats["geo_detect"] += 1

        for future in concurrent.futures.as_completed(future_to_meta):
            source, idx, link = future_to_meta[future]
            try:
                row = future.result()
            except Exception:
                row = LinkCountry(source=source, link=link, country_code="ZZ")
            ordered_results[source][idx] = row
            normalized = canonicalize_link(row.link)
            if normalized:
                run_dedupe[normalized] = row.country_code
            put_cached_country(country_cache, link=row.link, country_code=row.country_code, now_ts=time.time())

    detected: Dict[str, List[LinkCountry]] = {"ss": [], "vless": [], "keys": []}
    ru_pool: List[LinkCountry] = []

    for source in ("ss", "vless", "keys"):
        links = scan_links[source]
        for idx in range(len(links)):
            row = ordered_results[source].get(idx, LinkCountry(source=source, link=links[idx], country_code="ZZ"))
            code = row.country_code.upper()
            if source in {"ss", "vless"} and code == "RU":
                ru_pool.append(row)
            else:
                detected[source].append(row)

    for source in ("ss", "vless", "keys"):
        limit = OUTPUT_LIMITS[source]
        if len(detected[source]) >= limit:
            continue

        missing = limit - len(detected[source])
        for link in tail_links[source][:missing]:
            detected[source].append(LinkCountry(source=source, link=link, country_code="ZZ"))

    ss_rows = detected["ss"][: OUTPUT_LIMITS["ss"]]
    vless_rows = detected["vless"][: OUTPUT_LIMITS["vless"]]
    keys_rows = detected["keys"][: OUTPUT_LIMITS["keys"]]

    write_deck_file(OUTPUT_FILES["ss"], ss_rows)
    write_deck_file(OUTPUT_FILES["vless"], vless_rows)
    write_deck_file(OUTPUT_FILES["keys"], keys_rows)
    write_deck_file(OUTPUT_FILES["ru"], ru_pool)

    save_country_cache(COUNTRY_CACHE_PATH, country_cache)

    print(
        "[done] deck files created: "
        f"ss={len(ss_rows)}, vless={len(vless_rows)}, "
        f"keys={len(keys_rows)}, RU_keys={len(ru_pool)}"
    )
    print(f"[stats] geo: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
