#!/usr/bin/env python3
import concurrent.futures
import multiprocessing
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from check_keys import XRAY_BIN_PATH, TEST_URL, TIMEOUT_SEC, check_link, iter_links
try:
    from project_config import current_profile, env_int
except ModuleNotFoundError:
    from src.project_config import current_profile, env_int

# ===== Settings (edit here) =====
SOURCE_FILES = [
    Path("file/checked_keys/ss.txt"),
    Path("file/checked_keys/vless.txt"),
    Path("file/checked_keys/keys.txt"),
]
VALID_DIR = Path("file/valid_keys")
DEFAULT_ROUNDS = 3 if current_profile() == "full" else 1
ROUNDS = env_int("RAY_RANK_ROUNDS", DEFAULT_ROUNDS, minimum=1)
MAX_WORKERS = env_int(
    "RAY_RANK_WORKERS",
    min(100, max(8, multiprocessing.cpu_count() * 8)),
    minimum=1,
)
# ================================


@dataclass
class KeyStat:
    idx: int
    link: str
    rounds_total: int = ROUNDS
    latencies: List[float] = field(default_factory=list)
    fail_count: int = 0

    @property
    def success_count(self) -> int:
        return len(self.latencies)

    @property
    def success_rate(self) -> float:
        return self.success_count / self.rounds_total if self.rounds_total > 0 else 0.0

    @property
    def median_ms(self) -> float:
        if not self.latencies:
            return float("inf")
        return statistics.median(self.latencies)

    @property
    def avg_ms(self) -> float:
        if not self.latencies:
            return float("inf")
        return sum(self.latencies) / len(self.latencies)

    @property
    def best_ms(self) -> float:
        if not self.latencies:
            return float("inf")
        return min(self.latencies)


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


def rank_key(stat: KeyStat):
    # Better keys go first:
    # 1) Higher success rate
    # 2) Lower median latency
    # 3) Lower average latency
    # 4) Better original order as stable fallback
    return (-stat.success_rate, stat.median_ms, stat.avg_ms, stat.idx)


def rank_file(input_path: Path, valid_dir: Path, xray_bin: Path) -> bool:
    stem = input_path.stem
    output_path = valid_dir / f"{stem}.txt"
    details_path = valid_dir / f"{stem}_stats.csv"

    if not input_path.exists():
        print(f"[warn] Input file not found: {input_path}")
        valid_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text("", encoding="utf-8")
        details_path.write_text("idx,success_rate,success_count,fail_count,median_ms,avg_ms,best_ms,link\n", encoding="utf-8")
        return False

    links_raw = list(iter_links(input_path))
    if not links_raw:
        print("[info] No keys found in input")
        output_path.write_text("", encoding="utf-8")
        details_path.write_text("idx,success_rate,success_count,fail_count,median_ms,avg_ms,best_ms,link\n", encoding="utf-8")
        return True

    links = list(dict.fromkeys(links_raw))
    stats = [KeyStat(idx=i, link=link) for i, link in enumerate(links)]

    valid_dir.mkdir(parents=True, exist_ok=True)

    xray_workdir = xray_bin.parent.resolve()
    xray_bin_abs = xray_bin.resolve()

    started = time.time()

    rounds_for_file = ROUNDS
    if len(links) <= 120:
        rounds_for_file = max(1, ROUNDS - 1)
    for stat in stats:
        stat.rounds_total = rounds_for_file

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for round_no in range(1, rounds_for_file + 1):
            print(f"[round {round_no}/{rounds_for_file}] checking {len(stats)} keys (parallel={MAX_WORKERS})")

            future_to_idx = {
                executor.submit(
                    check_link_worker,
                    stat.link,
                    xray_bin_abs,
                    TEST_URL,
                    TIMEOUT_SEC,
                    xray_workdir,
                ): idx
                for idx, stat in enumerate(stats)
            }

            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                success, latency_ms = future.result()
                if success:
                    stats[idx].latencies.append(latency_ms)
                else:
                    stats[idx].fail_count += 1

    ranked = sorted(stats, key=rank_key)

    output_path.write_text(
        "".join(f"{s.link}\n" for s in ranked),
        encoding="utf-8",
    )

    with details_path.open("w", encoding="utf-8") as fh:
        fh.write("idx,success_rate,success_count,fail_count,median_ms,avg_ms,best_ms,link\n")
        for s in ranked:
            median_ms = "inf" if s.median_ms == float("inf") else f"{s.median_ms:.2f}"
            avg_ms = "inf" if s.avg_ms == float("inf") else f"{s.avg_ms:.2f}"
            best_ms = "inf" if s.best_ms == float("inf") else f"{s.best_ms:.2f}"
            fh.write(
                f"{s.idx},{s.success_rate:.3f},{s.success_count},{s.fail_count},"
                f"{median_ms},{avg_ms},{best_ms},\"{s.link}\"\n"
            )

    elapsed = time.time() - started
    success_total = sum(s.success_count for s in stats)
    checks_total = len(stats) * rounds_for_file
    success_rate = (success_total / checks_total) if checks_total else 0.0
    print(
        f"done input={len(links_raw)} used={len(links)} rounds={rounds_for_file} "
        f"elapsed={elapsed:.1f}s success={success_rate:.2%} ranked={output_path} stats={details_path}"
    )
    return True


def main() -> int:
    xray_bin = XRAY_BIN_PATH
    if not xray_bin.exists():
        print(f"[error] Xray binary not found: {xray_bin}")
        return 1

    overall_ok = True
    for input_path in SOURCE_FILES:
        ok = rank_file(input_path=input_path, valid_dir=VALID_DIR, xray_bin=xray_bin)
        overall_ok = overall_ok and ok

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
