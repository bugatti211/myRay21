#!/usr/bin/env python3
import argparse
import asyncio
import base64
import json
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

TEST_URLS = [
    "https://www.gstatic.com/generate_204",
    "https://cp.cloudflare.com/generate_204",
]


<<<<<<< HEAD
def read_keys(path: Path, prefix: str):
=======
def read_keys(path: Path, prefixes):
>>>>>>> authostart
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
<<<<<<< HEAD
        if line.startswith(prefix):
=======
        if any(line.startswith(prefix) for prefix in prefixes):
>>>>>>> authostart
            out.append(line)
    return out


def parse_vless(uri: str):
    p = urlparse(uri)
    qs = parse_qs(p.query)
    uuid = unquote(p.username or "")
    host = p.hostname
    port = p.port
    if not uuid or not host or not port:
        raise ValueError("bad vless uri")

    outbound = {
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": host,
                    "port": port,
                    "users": [
                        {
                            "id": uuid,
                            "encryption": qs.get("encryption", ["none"])[0],
                            "flow": qs.get("flow", [""])[0],
                        }
                    ],
                }
            ]
        },
        "streamSettings": {},
    }

    network = (qs.get("type", ["tcp"])[0] or "tcp").strip().lower()
    security = (qs.get("security", ["none"])[0] or "none").strip().lower()
    if security in {"false", "off"}:
        security = "none"
    if network == "raw":
        network = "tcp"
    outbound["streamSettings"]["network"] = network
    outbound["streamSettings"]["security"] = security

    sni = qs.get("sni", [""])[0] or qs.get("servername", [""])[0] or host
    alpn = qs.get("alpn", [""])[0]
    fp = qs.get("fp", [""])[0]
    pbk = qs.get("pbk", [""])[0]
    sid = qs.get("sid", [""])[0]
    spx = qs.get("spx", [""])[0]

    insecure_raw = (
        qs.get("allowInsecure", [""])[0]
        or qs.get("insecure", [""])[0]
        or qs.get("skip-cert-verify", [""])[0]
    )
    insecure = str(insecure_raw).strip().lower() in {"1", "true", "yes", "on"}

    if security == "tls":
        tls = {"allowInsecure": insecure}
        if sni:
            tls["serverName"] = sni
        if fp:
            tls["fingerprint"] = fp
        if alpn:
            tls["alpn"] = [x for x in alpn.split(",") if x]
        outbound["streamSettings"]["tlsSettings"] = tls

    if security == "reality":
        reality = {}
        if sni:
            reality["serverName"] = sni
        if fp:
            reality["fingerprint"] = fp
        if pbk:
            reality["publicKey"] = pbk
        if sid:
            reality["shortId"] = sid
        if spx:
            reality["spiderX"] = spx
        outbound["streamSettings"]["realitySettings"] = reality

    if network == "ws":
        path = qs.get("path", ["/"])[0] or "/"
        host_header = qs.get("host", [""])[0]
        ws = {"path": path}
        if host_header:
            ws["headers"] = {"Host": host_header}
        outbound["streamSettings"]["wsSettings"] = ws
    elif network == "grpc":
        service = qs.get("serviceName", [""])[0]
        mode = qs.get("mode", [""])[0]
        grpc = {}
        if service:
            grpc["serviceName"] = service
        if mode == "gun":
            grpc["multiMode"] = False
        outbound["streamSettings"]["grpcSettings"] = grpc
    elif network == "xhttp":
        xhttp = {}
        path = qs.get("path", [""])[0]
        host_header = qs.get("host", [""])[0]
        mode = qs.get("mode", [""])[0]
        if path:
            xhttp["path"] = path
        if host_header:
            xhttp["host"] = host_header
        if mode:
            xhttp["mode"] = mode
        if xhttp:
            outbound["streamSettings"]["xhttpSettings"] = xhttp
    elif network == "httpupgrade":
        hup = {}
        path = qs.get("path", [""])[0]
        host_header = qs.get("host", [""])[0]
        if path:
            hup["path"] = path
        if host_header:
            hup["host"] = host_header
        if hup:
            outbound["streamSettings"]["httpupgradeSettings"] = hup

    return outbound


def parse_ss(uri: str):
    p = urlparse(uri)
    if not p.hostname or not p.port:
        raise ValueError("bad ss uri")

    user = p.username
    pwd = p.password

    if user and pwd:
        method = unquote(user)
        password = unquote(pwd)
    else:
        raw = p.netloc.split("@", 1)[0]
        pad = "=" * ((4 - len(raw) % 4) % 4)
        decoded = base64.urlsafe_b64decode((raw + pad).encode()).decode(errors="ignore")
        if ":" not in decoded:
            raise ValueError("bad ss auth")
        method, password = decoded.split(":", 1)

    return {
        "protocol": "shadowsocks",
        "settings": {
            "servers": [
                {
                    "address": p.hostname,
                    "port": p.port,
                    "method": method,
                    "password": password,
                }
            ]
        },
    }


<<<<<<< HEAD
=======
def parse_trojan(uri: str):
    parsed = urlparse(uri)
    query = parse_qs(parsed.query)
    password = unquote(parsed.username or "")
    host = parsed.hostname
    port = parsed.port
    if not password or not host or not port:
        raise ValueError("bad trojan uri")

    network = (query.get("type", ["tcp"])[0] or "tcp").lower()
    security = (query.get("security", ["tls"])[0] or "tls").lower()
    if network == "raw":
        network = "tcp"
    if security in {"false", "off"}:
        security = "none"
    stream = {"network": network, "security": security}

    sni = query.get("sni", [""])[0] or query.get("servername", [""])[0] or host
    alpn = query.get("alpn", [""])[0]
    insecure_raw = query.get("allowInsecure", [""])[0] or query.get("insecure", [""])[0]
    insecure = str(insecure_raw).strip().lower() in {"1", "true", "yes", "on"}
    if security == "tls":
        tls = {"allowInsecure": insecure, "serverName": sni}
        if alpn:
            tls["alpn"] = [value for value in alpn.split(",") if value]
        stream["tlsSettings"] = tls

    if network == "ws":
        ws = {"path": query.get("path", ["/"])[0] or "/"}
        host_header = query.get("host", [""])[0]
        if host_header:
            ws["headers"] = {"Host": host_header}
        stream["wsSettings"] = ws
    elif network == "grpc":
        service_name = query.get("serviceName", [""])[0]
        if service_name:
            stream["grpcSettings"] = {"serviceName": service_name}

    return {
        "protocol": "trojan",
        "settings": {
            "servers": [{"address": host, "port": port, "password": password}]
        },
        "streamSettings": stream,
    }


def parse_hysteria2(uri: str):
    p = urlparse(uri)
    if p.scheme.lower() not in {"hysteria2", "hy2"}:
        raise ValueError("bad hysteria2 scheme")

    authority = uri.split("://", 1)[1].split("/", 1)[0].split("?", 1)[0]
    if "@" in authority:
        auth_raw, server_raw = authority.rsplit("@", 1)
        auth = unquote(auth_raw)
    else:
        auth = ""
        server_raw = authority

    if server_raw.startswith("["):
        bracket_end = server_raw.find("]")
        if bracket_end < 0:
            raise ValueError("bad hysteria2 IPv6 address")
        host = unquote(server_raw[1:bracket_end])
        remainder = server_raw[bracket_end + 1 :]
        port_spec = remainder[1:] if remainder.startswith(":") else ""
    elif ":" in server_raw:
        host, port_spec = server_raw.rsplit(":", 1)
        host = unquote(host)
    else:
        host = unquote(server_raw)
        port_spec = ""

    if not host:
        raise ValueError("bad hysteria2 host")

    qs = parse_qs(p.query, keep_blank_values=True)
    port_spec = unquote(
        qs.get("mport", [""])[0]
        or qs.get("ports", [""])[0]
        or port_spec
        or "443"
    )
    first_port = None
    for part in port_spec.split(","):
        bounds = part.strip().split("-", 1)
        try:
            start = int(bounds[0])
            end = int(bounds[1]) if len(bounds) == 2 else start
        except ValueError as exc:
            raise ValueError("bad hysteria2 port range") from exc
        if not (1 <= start <= end <= 65_535):
            raise ValueError("bad hysteria2 port range")
        if first_port is None:
            first_port = start

    stream_settings = {
        "network": "hysteria",
        "security": "tls",
        "hysteriaSettings": {
            "version": 2,
            "auth": auth,
        },
    }

    sni = unquote(qs.get("sni", [""])[0] or qs.get("peer", [""])[0] or host)
    tls = {
        "serverName": sni,
        "alpn": [
            value
            for value in (qs.get("alpn", ["h3"])[0] or "h3").split(",")
            if value
        ],
    }
    # Xray 26.3.27 removed allowInsecure. We intentionally do not copy the
    # URI's insecure=1 flag; normal CA validation or pinSHA256 is required.
    fingerprint = qs.get("fp", [""])[0]
    if fingerprint:
        tls["fingerprint"] = fingerprint

    cert_pin = (
        qs.get("pinSHA256", [""])[0]
        or qs.get("pinsha256", [""])[0]
        or qs.get("pin", [""])[0]
    )
    if cert_pin:
        normalized_pins = []
        for value in cert_pin.split(","):
            normalized = value.replace(":", "").strip().lower()
            if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
                raise ValueError("bad hysteria2 certificate pin")
            normalized_pins.append(normalized)
        tls["pinnedPeerCertSha256"] = ",".join(normalized_pins)

    ech = qs.get("ech", [""])[0]
    if ech:
        tls["echConfigList"] = ech
    stream_settings["tlsSettings"] = tls

    finalmask = {}
    obfs = qs.get("obfs", [""])[0].strip().lower()
    if obfs:
        if obfs not in {"salamander", "gecko"}:
            raise ValueError(f"unsupported hysteria2 obfs: {obfs}")
        obfs_password = qs.get("obfs-password", [""])[0]
        if not obfs_password:
            raise ValueError("hysteria2 obfs password is missing")
        salamander = {"password": obfs_password}
        if obfs == "gecko":
            salamander["packetSize"] = qs.get("packet-size", ["512-1200"])[0]
        finalmask["udp"] = [{"type": "salamander", "settings": salamander}]

    if "," in port_spec or "-" in port_spec:
        finalmask["quicParams"] = {
            "udpHop": {
                "ports": port_spec,
                "interval": qs.get("hop-interval", ["30"])[0],
            }
        }
    if finalmask:
        stream_settings["finalmask"] = finalmask

    return {
        "protocol": "hysteria",
        "settings": {
            "version": 2,
            "address": host,
            "port": first_port,
        },
        "streamSettings": stream_settings,
    }


>>>>>>> authostart
def build_config(outbound: dict, socks_port: int):
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "listen": "127.0.0.1",
                "port": socks_port,
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": False},
            }
        ],
        "outbounds": [
            outbound,
            {"protocol": "freedom", "tag": "direct"},
        ],
    }


<<<<<<< HEAD
async def check_one(key: str, kind: str, xray_bin: Path, socks_port: int, timeout: float):
    try:
        outbound = parse_vless(key) if kind.startswith("vless") else parse_ss(key)
=======
async def stop_process(proc, timeout: float = 1.5) -> None:
    """Stop a subprocess without leaking races when it has already exited."""
    if proc is None:
        return

    if proc.returncode is None:
        try:
            proc.terminate()
        except ProcessLookupError:
            pass

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
        return
    except (ProcessLookupError, ChildProcessError):
        return
    except asyncio.TimeoutError:
        pass
    except Exception:
        return

    try:
        proc.kill()
    except ProcessLookupError:
        pass
    try:
        await proc.wait()
    except (ProcessLookupError, ChildProcessError):
        pass
    except Exception:
        pass


async def check_one(key: str, kind: str, xray_bin: Path, socks_port: int, timeout: float):
    try:
        if key.startswith("vless://"):
            outbound = parse_vless(key)
        elif key.startswith("ss://"):
            outbound = parse_ss(key)
        elif key.startswith("trojan://"):
            outbound = parse_trojan(key)
        elif key.startswith(("hysteria2://", "hy2://")):
            outbound = parse_hysteria2(key)
        else:
            return False
>>>>>>> authostart
    except Exception:
        return False

    cfg = build_config(outbound, socks_port)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        cfg_path = Path(f.name)
        json.dump(cfg, f, ensure_ascii=False)

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            str(xray_bin),
            "run",
            "-c",
            str(cfg_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        await asyncio.sleep(1.0)
        for test_url in TEST_URLS:
            t0 = time.perf_counter()
            curl = await asyncio.create_subprocess_exec(
                "curl",
                "-sS",
                "--max-time",
                str(timeout),
                "--socks5-hostname",
                f"127.0.0.1:{socks_port}",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                test_url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await curl.communicate()
            dt_ms = (time.perf_counter() - t0) * 1000
            code = out.decode(errors="ignore").strip()
            if curl.returncode == 0 and code in {"200", "204"} and dt_ms > 0:
                return True
        return False
    except Exception:
        return False
    finally:
<<<<<<< HEAD
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=1.5)
            except Exception:
                proc.kill()
                try:
                    await proc.wait()
                except Exception:
                    pass
=======
        await stop_process(proc)
>>>>>>> authostart
        try:
            cfg_path.unlink(missing_ok=True)
        except Exception:
            pass


async def run_checks(
    keys,
    kind,
    xray_bin: Path,
    concurrency: int,
    timeout: float,
    base_port: int,
    kind_out_path: Path,
    max_alive: int | None = None,
<<<<<<< HEAD
=======
    priority_count: int = 0,
>>>>>>> authostart
):
    sem = asyncio.Semaphore(concurrency)
    alive = []
    done = 0
    write_lock = asyncio.Lock()
    stop_event = asyncio.Event()
    next_idx = 0
    idx_lock = asyncio.Lock()

<<<<<<< HEAD
    async def worker():
=======
    async def worker(worker_idx: int):
>>>>>>> authostart
        nonlocal done, next_idx
        while True:
            if stop_event.is_set():
                return
            async with idx_lock:
                if next_idx >= len(keys):
                    return
                idx = next_idx
                key = keys[idx]
                next_idx += 1
            async with sem:
<<<<<<< HEAD
                ok = await check_one(key, kind, xray_bin, base_port + idx, timeout)
=======
                try:
                    ok = await check_one(
                        key,
                        kind,
                        xray_bin,
                        base_port + worker_idx,
                        timeout,
                    )
                except Exception as exc:
                    print(
                        f"[{kind}] ошибка worker для ключа {idx + 1}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    ok = False
>>>>>>> authostart
            done += 1
            if done % 100 == 0 or done == len(keys):
                print(f"[{kind}] проверено {done}/{len(keys)}")
            if ok:
                async with write_lock:
<<<<<<< HEAD
                    if max_alive is not None and len(alive) >= max_alive:
=======
                    is_priority = idx < priority_count
                    if (
                        max_alive is not None
                        and len(alive) >= max_alive
                        and not is_priority
                    ):
>>>>>>> authostart
                        stop_event.set()
                        return
                    alive.append(key)
                    with kind_out_path.open("a", encoding="utf-8") as f:
                        f.write(key + "\n")
<<<<<<< HEAD
                    if max_alive is not None and len(alive) >= max_alive:
=======
                    if (
                        max_alive is not None
                        and len(alive) >= max_alive
                        and next_idx >= priority_count
                    ):
>>>>>>> authostart
                        print(f"[{kind}] достигнут лимит живых: {max_alive}, останавливаю проверку")
                        stop_event.set()
                        return

    workers = min(concurrency, max(1, len(keys)))
<<<<<<< HEAD
    await asyncio.gather(*(worker() for _ in range(workers)))
=======
    await asyncio.gather(*(worker(worker_idx) for worker_idx in range(workers)))
>>>>>>> authostart
    return alive


async def main_async(args):
    xray_bin = Path(args.xray_bin)
    if not xray_bin.exists():
        raise FileNotFoundError(f"Не найден xray: {xray_bin}")
<<<<<<< HEAD

    vless_keys = read_keys(Path(args.vless_file), "vless://")
    vless_ru_keys = read_keys(Path(args.vless_ru_file), "vless://")
    ss_keys = read_keys(Path(args.ss_file), "ss://")
    ss_ru_keys = read_keys(Path(args.ss_ru_file), "ss://")

    print(f"vless ключей: {len(vless_keys)}")
    print(f"vless_RU ключей: {len(vless_ru_keys)}")
    print(f"ss ключей: {len(ss_keys)}")
    print(f"ss_RU ключей: {len(ss_ru_keys)}")
=======
    if args.concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    highest_offset = 40_000
    if args.base_port < 1 or args.base_port + highest_offset + args.concurrency - 1 > 65_535:
        raise ValueError("base-port ranges exceed the valid TCP port range")

    vless_keys = read_keys(Path(args.vless_file), ("vless://", "hysteria2://", "hy2://"))
    vless_ru_keys = read_keys(Path(args.vless_ru_file), ("vless://", "hysteria2://", "hy2://"))
    trojan_keys = read_keys(Path(args.trojan_file), ("trojan://",))
    ss_keys = [] if args.skip_ss else read_keys(Path(args.ss_file), ("ss://",))

    print(f"vless ключей: {len(vless_keys)}")
    print(f"vless_RU ключей: {len(vless_ru_keys)}")
    print(f"trojan ключей: {len(trojan_keys)}")
    if args.skip_ss:
        print("ss ключи: пропущены")
    else:
        print(f"ss ключей: {len(ss_keys)}")
>>>>>>> authostart

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    vless_out = out_dir / "vless_ping_ok.txt"
    vless_ru_out = out_dir / "vless_RU_ping_ok.txt"
    ss_out = out_dir / "ss_ping_ok.txt"
<<<<<<< HEAD
    ss_ru_out = out_dir / "ss_RU_ping_ok.txt"
=======
    trojan_out = out_dir / "trojan_ping_ok.txt"
>>>>>>> authostart

    # Reset output files for a new run; then append alive keys during checks.
    vless_out.write_text("", encoding="utf-8")
    vless_ru_out.write_text("", encoding="utf-8")
<<<<<<< HEAD
    ss_out.write_text("", encoding="utf-8")
    ss_ru_out.write_text("", encoding="utf-8")

    max_alive_vless = args.max_alive_vless if args.max_alive_vless and args.max_alive_vless > 0 else None
    max_alive_ss = args.max_alive_ss if args.max_alive_ss and args.max_alive_ss > 0 else None
=======
    trojan_out.write_text("", encoding="utf-8")
    if not args.skip_ss:
        ss_out.write_text("", encoding="utf-8")

    max_alive_vless = args.max_alive_vless if args.max_alive_vless and args.max_alive_vless > 0 else None
    max_alive_ss = args.max_alive_ss if args.max_alive_ss and args.max_alive_ss > 0 else None
    max_alive_trojan = args.max_alive_trojan if args.max_alive_trojan and args.max_alive_trojan > 0 else None
>>>>>>> authostart

    alive_vless = await run_checks(
        vless_keys,
        "vless",
        xray_bin,
        args.concurrency,
        args.timeout,
        args.base_port,
        vless_out,
        max_alive_vless,
<<<<<<< HEAD
=======
        args.priority_vless_count,
>>>>>>> authostart
    )
    alive_vless_ru = await run_checks(
        vless_ru_keys,
        "vless_RU",
        xray_bin,
        args.concurrency,
        args.timeout,
        args.base_port + 20000,
        vless_ru_out,
        max_alive_vless,
<<<<<<< HEAD
    )
    alive_ss = await run_checks(
        ss_keys,
        "ss",
        xray_bin,
        args.concurrency,
        args.timeout,
        args.base_port + 40000,
        ss_out,
        max_alive_ss,
    )
    alive_ss_ru = await run_checks(
        ss_ru_keys,
        "ss_RU",
        xray_bin,
        args.concurrency,
        args.timeout,
        args.base_port + 60000,
        ss_ru_out,
        max_alive_ss,
    )

    print(f"\nГотово: {vless_out} ({len(alive_vless)})")
    print(f"Готово: {vless_ru_out} ({len(alive_vless_ru)})")
    print(f"Готово: {ss_out} ({len(alive_ss)})")
    print(f"Готово: {ss_ru_out} ({len(alive_ss_ru)})")
=======
        args.priority_vless_ru_count,
    )
    alive_trojan = await run_checks(
        trojan_keys,
        "trojan",
        xray_bin,
        args.concurrency,
        args.timeout,
        args.base_port + 30_000,
        trojan_out,
        max_alive_trojan,
        0,
    )
    if args.skip_ss:
        alive_ss = []
    else:
        alive_ss = await run_checks(
            ss_keys,
            "ss",
            xray_bin,
            args.concurrency,
            args.timeout,
            args.base_port + 40000,
            ss_out,
            max_alive_ss,
            0,
        )

    print(f"\nГотово: {vless_out} ({len(alive_vless)})")
    print(f"Готово: {vless_ru_out} ({len(alive_vless_ru)})")
    print(f"Готово: {trojan_out} ({len(alive_trojan)})")
    if args.skip_ss:
        print(f"Готово: {ss_out} (0, ss пропущены)")
    else:
        print(f"Готово: {ss_out} ({len(alive_ss)})")
>>>>>>> authostart


def main():
    parser = argparse.ArgumentParser(description="Проверка ключей через xray core с параллелизмом.")
    parser.add_argument("--vless-file", default="file/3KeysFromGit/vless.txt")
    parser.add_argument("--vless-ru-file", default="file/3KeysFromGit/vless_RU.txt")
<<<<<<< HEAD
    parser.add_argument("--ss-file", default="file/3KeysFromGit/ss.txt")
    parser.add_argument("--ss-ru-file", default="file/3KeysFromGit/ss_RU.txt")
=======
    parser.add_argument("--trojan-file", default="file/3KeysFromGit/trojan.txt")
    parser.add_argument("--ss-file", default="file/3KeysFromGit/ss.txt")
>>>>>>> authostart
    parser.add_argument("--xray-bin", default="xrayFile/xray")
    parser.add_argument("--output-dir", default="file/4LiveKeys")
    parser.add_argument("--concurrency", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--base-port", type=int, default=10000)
    parser.add_argument("--max-alive-vless", type=int, default=1000)
<<<<<<< HEAD
    parser.add_argument("--max-alive-ss", type=int, default=100)
=======
    parser.add_argument("--max-alive-trojan", type=int, default=50)
    parser.add_argument("--max-alive-ss", type=int, default=100)
    parser.add_argument(
        "--priority-vless-count",
        type=int,
        default=0,
        help="Количество первых VLESS-ключей, которые нужно проверить независимо от лимита.",
    )
    parser.add_argument(
        "--priority-vless-ru-count",
        type=int,
        default=0,
        help="Количество первых RU-ключей, которые нужно проверить независимо от лимита.",
    )
    parser.add_argument("--skip-ss", action="store_true", help="Не читать и не проверять ss:// ключи.")
>>>>>>> authostart
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
