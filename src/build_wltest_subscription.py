#!/usr/bin/env python3
import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Sequence, Tuple

import pipeline_shared_tools as shared
import write_git_publish_files as publisher
import network_filter


DEFAULT_SOURCE_FILES = (
    Path("file/1AllLinksFromGit/whiteList.txt"),
)
DEFAULT_NETWORKS_FILE = Path("normalized_networks.txt")
DEFAULT_WORK_DIR = Path("file/6NetworkFilteredTest")
DEFAULT_OUTPUT = Path("git/WLTest")
SUPPORTED_PREFIXES = ("vless://", "hysteria2://", "hy2://")

SourceFetcher = Callable[[str], Sequence[str]]


def read_all_source_urls(paths: Sequence[Path]) -> List[str]:
    urls: List[str] = []
    seen = set()
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"source list not found: {path}")
        for url in shared.read_subscription_urls(path):
            if url not in seen:
                seen.add(url)
                urls.append(url)
    if not urls:
        raise ValueError("no subscription URLs found")
    return urls


async def download_all_sources(
    urls: Sequence[str],
    concurrency: int,
    retries: int = 2,
    fetcher: SourceFetcher = shared.fetch_lines,
) -> Tuple[List[str], List[Tuple[str, str]]]:
    if concurrency < 1:
        raise ValueError("download concurrency must be at least 1")
    if retries < 0:
        raise ValueError("download retries cannot be negative")

    semaphore = asyncio.Semaphore(concurrency)
    completed = 0
    progress_lock = asyncio.Lock()

    async def download_one(url: str):
        nonlocal completed
        result = ([], "download failed")
        for attempt in range(retries + 1):
            try:
                async with semaphore:
                    rows = await asyncio.to_thread(fetcher, url)
                result = (list(rows), None)
                break
            except Exception as exc:
                result = ([], str(exc))
                if attempt < retries:
                    await asyncio.sleep(min(2 ** attempt, 4))
        async with progress_lock:
            completed += 1
            if completed % 10 == 0 or completed == len(urls):
                print(f"[download] processed {completed}/{len(urls)} subscriptions")
        return result

    results = await asyncio.gather(*(download_one(url) for url in urls))
    keys: List[str] = []
    failures: List[Tuple[str, str]] = []
    for url, (rows, error) in zip(urls, results):
        if error is not None:
            failures.append((url, error))
            continue
        keys.extend(
            row.strip()
            for row in rows
            if row.strip().startswith(SUPPORTED_PREFIXES)
        )
    return shared.dedupe_keys_by_endpoint(keys), failures


async def collect_network_candidates(
    source_files: Sequence[Path],
    networks_file: Path,
    download_concurrency: int,
    download_retries: int = 2,
    fetcher: SourceFetcher = shared.fetch_lines,
) -> dict:
    urls = read_all_source_urls(source_files)
    keys, failures = await download_all_sources(
        urls,
        download_concurrency,
        download_retries,
        fetcher,
    )
    matcher = network_filter.load_network_matcher(networks_file)
    matched, stats = network_filter.filter_keys_by_network(keys, matcher)
    matched = shared.dedupe_keys_by_endpoint(matched)
    return {
        "urls": urls,
        "failures": failures,
        "supported_keys": keys,
        "matched_keys": matched,
        "filter_stats": stats,
        "merged_intervals": matcher.interval_count,
    }


def write_plain_keys(path: Path, keys: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(keys) + ("\n" if keys else ""),
        encoding="utf-8",
    )


async def build_wltest(
    source_files: Sequence[Path] = DEFAULT_SOURCE_FILES,
    networks_file: Path = DEFAULT_NETWORKS_FILE,
    work_dir: Path = DEFAULT_WORK_DIR,
    output_path: Path = DEFAULT_OUTPUT,
    download_concurrency: int = 12,
    download_retries: int = 2,
    fetcher: SourceFetcher = shared.fetch_lines,
) -> dict:
    result = await collect_network_candidates(
        source_files,
        networks_file,
        download_concurrency,
        download_retries,
        fetcher,
    )
    candidates = result["matched_keys"]
    if not candidates:
        raise RuntimeError(
            "no supported keys with IPs from normalized_networks were found; "
            "WLTest was not overwritten"
        )

    work_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = work_dir / "WLTest_candidates.txt"
    obsolete_alive_path = work_dir / "WLTest_alive.txt"
    report_path = work_dir / "WLTest_report.json"
    write_plain_keys(candidates_path, candidates)
    obsolete_alive_path.unlink(missing_ok=True)

    formatted = [
        publisher.rewrite_desc(key, index + 1, publisher.CHANNEL_TEXT)
        for index, key in enumerate(candidates)
    ]
    publisher.write_target(output_path, formatted)

    stats = result["filter_stats"]
    report = {
        "built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_files": [str(path) for path in source_files],
        "subscription_urls": len(result["urls"]),
        "downloaded": len(result["urls"]) - len(result["failures"]),
        "failed": [
            {"url": url, "error": error}
            for url, error in result["failures"]
        ],
        "supported_unique_keys": len(result["supported_keys"]),
        "network_list": str(networks_file),
        "merged_network_intervals": result["merged_intervals"],
        "network_matched_keys": len(candidates),
        "outside_networks": stats.outside_networks,
        "domain_or_invalid": stats.domain_or_invalid,
        "ping_enabled": False,
        "output_keys": len(candidates),
        "output": str(output_path),
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        f"[WLTest] urls={len(result['urls'])}, "
        f"downloaded={report['downloaded']}, failed={len(result['failures'])}"
    )
    print(
        f"[WLTest] supported={len(result['supported_keys'])}, "
        f"network_matched={len(candidates)}, written={len(candidates)}"
    )
    print(f"[ok] written {output_path}")
    print(f"[info] report: {report_path}")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build WLTest from every whiteList subscription: filter "
            "literal server IPs by normalized_networks, then write all matches "
            "without ping."
        )
    )
    parser.add_argument(
        "--source-file",
        type=Path,
        action="append",
        dest="source_files",
        help="URL list; may be specified multiple times",
    )
    parser.add_argument("--networks", type=Path, default=DEFAULT_NETWORKS_FILE)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--download-concurrency", type=int, default=12)
    parser.add_argument("--download-retries", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_files = tuple(args.source_files or DEFAULT_SOURCE_FILES)
    try:
        asyncio.run(
            build_wltest(
                source_files=source_files,
                networks_file=args.networks,
                work_dir=args.work_dir,
                output_path=args.output,
                download_concurrency=args.download_concurrency,
                download_retries=args.download_retries,
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"[error] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
