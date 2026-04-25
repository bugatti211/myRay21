#!/usr/bin/env python3
import concurrent.futures
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote, urldefrag

from check_keys import XRAY_BIN_PATH, TIMEOUT_SEC, iter_links, make_config, parse_link, reserve_port

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
MAX_WORKERS = 80
COUNTRY_TIMEOUT_SEC = TIMEOUT_SEC
DESCRIPTION_PREFIX = "t.me@freekesha21"
# ================================


@dataclass
class LinkCountry:
    source: str
    link: str
    country_code: str


def country_to_flag(country_code: str) -> str:
    code = (country_code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return "🏳️"
    return chr(127397 + ord(code[0])) + chr(127397 + ord(code[1]))


def with_description(link: str, seq_no: int, country_code: str) -> str:
    flag = country_to_flag(country_code)
    # Required format example: %F0%9F%87%B1%F0%9F%87%B9%20
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
    ]

    for cmd in commands:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            continue
        code = (result.stdout or "").strip().upper()
        if len(code) == 2 and code.isalpha():
            return code

    return "ZZ"


def detect_country_for_link(link: str, xray_bin: Path, timeout: float, xray_workdir: Path) -> str:
    parsed = parse_link(link)
    socks_port = reserve_port()
    config = make_config(parsed.outbound, socks_port)

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        import json

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

    total_links = sum(len(v) for v in links_by_source.values())
    print(f"[info] total keys for geodetect: {total_links}")

    detected: Dict[str, List[LinkCountry]] = {"ss": [], "vless": [], "keys": []}
    ru_pool: List[LinkCountry] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_meta = {}
        for source, links in links_by_source.items():
            for idx, link in enumerate(links):
                future = executor.submit(
                    detect_country_worker,
                    source,
                    link,
                    xray_bin_abs,
                    COUNTRY_TIMEOUT_SEC,
                    xray_workdir,
                )
                future_to_meta[future] = (source, idx)

        # Keep original order per source.
        ordered_results: Dict[str, Dict[int, LinkCountry]] = {"ss": {}, "vless": {}, "keys": {}}
        for future in concurrent.futures.as_completed(future_to_meta):
            source, idx = future_to_meta[future]
            try:
                row = future.result()
            except Exception:
                row = LinkCountry(source=source, link=links_by_source[source][idx], country_code="ZZ")
            ordered_results[source][idx] = row

    for source in ("ss", "vless", "keys"):
        for idx in range(len(links_by_source[source])):
            row = ordered_results[source].get(
                idx, LinkCountry(source=source, link=links_by_source[source][idx], country_code="ZZ")
            )
            code = row.country_code.upper()
            if source in {"ss", "vless"} and code == "RU":
                ru_pool.append(row)
            else:
                detected[source].append(row)

    ss_rows = detected["ss"][: OUTPUT_LIMITS["ss"]]
    vless_rows = detected["vless"][: OUTPUT_LIMITS["vless"]]
    keys_rows = detected["keys"][: OUTPUT_LIMITS["keys"]]

    write_deck_file(OUTPUT_FILES["ss"], ss_rows)
    write_deck_file(OUTPUT_FILES["vless"], vless_rows)
    write_deck_file(OUTPUT_FILES["keys"], keys_rows)
    write_deck_file(OUTPUT_FILES["ru"], ru_pool)

    print(
        "[done] deck files created: "
        f"ss={len(ss_rows)}, vless={len(vless_rows)}, "
        f"keys={len(keys_rows)}, RU_keys={len(ru_pool)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
