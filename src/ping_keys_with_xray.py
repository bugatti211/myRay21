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


def read_keys(path: Path, prefix: str):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(prefix):
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


async def check_one(key: str, kind: str, xray_bin: Path, socks_port: int, timeout: float):
    try:
        outbound = parse_vless(key) if kind.startswith("vless") else parse_ss(key)
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
):
    sem = asyncio.Semaphore(concurrency)
    alive = []
    done = 0
    write_lock = asyncio.Lock()
    stop_event = asyncio.Event()
    next_idx = 0
    idx_lock = asyncio.Lock()

    async def worker():
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
                ok = await check_one(key, kind, xray_bin, base_port + idx, timeout)
            done += 1
            if done % 100 == 0 or done == len(keys):
                print(f"[{kind}] проверено {done}/{len(keys)}")
            if ok:
                async with write_lock:
                    if max_alive is not None and len(alive) >= max_alive:
                        stop_event.set()
                        return
                    alive.append(key)
                    with kind_out_path.open("a", encoding="utf-8") as f:
                        f.write(key + "\n")
                    if max_alive is not None and len(alive) >= max_alive:
                        print(f"[{kind}] достигнут лимит живых: {max_alive}, останавливаю проверку")
                        stop_event.set()
                        return

    workers = min(concurrency, max(1, len(keys)))
    await asyncio.gather(*(worker() for _ in range(workers)))
    return alive


async def main_async(args):
    xray_bin = Path(args.xray_bin)
    if not xray_bin.exists():
        raise FileNotFoundError(f"Не найден xray: {xray_bin}")

    vless_keys = read_keys(Path(args.vless_file), "vless://")
    vless_ru_keys = read_keys(Path(args.vless_ru_file), "vless://")
    ss_keys = read_keys(Path(args.ss_file), "ss://")
    ss_ru_keys = read_keys(Path(args.ss_ru_file), "ss://")

    print(f"vless ключей: {len(vless_keys)}")
    print(f"vless_RU ключей: {len(vless_ru_keys)}")
    print(f"ss ключей: {len(ss_keys)}")
    print(f"ss_RU ключей: {len(ss_ru_keys)}")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    vless_out = out_dir / "vless_ping_ok.txt"
    vless_ru_out = out_dir / "vless_RU_ping_ok.txt"
    ss_out = out_dir / "ss_ping_ok.txt"
    ss_ru_out = out_dir / "ss_RU_ping_ok.txt"

    # Reset output files for a new run; then append alive keys during checks.
    vless_out.write_text("", encoding="utf-8")
    vless_ru_out.write_text("", encoding="utf-8")
    ss_out.write_text("", encoding="utf-8")
    ss_ru_out.write_text("", encoding="utf-8")

    alive_vless = await run_checks(
        vless_keys,
        "vless",
        xray_bin,
        args.concurrency,
        args.timeout,
        args.base_port,
        vless_out,
        args.max_alive_vless,
    )
    alive_vless_ru = await run_checks(
        vless_ru_keys,
        "vless_RU",
        xray_bin,
        args.concurrency,
        args.timeout,
        args.base_port + 20000,
        vless_ru_out,
        args.max_alive_vless,
    )
    alive_ss = await run_checks(
        ss_keys,
        "ss",
        xray_bin,
        args.concurrency,
        args.timeout,
        args.base_port + 40000,
        ss_out,
        args.max_alive_ss,
    )
    alive_ss_ru = await run_checks(
        ss_ru_keys,
        "ss_RU",
        xray_bin,
        args.concurrency,
        args.timeout,
        args.base_port + 60000,
        ss_ru_out,
        args.max_alive_ss,
    )

    print(f"\nГотово: {vless_out} ({len(alive_vless)})")
    print(f"Готово: {vless_ru_out} ({len(alive_vless_ru)})")
    print(f"Готово: {ss_out} ({len(alive_ss)})")
    print(f"Готово: {ss_ru_out} ({len(alive_ss_ru)})")


def main():
    parser = argparse.ArgumentParser(description="Проверка ключей через xray core с параллелизмом.")
    parser.add_argument("--vless-file", default="file/3KeysFromGit/vless.txt")
    parser.add_argument("--vless-ru-file", default="file/3KeysFromGit/vless_RU.txt")
    parser.add_argument("--ss-file", default="file/3KeysFromGit/ss.txt")
    parser.add_argument("--ss-ru-file", default="file/3KeysFromGit/ss_RU.txt")
    parser.add_argument("--xray-bin", default="xrayFile/xray")
    parser.add_argument("--output-dir", default="file/4LiveKeys")
    parser.add_argument("--concurrency", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--base-port", type=int, default=10000)
    parser.add_argument("--max-alive-vless", type=int, default=1000)
    parser.add_argument("--max-alive-ss", type=int, default=100)
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
