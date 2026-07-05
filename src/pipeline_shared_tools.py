#!/usr/bin/env python3
import asyncio
import base64
import hashlib
import json
import math
import random
import re
import statistics
import subprocess
import sys
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import urlopen

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from ping_keys_with_xray import check_one

STATS_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*-\s*(\d+)\s*$")
URL_RE = re.compile(r"^https?://\S+$")
RU_WORD_RE = re.compile(r"\b(RU|RUS|RUSSIA)\b", re.IGNORECASE)
KEY_PREFIXES = ("vless://", "ss://", "trojan://")


def parse_pairs(lines):
    cleaned = [line.strip() for line in lines if line.strip()]
    records = []
    i = 0

    while i < len(cleaned):
        url = cleaned[i]
        if not URL_RE.match(url):
            raise ValueError(f"Ожидалась ссылка в строке {i + 1}: {url}")
        if i + 1 >= len(cleaned):
            raise ValueError(f"Для ссылки нет строки со статистикой: {url}")

        m = STATS_RE.match(cleaned[i + 1])
        if not m:
            raise ValueError(
                f"Неверный формат статистики после ссылки {url}: '{cleaned[i + 1]}'. "
                "Ожидается: 'всего - без_дубликатов - живых'"
            )

        total, unique, alive = map(int, m.groups())
        records.append({"url": url, "total": total, "unique": unique, "alive": alive})
        i += 2

    return records


def read_subscription_urls(path: Path):
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [line for line in lines if URL_RE.match(line)]


def parse_base64_subscription(text: str):
    compact = "".join(text.split())
    if not compact or any(prefix in text for prefix in KEY_PREFIXES):
        return None
    try:
        padded = compact + ("=" * ((4 - len(compact) % 4) % 4))
        decoded = base64.b64decode(padded, validate=False).decode("utf-8", errors="replace")
    except Exception:
        return None
    if any(prefix in decoded for prefix in KEY_PREFIXES):
        return decoded
    return None


def extract_key_lines(text: str):
    decoded = parse_base64_subscription(text)
    if decoded is not None:
        text = decoded

    keys = []
    seen = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line in seen:
            continue
        if line.startswith(KEY_PREFIXES):
            seen.add(line)
            keys.append(line)
    return keys


def fetch_subscription_keys(url: str):
    try:
        with urlopen(url, timeout=30) as response:
            text = response.read().decode("utf-8", errors="replace")
    except Exception:
        result = subprocess.run(
            ["curl", "-L", "--insecure", "--max-time", "30", url],
            check=True,
            capture_output=True,
            text=True,
        )
        text = result.stdout
    return extract_key_lines(text)


def stable_seed(*parts):
    data = "\0".join(str(part) for part in parts).encode("utf-8", errors="replace")
    return int.from_bytes(hashlib.sha256(data).digest()[:8], "big")


def stratified_sample(keys, target_count: int, exclude=None, seed_parts=()):
    exclude = exclude or set()
    available_indexes = [idx for idx, key in enumerate(keys) if key not in exclude]
    if target_count >= len(available_indexes):
        return [keys[idx] for idx in available_indexes]
    if target_count <= 0:
        return []

    rng = random.Random(stable_seed(*seed_parts))
    chosen_indexes = set()
    total = len(keys)
    for bucket in range(target_count):
        start = math.floor(bucket * total / target_count)
        end = math.floor((bucket + 1) * total / target_count)
        candidates = [
            idx for idx in range(start, max(start + 1, end))
            if idx < total and keys[idx] not in exclude and idx not in chosen_indexes
        ]
        if candidates:
            chosen_indexes.add(rng.choice(candidates))

    if len(chosen_indexes) < target_count:
        leftovers = [idx for idx in available_indexes if idx not in chosen_indexes]
        rng.shuffle(leftovers)
        chosen_indexes.update(leftovers[: target_count - len(chosen_indexes)])

    return [keys[idx] for idx in sorted(chosen_indexes)]


def wilson_lower_bound(successes: int, trials: int, z: float = 1.28):
    if trials <= 0:
        return 0.0
    p = successes / trials
    denom = 1 + z * z / trials
    centre = p + z * z / (2 * trials)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * trials)) / trials)
    return max(0.0, (centre - margin) / denom)


@dataclass
class SubscriptionEstimate:
    url: str
    total_keys: int = 0
    checked: dict[str, bool] = field(default_factory=dict)
    fetch_error: str | None = None

    @property
    def checked_count(self):
        return len(self.checked)

    @property
    def alive_count(self):
        return sum(1 for result in self.checked.values() if result.get("ok"))

    @property
    def alive_rate(self):
        return self.alive_count / self.checked_count if self.checked_count else 0.0

    @property
    def estimated_alive(self):
        return self.alive_rate * self.total_keys

    @property
    def alive_elapsed_ms(self):
        return [
            result["elapsed_ms"]
            for result in self.checked.values()
            if result.get("ok") and result.get("elapsed_ms") is not None
        ]

    @property
    def median_alive_ms(self):
        values = self.alive_elapsed_ms
        return statistics.median(values) if values else None

    @property
    def score(self):
        confidence_rate = wilson_lower_bound(self.alive_count, self.checked_count)
        volume_score = math.log1p(self.estimated_alive) / math.log(10_000)
        evidence_score = min(1.0, self.alive_count / 25)
        if self.median_alive_ms is None:
            latency_score = 0.0
        else:
            latency_score = max(0.0, min(1.0, (8_000 - self.median_alive_ms) / 7_000))
        size_penalty = 0.0 if self.total_keys else 0.25
        return (
            confidence_rate * 620
            + volume_score * 190
            + evidence_score * 70
            + latency_score * 120
            - size_penalty * 100
        )

    def as_record(self):
        return {
            "url": self.url,
            "total_keys": self.total_keys,
            "checked": self.checked_count,
            "alive": self.alive_count,
            "alive_rate": round(self.alive_rate, 4),
            "estimated_alive": round(self.estimated_alive, 2),
            "median_alive_ms": round(self.median_alive_ms, 2) if self.median_alive_ms is not None else None,
            "score": round(self.score, 4),
            "fetch_error": self.fetch_error,
        }


async def ping_sample(keys, kind: str, xray_bin: Path, concurrency: int, timeout: float, base_port: int):
    results = {}
    queue = asyncio.Queue()
    for idx, key in enumerate(keys):
        queue.put_nowait((idx, key))

    async def worker():
        while True:
            try:
                idx, key = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                started = asyncio.get_running_loop().time()
                ok = await check_one(key, kind, xray_bin, base_port + idx, timeout)
                elapsed_ms = (asyncio.get_running_loop().time() - started) * 1000
                results[key] = {"ok": ok, "elapsed_ms": elapsed_ms}
            finally:
                queue.task_done()

    workers_count = min(max(1, concurrency), max(1, len(keys)))
    await asyncio.gather(*(worker() for _ in range(workers_count)))
    return results


async def refine_subscription(
    estimate: SubscriptionEstimate,
    stage_name: str,
    target_checked: int,
    xray_bin: Path,
    concurrency: int,
    timeout: float,
    base_port: int,
):
    try:
        keys = fetch_subscription_keys(estimate.url)
    except Exception as exc:
        estimate.fetch_error = str(exc)
        return estimate

    estimate.total_keys = len(keys)
    needed = min(target_checked, len(keys)) - estimate.checked_count
    if needed <= 0:
        return estimate

    sample = stratified_sample(
        keys,
        needed,
        exclude=set(estimate.checked),
        seed_parts=(estimate.url, stage_name, target_checked),
    )
    if not sample:
        return estimate

    kind = f"subs:{stage_name}"
    results = await ping_sample(sample, kind, xray_bin, concurrency, timeout, base_port)
    estimate.checked.update(results)
    return estimate


def rank_subscription_estimates(estimates, limit=None, max_per_source=2):
    ranked = sorted(
        [item for item in estimates if item.total_keys > 0 and item.checked_count > 0],
        key=lambda item: (item.score, item.alive_count, item.total_keys),
        reverse=True,
    )

    selected = []
    selected_urls = set()
    source_counts = {}
    for item in ranked:
        source = subscription_source_key(item.url)
        if source_counts.get(source, 0) >= max_per_source:
            continue
        selected.append(item)
        selected_urls.add(item.url)
        source_counts[source] = source_counts.get(source, 0) + 1
        if limit is not None and len(selected) >= limit:
            return selected

    for item in ranked:
        if item.url in selected_urls:
            continue
        selected.append(item)
        if limit is not None and len(selected) >= limit:
            break

    return selected


async def select_top_subscriptions_by_ping(
    urls,
    xray_bin: Path,
    concurrency: int = 50,
    timeout: float = 10.0,
    stage1_sample: int = 80,
    stage1_keep: int = 30,
    stage2_sample: int = 450,
    stage2_keep: int = 15,
    stage3_sample: int = 1000,
    close_extra_sample: int = 1500,
    close_score_delta: float = 20.0,
    limit: int = 10,
    base_port: int = 30000,
):
    estimates = [SubscriptionEstimate(url=url) for url in urls]
    stages = [
        ("stage1", stage1_sample, stage1_keep),
        ("stage2", stage2_sample, stage2_keep),
        ("stage3", stage3_sample, None),
    ]

    candidates = estimates
    port_cursor = base_port
    for stage_name, target_checked, keep in stages:
        print(f"[{stage_name}] подписок: {len(candidates)}, цель проверок на подписку: {target_checked}")
        for idx, estimate in enumerate(candidates, start=1):
            await refine_subscription(
                estimate,
                stage_name,
                target_checked,
                xray_bin,
                concurrency,
                timeout,
                port_cursor,
            )
            port_cursor += max(2000, target_checked + 100)
            print(
                f"[{stage_name}] {idx}/{len(candidates)} "
                f"keys={estimate.total_keys} checked={estimate.checked_count} "
                f"alive={estimate.alive_count} score={estimate.score:.1f}"
            )
        candidates = rank_subscription_estimates(candidates, keep)

    ranked = rank_subscription_estimates(candidates, None)
    if len(ranked) > limit:
        cutoff = ranked[limit - 1].score
        close = [item for item in ranked if item.score >= cutoff - close_score_delta]
        if len(close) > limit:
            print(f"[final] близких кандидатов: {len(close)}, уточняю до {close_extra_sample} проверок")
            for idx, estimate in enumerate(close, start=1):
                await refine_subscription(
                    estimate,
                    "close",
                    close_extra_sample,
                    xray_bin,
                    concurrency,
                    timeout,
                    port_cursor,
                )
                port_cursor += max(2500, close_extra_sample + 100)
                print(
                    f"[final] {idx}/{len(close)} "
                    f"keys={estimate.total_keys} checked={estimate.checked_count} "
                    f"alive={estimate.alive_count} score={estimate.score:.1f}"
                )

    return rank_subscription_estimates(candidates, limit), estimates


def subscription_source_key(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    parts = [part for part in parsed.path.split("/") if part]

    if host == "raw.githubusercontent.com" and len(parts) >= 2:
        return f"github:{parts[0]}/{parts[1]}".lower()
    if host.endswith("github.com") and len(parts) >= 2:
        return f"github:{parts[0]}/{parts[1]}".lower()
    if host.endswith("gitverse.ru") and "repos" in parts:
        repos_index = parts.index("repos")
        if len(parts) > repos_index + 2:
            return f"gitverse:{parts[repos_index + 1]}/{parts[repos_index + 2]}".lower()
    return host


def subscription_score(record):
    total = record["total"]
    unique = record["unique"]
    alive = record["alive"]
    alive_rate = alive / unique if unique else 0
    unique_rate = unique / total if total else 0
    noise_rate = 1 - unique_rate if total else 1

    return (
        alive * 1_000
        + alive_rate * 300
        + unique_rate * 100
        - noise_rate * 50
    )


def select_top_subscriptions(records, limit=10, max_per_source=2):
    candidates = [
        record
        for record in records
        if record["alive"] > 0 and record["unique"] > 0
    ]
    ranked = sorted(
        candidates,
        key=lambda item: (
            subscription_score(item),
            item["alive"],
            item["unique"],
        ),
        reverse=True,
    )

    selected = []
    selected_urls = set()
    source_counts = {}
    for record in ranked:
        source = subscription_source_key(record["url"])
        if source_counts.get(source, 0) >= max_per_source:
            continue
        selected.append(record)
        selected_urls.add(record["url"])
        source_counts[source] = source_counts.get(source, 0) + 1
        if len(selected) >= limit:
            return selected

    for record in ranked:
        if record["url"] in selected_urls:
            continue
        selected.append(record)
        if len(selected) >= limit:
            break

    return selected


def build_json_and_top10(
    input_path: Path,
    output_dir: Path,
    name_suffix: str | None = None,
    xray_bin: Path | str = "xrayFile/xray",
    concurrency: int = 50,
    timeout: float = 10.0,
    base_port: int = 30000,
):
    if not input_path.exists():
        raise FileNotFoundError(f"Не найден входной файл: {input_path}")

    urls = read_subscription_urls(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    base_name = name_suffix or "subs"
    json_path = output_dir / f"{base_name}.json"
    top10_path = output_dir / f"{base_name}_top10.txt"

    xray_path = Path(xray_bin)
    if not xray_path.exists():
        raise FileNotFoundError(f"Не найден xray: {xray_path}")

    top10, estimates = asyncio.run(
        select_top_subscriptions_by_ping(
            urls=urls,
            xray_bin=xray_path,
            concurrency=concurrency,
            timeout=timeout,
            base_port=base_port,
        )
    )
    records = [item.as_record() for item in rank_subscription_estimates(estimates, None)]

    payload = {
        "checked_at": checked_at,
        "source_file": str(input_path),
        "subscriptions_total": len(urls),
        "algorithm": {
            "name": "multi_stage_stratified_ping_sampling",
            "stage_samples": [80, 450, 1000],
            "final_close_sample": 1500,
            "score": "620*wilson_alive_rate + 190*log_estimated_alive + 70*alive_evidence + 120*latency",
            "concurrency": concurrency,
            "timeout": timeout,
        },
        "subscriptions": records,
        "top10": [item.as_record() for item in top10],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    top10_path.write_text("\n".join(item.url for item in top10) + ("\n" if top10 else ""), encoding="utf-8")

    return {
        "json_path": json_path,
        "top10_path": top10_path,
        "records": len(urls),
        "selected": len(top10),
    }


def read_top_urls(path: Path):
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line and URL_RE.match(line)]


def read_urls_from_pairs_file(path: Path):
    if not path.exists():
        return set()
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if all(URL_RE.match(line) for line in lines):
        return set(lines)

    urls = set()
    for i in range(0, len(lines), 2):
        url = lines[i]
        if URL_RE.match(url):
            urls.add(url)
    return urls


def read_urls_from_list_file(path: Path):
    if not path.exists():
        return set()
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return {line for line in lines if line and URL_RE.match(line)}


def fetch_lines(url: str):
    try:
        with urlopen(url, timeout=30) as response:
            text = response.read().decode("utf-8", errors="replace")
    except Exception:
        result = subprocess.run(
            ["curl", "-L", "--insecure", "--max-time", "30", url],
            check=True,
            capture_output=True,
            text=True,
        )
        text = result.stdout
    return [line.strip() for line in text.splitlines() if line.strip()]


def is_ru_key(key: str):
    decoded = unquote(key)
    if "🇷🇺" in decoded or "%F0%9F%87%B7%F0%9F%87%BA" in key.upper():
        return True
    desc = decoded.split("#", 1)[1] if "#" in decoded else ""
    return bool(RU_WORD_RE.search(desc))


def extract_keys_from_top10(
    top10_path: Path,
    output_dir: Path,
    force_ru_sources_path: Path | None = None,
    trojan_ru_sources_path: Path | None = None,
):
    urls = read_top_urls(top10_path)
    force_ru_urls = read_urls_from_pairs_file(force_ru_sources_path) if force_ru_sources_path else set()
    trojan_ru_urls = read_urls_from_list_file(trojan_ru_sources_path) if trojan_ru_sources_path else set()
    vless_keys = []
    ss_keys = []
    vless_ru_keys = []
    failed = []

    for url in urls:
        force_ru = url in force_ru_urls
        allow_trojan_ru = url in trojan_ru_urls
        try:
            lines = fetch_lines(url)
        except Exception as exc:
            failed.append((url, str(exc)))
            continue

        for line in lines:
            if line.startswith("vless://"):
                if force_ru or is_ru_key(line):
                    vless_ru_keys.append(line)
                else:
                    vless_keys.append(line)
            elif line.startswith("ss://"):
                if not (force_ru or is_ru_key(line)):
                    ss_keys.append(line)
            elif line.startswith("trojan://"):
                if allow_trojan_ru:
                    vless_ru_keys.append(line)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "vless.txt").write_text("\n".join(vless_keys) + ("\n" if vless_keys else ""), encoding="utf-8")
    (output_dir / "ss.txt").write_text("\n".join(ss_keys) + ("\n" if ss_keys else ""), encoding="utf-8")
    (output_dir / "vless_RU.txt").write_text("\n".join(vless_ru_keys) + ("\n" if vless_ru_keys else ""), encoding="utf-8")

    return {
        "urls_total": len(urls),
        "failed": failed,
        "vless_total": len(vless_keys),
        "ss_total": len(ss_keys),
        "vless_ru": len(vless_ru_keys),
    }
