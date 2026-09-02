#!/usr/bin/env python3
"""Shared parsing and extraction helpers for the active pipeline."""

import base64
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote
from urllib.request import urlopen


URL_RE = re.compile(r"^https?://\S+$")
RU_WORD_RE = re.compile(r"\b(RU|RUS|RUSSIA)\b", re.IGNORECASE)
HYSTERIA_PREFIXES = ("hysteria2://", "hy2://")
TROJAN_PREFIX = "trojan://"
KEY_PREFIXES = ("vless://", TROJAN_PREFIX, "ss://", *HYSTERIA_PREFIXES)


def read_subscription_urls(path: Path):
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return list(dict.fromkeys(line for line in lines if URL_RE.match(line)))


def parse_base64_subscription(text: str):
    compact = "".join(text.split())
    if not compact or any(prefix in text for prefix in KEY_PREFIXES):
        return None
    try:
        padded = compact + ("=" * ((4 - len(compact) % 4) % 4))
        decoded = base64.b64decode(
            padded,
            altchars=b"-_",
            validate=False,
        ).decode("utf-8", errors="replace")
    except Exception:
        return None
    return decoded if any(prefix in decoded for prefix in KEY_PREFIXES) else None


def key_endpoint(key: str) -> str:
    """Return the connection URI without its display-only fragment."""
    return key.strip().split("#", 1)[0]


def extract_key_lines(text: str):
    decoded = parse_base64_subscription(text)
    if decoded is not None:
        text = decoded

    keys = []
    seen_endpoints = set()
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line or not line.startswith(KEY_PREFIXES):
            continue
        endpoint = key_endpoint(line)
        if endpoint in seen_endpoints:
            continue
        seen_endpoints.add(endpoint)
        keys.append(line)
    return keys


def dedupe_keys_by_endpoint(keys):
    seen = set()
    unique = []
    for key in keys:
        endpoint = key_endpoint(key)
        if not endpoint or endpoint in seen:
            continue
        seen.add(endpoint)
        unique.append(key)
    return unique


def read_top_urls(path: Path):
    return read_subscription_urls(path)


def fetch_lines(url: str):
    try:
        with urlopen(url, timeout=30) as response:
            text = response.read().decode("utf-8", errors="replace")
    except Exception:
        result = subprocess.run(
            ["curl", "-fL", "--max-time", "30", url],
            check=True,
            capture_output=True,
            text=True,
        )
        text = result.stdout
    return extract_key_lines(text)


def is_ru_key(key: str):
    decoded = unquote(key)
    if "🇷🇺" in decoded or "%F0%9F%87%B7%F0%9F%87%BA" in key.upper():
        return True
    description = decoded.split("#", 1)[1] if "#" in decoded else ""
    return bool(RU_WORD_RE.search(description))


def extract_keys_from_top15(
    top15_path: Path,
    output_dir: Path,
    include_ss: bool = True,
):
    urls = read_top_urls(top15_path)
    vless_keys = []
    ss_keys = []
    vless_ru_keys = []
    trojan_keys = []
    failed = []

    for url in urls:
        try:
            lines = fetch_lines(url)
        except Exception as exc:
            failed.append((url, str(exc)))
            continue

        for line in lines:
            if line.startswith(("vless://", *HYSTERIA_PREFIXES)):
                if is_ru_key(line):
                    vless_ru_keys.append(line)
                else:
                    vless_keys.append(line)
            elif line.startswith(TROJAN_PREFIX):
                trojan_keys.append(line)
            elif line.startswith("ss://") and include_ss and not is_ru_key(line):
                ss_keys.append(line)

    output_dir.mkdir(parents=True, exist_ok=True)
    vless_keys = dedupe_keys_by_endpoint(vless_keys)
    ss_keys = dedupe_keys_by_endpoint(ss_keys)
    vless_ru_keys = dedupe_keys_by_endpoint(vless_ru_keys)
    trojan_keys = dedupe_keys_by_endpoint(trojan_keys)
    ru_endpoints = {key_endpoint(key) for key in vless_ru_keys}
    vless_keys = [key for key in vless_keys if key_endpoint(key) not in ru_endpoints]

    (output_dir / "vless.txt").write_text(
        "\n".join(vless_keys) + ("\n" if vless_keys else ""),
        encoding="utf-8",
    )
    ss_path = output_dir / "ss.txt"
    if include_ss:
        ss_path.write_text("\n".join(ss_keys) + ("\n" if ss_keys else ""), encoding="utf-8")
    else:
        ss_path.unlink(missing_ok=True)
    (output_dir / "vless_RU.txt").write_text(
        "\n".join(vless_ru_keys) + ("\n" if vless_ru_keys else ""),
        encoding="utf-8",
    )
    (output_dir / "trojan.txt").write_text(
        "\n".join(trojan_keys) + ("\n" if trojan_keys else ""),
        encoding="utf-8",
    )

    return {
        "urls_total": len(urls),
        "failed": failed,
        "vless_total": len(vless_keys),
        "ss_total": len(ss_keys),
        "vless_ru": len(vless_ru_keys),
        "trojan_total": len(trojan_keys),
    }
