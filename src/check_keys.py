#!/usr/bin/env python3
import base64
import concurrent.futures
import hashlib
import json
import os
import multiprocessing
import random
import socket
import string
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, parse_qsl, unquote, urldefrag, urlencode, urlparse

try:
    from project_config import current_profile, env_float, env_int
except ModuleNotFoundError:
    from src.project_config import current_profile, env_float, env_int

# ===== Settings (edit here) =====
XRAY_BIN_PATH = Path("xrayFile/xray")
TEST_URL = "https://www.gstatic.com/generate_204"
PROFILE = current_profile()
DEFAULT_CHECK_TIMEOUT = 6.0 if PROFILE == "full" else 4.0
DEFAULT_PRECHECK_TIMEOUT = 1.8 if PROFILE == "full" else 1.0
TIMEOUT_SEC = env_float("RAY_CHECK_TIMEOUT_SEC", DEFAULT_CHECK_TIMEOUT, minimum=0.5)
MAX_WORKERS = env_int(
    "RAY_CHECK_WORKERS",
    min(60, max(8, multiprocessing.cpu_count() * 6)),
    minimum=1,
)
PRECHECK_TIMEOUT_SEC = env_float("RAY_PRECHECK_TIMEOUT_SEC", DEFAULT_PRECHECK_TIMEOUT, minimum=0.1)
LIMIT = env_int("RAY_CHECK_LIMIT", 0, minimum=0)  # 0 = all links
FAIL_STREAK_FOR_SKIP = 4
BASE_SKIP_AHEAD = 2
MAX_SKIP_AHEAD = 8

CACHE_PATH = Path("file/cache/check_cache.json")
OK_CACHE_TTL_SEC = env_int("RAY_CHECK_OK_CACHE_TTL_SEC", 8 * 3600, minimum=60)
FAIL_CACHE_TTL_SEC = env_int("RAY_CHECK_FAIL_CACHE_TTL_SEC", 90 * 60, minimum=60)

SOURCE_JOBS = [
    {
        "name": "ss",
        "input": Path("file/git_keys/default/ss.txt"),
        "output": Path("file/checked_keys/ss.txt"),
        "target": 100,
    },
    {
        "name": "vless",
        "input": Path("file/git_keys/default/vless.txt"),
        "output": Path("file/checked_keys/vless.txt"),
        "target": 500,
    },
    {
        "name": "keys",
        "input": Path("file/git_keys/whiteList/keys.txt"),
        "output": Path("file/checked_keys/keys.txt"),
        "target": 500,
    },
]

GIT_SUBS_DIR = Path("git")
DAY_FILES = [
    "1Mond",
    "2Tues",
    "3Wend",
    "4Thur",
    "5Frid",
    "6Satu",
    "7Sand",
]
PRIORITY_MULTIPLIER = 3

# ================================


@dataclass
class ParseResult:
    protocol: str
    outbound: Dict[str, Any]


def _q(query: Dict[str, List[str]], key: str, default: str = "") -> str:
    values = query.get(key)
    if not values:
        return default
    return values[0]


def _to_bool(value: str, default: bool = False) -> bool:
    if value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _split_csv(value: str) -> List[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _random_tag(prefix: str = "node") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}-{suffix}"


def parse_vless(link: str) -> ParseResult:
    parsed = urlparse(link)
    query = parse_qs(parsed.query)

    host = parsed.hostname
    port = parsed.port or 443
    user_id = unquote(parsed.username or "")
    if not host or not user_id:
        raise ValueError("VLESS link missing host or id")

    network = _q(query, "type", "tcp")
    security = _q(query, "security", "none")

    outbound: Dict[str, Any] = {
        "tag": _random_tag("vless"),
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": host,
                    "port": port,
                    "users": [
                        {
                            "id": user_id,
                            "encryption": _q(query, "encryption", "none"),
                        }
                    ],
                }
            ]
        },
        "streamSettings": {
            "network": network,
            "security": security,
        },
    }

    flow = _q(query, "flow")
    if flow:
        outbound["settings"]["vnext"][0]["users"][0]["flow"] = flow

    sni = _q(query, "sni") or _q(query, "serverName")
    fp = _q(query, "fp")
    alpn = _split_csv(_q(query, "alpn"))

    if security == "tls":
        tls_settings: Dict[str, Any] = {
            "allowInsecure": _to_bool(_q(query, "insecure") or _q(query, "allowInsecure"), False)
        }
        if sni:
            tls_settings["serverName"] = sni
        if alpn:
            tls_settings["alpn"] = alpn
        if fp:
            tls_settings["fingerprint"] = fp
        outbound["streamSettings"]["tlsSettings"] = tls_settings
    elif security == "reality":
        reality_settings: Dict[str, Any] = {}
        if sni:
            reality_settings["serverName"] = sni
        if fp:
            reality_settings["fingerprint"] = fp
        pbk = _q(query, "pbk")
        sid = _q(query, "sid")
        spx = _q(query, "spx")
        if pbk:
            reality_settings["publicKey"] = pbk
        if sid:
            reality_settings["shortId"] = sid
        if spx:
            reality_settings["spiderX"] = spx
        outbound["streamSettings"]["realitySettings"] = reality_settings

    if network == "tcp":
        header_type = _q(query, "headerType", "none")
        if header_type and header_type != "none":
            outbound["streamSettings"]["tcpSettings"] = {
                "header": {"type": header_type}
            }
    elif network == "ws":
        ws_settings: Dict[str, Any] = {"path": _q(query, "path", "/")}
        host_header = _q(query, "host")
        if host_header:
            ws_settings["headers"] = {"Host": host_header}
        outbound["streamSettings"]["wsSettings"] = ws_settings
    elif network == "grpc":
        grpc_settings: Dict[str, Any] = {
            "serviceName": _q(query, "serviceName")
        }
        authority = _q(query, "authority")
        if authority:
            grpc_settings["authority"] = authority
        mode = _q(query, "mode")
        if mode == "multi":
            grpc_settings["multiMode"] = True
        outbound["streamSettings"]["grpcSettings"] = grpc_settings
    elif network == "xhttp":
        xhttp_settings: Dict[str, Any] = {}
        path = _q(query, "path")
        host = _q(query, "host")
        mode = _q(query, "mode")
        extra = _q(query, "extra")
        if path:
            xhttp_settings["path"] = path
        if host:
            xhttp_settings["host"] = host
        if mode:
            xhttp_settings["mode"] = mode
        if extra and extra != "null":
            xhttp_settings["extra"] = extra
        if xhttp_settings:
            outbound["streamSettings"]["xhttpSettings"] = xhttp_settings
    elif network == "httpupgrade":
        hu_settings: Dict[str, Any] = {}
        path = _q(query, "path")
        host = _q(query, "host")
        if path:
            hu_settings["path"] = path
        if host:
            hu_settings["host"] = host
        outbound["streamSettings"]["httpupgradeSettings"] = hu_settings
    elif network == "splithttp":
        sh_settings: Dict[str, Any] = {}
        path = _q(query, "path")
        host = _q(query, "host")
        if path:
            sh_settings["path"] = path
        if host:
            sh_settings["host"] = host
        outbound["streamSettings"]["splithttpSettings"] = sh_settings

    return ParseResult(protocol="vless", outbound=outbound)


def parse_trojan(link: str) -> ParseResult:
    parsed = urlparse(link)
    query = parse_qs(parsed.query)

    host = parsed.hostname
    port = parsed.port or 443
    password = unquote(parsed.username or "")
    if not host or not password:
        raise ValueError("Trojan link missing host or password")

    network = _q(query, "type", "tcp")
    security = _q(query, "security", "tls")

    outbound: Dict[str, Any] = {
        "tag": _random_tag("trojan"),
        "protocol": "trojan",
        "settings": {
            "servers": [{"address": host, "port": port, "password": password}]
        },
        "streamSettings": {
            "network": network,
            "security": security,
        },
    }

    sni = _q(query, "sni") or _q(query, "serverName")
    if security == "tls":
        tls_settings: Dict[str, Any] = {
            "allowInsecure": _to_bool(_q(query, "insecure") or _q(query, "allowInsecure"), False)
        }
        if sni:
            tls_settings["serverName"] = sni
        alpn = _split_csv(_q(query, "alpn"))
        if alpn:
            tls_settings["alpn"] = alpn
        outbound["streamSettings"]["tlsSettings"] = tls_settings

    if network == "ws":
        ws_settings: Dict[str, Any] = {"path": _q(query, "path", "/")}
        host_header = _q(query, "host")
        if host_header:
            ws_settings["headers"] = {"Host": host_header}
        outbound["streamSettings"]["wsSettings"] = ws_settings

    return ParseResult(protocol="trojan", outbound=outbound)


def parse_vmess(link: str) -> ParseResult:
    raw = link[len("vmess://") :]
    try:
        pad = "=" * ((4 - len(raw) % 4) % 4)
        decoded = base64.urlsafe_b64decode(raw + pad).decode("utf-8")
        conf = json.loads(decoded)
    except Exception as exc:
        raise ValueError(f"Bad vmess link: {exc}") from exc

    host = conf.get("add")
    port = int(conf.get("port", 443))
    user_id = conf.get("id")
    if not host or not user_id:
        raise ValueError("VMESS link missing add/id")

    net = conf.get("net", "tcp")
    tls_mode = conf.get("tls", "")
    security = "tls" if tls_mode in {"tls", "reality"} else "none"

    outbound: Dict[str, Any] = {
        "tag": _random_tag("vmess"),
        "protocol": "vmess",
        "settings": {
            "vnext": [
                {
                    "address": host,
                    "port": port,
                    "users": [
                        {
                            "id": user_id,
                            "alterId": int(conf.get("aid", 0)),
                            "security": conf.get("scy", "auto"),
                        }
                    ],
                }
            ]
        },
        "streamSettings": {
            "network": net,
            "security": security,
        },
    }

    if security == "tls":
        tls_settings: Dict[str, Any] = {}
        if conf.get("sni"):
            tls_settings["serverName"] = conf["sni"]
        if conf.get("allowInsecure") is not None:
            tls_settings["allowInsecure"] = bool(conf["allowInsecure"])
        if tls_settings:
            outbound["streamSettings"]["tlsSettings"] = tls_settings

    if net == "ws":
        ws_settings: Dict[str, Any] = {"path": conf.get("path", "/")}
        host_header = conf.get("host")
        if host_header:
            ws_settings["headers"] = {"Host": host_header}
        outbound["streamSettings"]["wsSettings"] = ws_settings

    return ParseResult(protocol="vmess", outbound=outbound)


def parse_ss(link: str) -> ParseResult:
    parsed = urlparse(link)
    if not parsed.hostname:
        raise ValueError("SS link missing host")
    host = parsed.hostname
    port = parsed.port
    if not port:
        raise ValueError("SS link missing port")

    userinfo = parsed.username or ""
    if not userinfo and parsed.netloc:
        # ss://BASE64(method:password)@host:port style
        netloc = parsed.netloc
        if "@" in netloc:
            creds_enc = netloc.split("@", 1)[0]
            pad = "=" * ((4 - len(creds_enc) % 4) % 4)
            creds = base64.urlsafe_b64decode(creds_enc + pad).decode("utf-8")
            method, password = creds.split(":", 1)
        else:
            raise ValueError("Unsupported SS link format")
    else:
        try:
            pad = "=" * ((4 - len(userinfo) % 4) % 4)
            creds = base64.urlsafe_b64decode(userinfo + pad).decode("utf-8")
            method, password = creds.split(":", 1)
        except Exception as exc:
            raise ValueError(f"Bad SS credentials: {exc}") from exc

    outbound: Dict[str, Any] = {
        "tag": _random_tag("ss"),
        "protocol": "shadowsocks",
        "settings": {
            "servers": [
                {
                    "address": host,
                    "port": port,
                    "method": method,
                    "password": password,
                }
            ]
        },
    }
    return ParseResult(protocol="ss", outbound=outbound)


def parse_link(link: str) -> ParseResult:
    if link.startswith("vless://"):
        return parse_vless(link)
    if link.startswith("trojan://"):
        return parse_trojan(link)
    if link.startswith("vmess://"):
        return parse_vmess(link)
    if link.startswith("ss://"):
        return parse_ss(link)
    raise ValueError("Unsupported protocol")


def make_config(outbound: Dict[str, Any], socks_port: int) -> Dict[str, Any]:
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "socks-in",
                "listen": "127.0.0.1",
                "port": socks_port,
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": True},
            }
        ],
        "outbounds": [
            outbound,
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {
                    "type": "field",
                    "inboundTag": ["socks-in"],
                    "outboundTag": outbound["tag"],
                }
            ],
        },
    }


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def canonicalize_link(link: str) -> str:
    clean_link, _ = urldefrag((link or "").strip())
    if not clean_link:
        return ""

    try:
        parsed = urlparse(clean_link)
    except ValueError:
        return clean_link
    if not parsed.scheme:
        return clean_link

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if query_pairs:
        query_pairs.sort()
        normalized_query = urlencode(query_pairs, doseq=True)
        parsed = parsed._replace(query=normalized_query)

    parsed = parsed._replace(fragment="")
    return parsed.geturl()


def dedupe_links(links: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for link in links:
        normalized = canonicalize_link(link)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(link.strip())
    return out


def _existing_files(paths: List[Path]) -> List[Path]:
    return [p for p in paths if p.exists() and p.is_file()]


def latest_day_subscription_files(limit: int = 2) -> List[Path]:
    candidates = _existing_files([GIT_SUBS_DIR / name for name in DAY_FILES])
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[:limit]


def load_priority_links(job_name: str, target_valid: int) -> List[str]:
    if job_name == "ss":
        sources = _existing_files(
            [
                Path("file/checked_keys/ss.txt"),
                Path("file/valid_keys/ss.txt"),
                Path("file/desc_keys/ss.txt"),
            ]
        )
    elif job_name == "vless":
        sources = _existing_files(
            [
                Path("file/checked_keys/vless.txt"),
                Path("file/valid_keys/vless.txt"),
                Path("file/desc_keys/vless.txt"),
            ]
        )
        sources.extend(latest_day_subscription_files(limit=2))
    elif job_name == "keys":
        sources = _existing_files(
            [
                Path("file/checked_keys/keys.txt"),
                Path("file/valid_keys/keys.txt"),
                Path("file/desc_keys/keys.txt"),
                GIT_SUBS_DIR / "WhiteKeys",
            ]
        )
    else:
        sources = []

    if not sources:
        return []

    cap = max(target_valid * PRIORITY_MULTIPLIER, target_valid)
    merged: List[str] = []
    for src in sources:
        for link in iter_links(src):
            merged.append(link)
            if len(merged) >= cap:
                return dedupe_links(merged)

    return dedupe_links(merged)


def _cache_key(link: str) -> str:
    normalized = canonicalize_link(link)
    return hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()


def load_cache(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    cache: Dict[str, Dict[str, Any]] = {}
    for k, v in raw.items():
        if isinstance(k, str) and isinstance(v, dict):
            cache[k] = v
    return cache


def save_cache(path: Path, cache: Dict[str, Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
        json.dump(cache, tmp, ensure_ascii=False)
        tmp.flush()
        temp_name = tmp.name
    os.replace(temp_name, path)


def get_fresh_cache_entry(
    cache: Dict[str, Dict[str, Any]],
    link: str,
    now_ts: float,
) -> Optional[Dict[str, Any]]:
    entry = cache.get(_cache_key(link))
    if not entry:
        return None
    checked_at = float(entry.get("checked_at", 0.0))
    ttl = OK_CACHE_TTL_SEC if bool(entry.get("ok", False)) else FAIL_CACHE_TTL_SEC
    if now_ts - checked_at > ttl:
        return None
    return entry


def update_cache_entry(
    cache: Dict[str, Dict[str, Any]],
    link: str,
    ok: bool,
    latency_ms: float,
    reason: str,
    checked_at: float,
) -> None:
    cache[_cache_key(link)] = {
        "ok": bool(ok),
        "latency_ms": float(latency_ms),
        "reason": reason,
        "checked_at": float(checked_at),
    }


def extract_host_port_for_precheck(link: str) -> Tuple[str, int]:
    parsed = parse_link(link)
    outbound = parsed.outbound

    if parsed.protocol in {"vless", "vmess"}:
        server = outbound["settings"]["vnext"][0]
        host = str(server["address"])
        port = int(server["port"])
    elif parsed.protocol in {"trojan", "ss"}:
        server = outbound["settings"]["servers"][0]
        host = str(server["address"])
        port = int(server["port"])
    else:
        raise ValueError("unsupported protocol")

    return host, port


def fast_precheck(link: str, timeout: float) -> bool:
    try:
        host, port = extract_host_port_for_precheck(link)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def probe_via_socks(socks_port: int, test_url: str, timeout: float) -> float:
    cmd = [
        "curl",
        "--silent",
        "--show-error",
        "--output",
        "/dev/null",
        "--write-out",
        "%{time_total}",
        "--max-time",
        str(timeout),
        "--proxy",
        f"socks5h://127.0.0.1:{socks_port}",
        test_url,
    ]
    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "curl failed")
    raw = result.stdout.strip()
    try:
        sec = float(raw)
    except ValueError:
        sec = time.time() - start
    return sec * 1000.0


def check_link(xray_bin: Path, link: str, test_url: str, timeout: float, xray_workdir: Path) -> float:
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
                raise RuntimeError(f"xray exited with code {proc.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", socks_port), timeout=0.15):
                    break
            except OSError:
                time.sleep(0.08)
        else:
            raise RuntimeError("xray socks inbound did not start")

        return probe_via_socks(socks_port, test_url, timeout)
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


def iter_links(path: Path):
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        yield line


def check_link_worker(link: str, xray_bin: Path, test_url: str, timeout: float, xray_workdir: Path):
    try:
        latency_ms = check_link(
            xray_bin=xray_bin,
            link=link,
            test_url=test_url,
            timeout=timeout,
            xray_workdir=xray_workdir,
        )
        return True, latency_ms
    except Exception:
        return False, -1.0


def fast_precheck_worker(link: str, timeout: float):
    try:
        return fast_precheck(link=link, timeout=timeout)
    except Exception:
        return False


def collect_valid_links(
    job_name: str,
    input_path: Path,
    output_path: Path,
    target_valid: int,
    xray_bin_abs: Path,
    xray_workdir: Path,
    cache: Dict[str, Dict[str, Any]],
) -> bool:
    if not input_path.exists():
        print(f"[warn] Input file not found: {input_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("", encoding="utf-8")
        return False

    priority_links = load_priority_links(job_name=job_name, target_valid=target_valid)
    source_links = list(iter_links(input_path))
    links_raw = priority_links + source_links
    if LIMIT > 0:
        links_raw = links_raw[:LIMIT]

    links = dedupe_links(links_raw)
    total = len(links)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("", encoding="utf-8")

    if total == 0:
        print(f"[info] No links found in input: {input_path}")
        return True

    if total < target_valid:
        print(
            f"[warn] unique normalized links ({total}) < target ({target_valid}) for {input_path}"
        )

    ok = 0
    bad = 0
    cursor = 0
    fail_streak = 0
    seen_valid = set()
    started = time.time()
    reason_stats = {"cache_ok": 0, "cache_fail": 0, "precheck_fail": 0, "xray_ok": 0, "xray_fail": 0}

    print(
        f"[start] {input_path} -> {output_path}, "
        f"priority={len(priority_links)} raw={len(links_raw)} unique={total}, target={target_valid}"
    )

    with output_path.open("a", encoding="utf-8") as out_valid:
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            while ok < target_valid and cursor < total:
                precheck_batch: List[Tuple[str, str]] = []
                xray_batch: List[Tuple[str, str]] = []

                while len(xray_batch) < MAX_WORKERS and cursor < total and ok < target_valid:
                    link = links[cursor]
                    cursor += 1
                    normalized = canonicalize_link(link)
                    now_ts = time.time()

                    cached = get_fresh_cache_entry(cache, link=link, now_ts=now_ts)
                    if cached is not None:
                        if bool(cached.get("ok", False)):
                            if normalized not in seen_valid:
                                out_valid.write(link + "\n")
                                out_valid.flush()
                                seen_valid.add(normalized)
                                ok += 1
                                latency_ms = float(cached.get("latency_ms", -1.0))
                                print(f"[CACHE_OK]: {latency_ms:.0f}ms ({ok}/{target_valid})")
                            reason_stats["cache_ok"] += 1
                            fail_streak = 0
                        else:
                            bad += 1
                            fail_streak += 1
                            reason_stats["cache_fail"] += 1
                            print("[CACHE_FAIL]: -1")
                        if fail_streak >= FAIL_STREAK_FOR_SKIP:
                            dynamic_skip = BASE_SKIP_AHEAD + (fail_streak - FAIL_STREAK_FOR_SKIP)
                            jump = min(dynamic_skip, MAX_SKIP_AHEAD, max(0, total - cursor))
                            cursor += jump
                        continue

                    precheck_batch.append((link, normalized))

                if precheck_batch:
                    precheck_results: List[Optional[bool]] = [None] * len(precheck_batch)
                    precheck_future_to_idx = {
                        executor.submit(
                            fast_precheck_worker,
                            item[0],
                            PRECHECK_TIMEOUT_SEC,
                        ): idx
                        for idx, item in enumerate(precheck_batch)
                    }

                    for future in concurrent.futures.as_completed(precheck_future_to_idx):
                        idx = precheck_future_to_idx[future]
                        try:
                            precheck_results[idx] = bool(future.result())
                        except Exception:
                            precheck_results[idx] = False

                    for idx, passed in enumerate(precheck_results):
                        link, normalized = precheck_batch[idx]
                        now_ts = time.time()
                        if passed:
                            xray_batch.append((link, normalized))
                            continue

                        bad += 1
                        fail_streak += 1
                        reason_stats["precheck_fail"] += 1
                        update_cache_entry(
                            cache,
                            link=link,
                            ok=False,
                            latency_ms=-1.0,
                            reason="precheck",
                            checked_at=now_ts,
                        )
                        print("[PRECHECK_FAIL]: -1")
                        if fail_streak >= FAIL_STREAK_FOR_SKIP:
                            dynamic_skip = BASE_SKIP_AHEAD + (fail_streak - FAIL_STREAK_FOR_SKIP)
                            jump = min(dynamic_skip, MAX_SKIP_AHEAD, max(0, total - cursor))
                            cursor += jump

                if not xray_batch:
                    continue

                results: List[Optional[tuple]] = [None] * len(xray_batch)
                future_to_idx = {
                    executor.submit(
                        check_link_worker,
                        item[0],
                        xray_bin_abs,
                        TEST_URL,
                        TIMEOUT_SEC,
                        xray_workdir,
                    ): idx
                    for idx, item in enumerate(xray_batch)
                }

                for future in concurrent.futures.as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        results[idx] = future.result()
                    except Exception:
                        results[idx] = (False, -1.0)

                for idx, result in enumerate(results):
                    link, normalized = xray_batch[idx]
                    success, latency_ms = result if result is not None else (False, -1.0)
                    now_ts = time.time()

                    update_cache_entry(
                        cache,
                        link=link,
                        ok=bool(success),
                        latency_ms=float(latency_ms),
                        reason="xray",
                        checked_at=now_ts,
                    )

                    if success:
                        fail_streak = 0
                        if normalized not in seen_valid:
                            out_valid.write(link + "\n")
                            out_valid.flush()
                            seen_valid.add(normalized)
                            ok += 1
                            reason_stats["xray_ok"] += 1
                            print(f"[DONE]: {latency_ms:.0f}ms ({ok}/{target_valid})")
                            if ok >= target_valid:
                                break
                    else:
                        bad += 1
                        fail_streak += 1
                        reason_stats["xray_fail"] += 1
                        print("[FAIL]: -1")

                        if fail_streak >= FAIL_STREAK_FOR_SKIP:
                            dynamic_skip = BASE_SKIP_AHEAD + (fail_streak - FAIL_STREAK_FOR_SKIP)
                            jump = min(dynamic_skip, MAX_SKIP_AHEAD, max(0, total - cursor))
                            cursor += jump

    elapsed = time.time() - started
    if ok < target_valid:
        pool = [link for link in links if canonicalize_link(link) not in seen_valid]
        random.shuffle(pool)
        need = target_valid - ok
        filler = pool[:need]

        if filler:
            with output_path.open("a", encoding="utf-8") as out_valid:
                for link in filler:
                    out_valid.write(link + "\n")
            ok += len(filler)
            print(
                f"[warn] target not reached after checks; added random fallback keys: {len(filler)}"
            )

        if ok < target_valid:
            print(f"[warn] still below target: {ok}/{target_valid} (not enough unique links in source)")
    rate = (ok / elapsed) if elapsed > 0 else 0.0
    print(
        f"done total={total} valid={ok} fail={bad} elapsed={elapsed:.1f}s "
        f"rate={rate:.2f} key/s file={output_path}"
    )
    print(f"[stats] {job_name}: {reason_stats}")
    return True


def main() -> int:
    xray_bin = XRAY_BIN_PATH
    if not xray_bin.exists():
        print(f"[error] Xray binary not found: {xray_bin}")
        return 1

    xray_workdir = xray_bin.parent.resolve()
    xray_bin_abs = xray_bin.resolve()
    overall_ok = True
    cache = load_cache(CACHE_PATH)

    for job in SOURCE_JOBS:
        ok = collect_valid_links(
            job_name=str(job["name"]),
            input_path=job["input"],
            output_path=job["output"],
            target_valid=int(job["target"]),
            xray_bin_abs=xray_bin_abs,
            xray_workdir=xray_workdir,
            cache=cache,
        )
        overall_ok = overall_ok and ok

    save_cache(CACHE_PATH, cache)
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
