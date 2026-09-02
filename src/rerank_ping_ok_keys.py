#!/usr/bin/env python3
import argparse
import asyncio
import json
import statistics
import tempfile
import time
from pathlib import Path

from ping_keys_with_xray import (
    TEST_URLS,
    build_config,
    parse_hysteria2,
    parse_ss,
    parse_vless,
    stop_process,
)


def read_keys(path: Path):
    if not path.exists():
        return []
    out = []
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        key = line.strip()
        if not key:
            continue
        if key in seen:
            continue
        if key.startswith(("ss://", "vless://", "hysteria2://", "hy2://")):
            seen.add(key)
            out.append(key)
    return out


def key_kind(key: str):
    if key.startswith("ss://"):
        return "ss"
    if key.startswith("vless://"):
        return "vless"
    if key.startswith(("hysteria2://", "hy2://")):
        return "hysteria2"
    return "unknown"


async def probe_once(key: str, xray_bin: Path, socks_port: int, timeout: float):
    try:
        if key.startswith("vless://"):
            outbound = parse_vless(key)
        elif key.startswith(("hysteria2://", "hy2://")):
            outbound = parse_hysteria2(key)
        else:
            outbound = parse_ss(key)
    except Exception:
        return None

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
        best_ms = None
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
                if best_ms is None or dt_ms < best_ms:
                    best_ms = dt_ms

        return best_ms
    except Exception:
        return None
    finally:
        await stop_process(proc)
        try:
            cfg_path.unlink(missing_ok=True)
        except Exception:
            pass


async def measure_key(key: str, runs: int, xray_bin: Path, timeout: float, socks_port: int):
    lats = []
    for _ in range(runs):
        lat = await probe_once(key, xray_bin, socks_port, timeout)
        if lat is not None:
            lats.append(lat)

    if not lats:
        return None

    # Stable ranking: first by successful runs count, then by median latency.
    score_ms = statistics.median(lats)
    return {
        "key": key,
        "success_runs": len(lats),
        "score_ms": score_ms,
        "min_ms": min(lats),
        "avg_ms": sum(lats) / len(lats),
    }


async def rerank_file(path: Path, out_dir: Path, xray_bin: Path, concurrency: int, timeout: float, runs: int, base_port: int):
    keys = read_keys(path)
    if not keys:
        out_path = out_dir / path.name
        out_path.write_text("", encoding="utf-8")
        print(f"[{path.name}] пустой/нет ключей")
        return

    print(f"[{path.name}] ключей: {len(keys)}")

    workers_count = min(max(1, concurrency), len(keys))
    available_ports = asyncio.Queue()
    for worker_idx in range(workers_count):
        available_ports.put_nowait(base_port + worker_idx)
    done = 0

    async def one(key: str):
        nonlocal done
        socks_port = await available_ports.get()
        try:
            try:
                result = await measure_key(
                    key=key,
                    runs=runs,
                    xray_bin=xray_bin,
                    timeout=timeout,
                    socks_port=socks_port,
                )
            except Exception as exc:
                print(
                    f"[{path.name}] ошибка worker: "
                    f"{type(exc).__name__}: {exc}"
                )
                result = None
        finally:
            available_ports.put_nowait(socks_port)
        done += 1
        if done % 50 == 0 or done == len(keys):
            print(f"[{path.name}] проверено {done}/{len(keys)}")
        return result

    results = await asyncio.gather(*(one(key) for key in keys))
    alive = [x for x in results if x is not None]

    ss_ranked = sorted(
        [x for x in alive if key_kind(x["key"]) == "ss"],
        key=lambda x: (-x["success_runs"], x["score_ms"], x["min_ms"]),
    )
    vless_like_ranked = sorted(
        [x for x in alive if key_kind(x["key"]) in {"vless", "hysteria2"}],
        key=lambda x: (-x["success_runs"], x["score_ms"], x["min_ms"]),
    )

    selected = []
    selected.extend(vless_like_ranked[:300])
    selected.extend(ss_ranked[:10])

    # If file contains only one protocol, keep natural order for that protocol.
    selected_sorted = sorted(
        selected,
        key=lambda x: (0 if key_kind(x["key"]) in {"vless", "hysteria2"} else 1, -x["success_runs"], x["score_ms"], x["min_ms"]),
    )
    out_keys = [x["key"] for x in selected_sorted]

    out_path = out_dir / path.name
    out_path.write_text("\n".join(out_keys) + ("\n" if out_keys else ""), encoding="utf-8")

    print(
        f"[{path.name}] alive={len(alive)}, vless_hysteria2_top={min(300, len(vless_like_ranked))}, "
        f"ss_top={min(10, len(ss_ranked))} -> {out_path}"
    )


async def main_async(args):
    in_dir = Path(args.input_dir)
    out_dir = Path(args.output_dir)
    xray_bin = Path(args.xray_bin)

    if not in_dir.exists():
        raise FileNotFoundError(f"Не найдена папка input-dir: {in_dir}")
    if not xray_bin.exists():
        raise FileNotFoundError(f"Не найден xray: {xray_bin}")

    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(in_dir.glob(args.glob))
    if not files:
        print("Файлы не найдены по шаблону.")
        return

    print(f"Найдено файлов: {len(files)}")
    for i, path in enumerate(files):
        file_base_port = args.base_port + (i * 1000)
        if file_base_port < 1 or file_base_port + max(1, args.concurrency) - 1 > 65_535:
            raise ValueError(f"port range is invalid for {path.name}")
        await rerank_file(
            path=path,
            out_dir=out_dir,
            xray_bin=xray_bin,
            concurrency=args.concurrency,
            timeout=args.timeout,
            runs=args.runs,
            base_port=file_base_port,
        )


def main():
    parser = argparse.ArgumentParser(
        description="Повторная проверка ping_ok файлов: 3 прогона и отбор самых быстрых ключей."
    )
    parser.add_argument("--input-dir", default="file/4LiveKeys")
    parser.add_argument("--output-dir", default="file/5TopLiveKeys")
    parser.add_argument("--glob", default="*_ping_ok.txt")
    parser.add_argument("--xray-bin", default="xrayFile/xray")
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--base-port", type=int, default=11000)
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
