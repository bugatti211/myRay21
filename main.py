#!/usr/bin/env python3
from pathlib import Path
import sys
import subprocess
<<<<<<< HEAD
import importlib.util
=======
import re
from datetime import datetime, timedelta
import time
>>>>>>> authostart

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

<<<<<<< HEAD
_shared_tools_path = SRC / "pipeline_shared_tools.py"
_shared_tools_spec = importlib.util.spec_from_file_location("pipeline_shared_tools", _shared_tools_path)
if _shared_tools_spec is None or _shared_tools_spec.loader is None:
    raise RuntimeError(f"Cannot load shared tools from: {_shared_tools_path}")
_shared_tools = importlib.util.module_from_spec(_shared_tools_spec)
_shared_tools_spec.loader.exec_module(_shared_tools)
build_json_and_top10 = _shared_tools.build_json_and_top10
extract_keys_from_top10 = _shared_tools.extract_keys_from_top10


def ask(prompt: str, default: str) -> str:
    value = input(f"{prompt} [{default}]: ").strip()
    return value or default


def default_top10_path() -> str:
    return "file/2TopLinksFromGit/default_top10.txt"


def run_top10_only():
    input_path = "file/1AllLinksFromGit/default.txt"
    whitelist_path = "file/1AllLinksFromGit/whiteList.txt"
    output_dir = "file/2TopLinksFromGit"

    default_result = build_json_and_top10(
        Path(input_path),
        Path(output_dir),
        "default",
    )
    whitelist_result = build_json_and_top10(
        Path(whitelist_path),
        Path(output_dir),
        "whiteList",
    )
    print(f"\n[default] Готово: {default_result['json_path']}")
    print(f"[default] Готово: {default_result['top10_path']}")
    print(f"[default] Обработано подписок: {default_result['records']}")
    print(f"\n[whiteList] Готово: {whitelist_result['json_path']}")
    print(f"[whiteList] Готово: {whitelist_result['top10_path']}")
    print(f"[whiteList] Обработано подписок: {whitelist_result['records']}")


def run_keys_only():
    default_top10 = Path("file/2TopLinksFromGit/default_top10.txt")
    whitelist_top10 = Path("file/2TopLinksFromGit/whiteList_top10.txt")
    keys_dir = "file/3KeysFromGit"
    force_ru_sources = "file/1AllLinksFromGit/whiteList.txt"

    top10_lines = []
    seen = set()
    for path in [default_top10, whitelist_top10]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            row = line.strip()
            if not row or row in seen:
                continue
            seen.add(row)
            top10_lines.append(row)

    if not top10_lines:
        fallback = Path(default_top10_path())
        if fallback.exists():
            for line in fallback.read_text(encoding="utf-8").splitlines():
                row = line.strip()
                if not row or row in seen:
                    continue
                seen.add(row)
                top10_lines.append(row)
        else:
            raise FileNotFoundError("Не найдено top10 файлов для шага 2")

    combined_top10 = Path("file/2TopLinksFromGit/_combined_top10.txt")
    combined_top10.write_text("\n".join(top10_lines) + "\n", encoding="utf-8")

    result = extract_keys_from_top10(
        combined_top10,
        Path(keys_dir),
        Path(force_ru_sources),
    )
    print(f"\nГотово: {Path(keys_dir) / 'vless.txt'} ({result['vless_total']})")
    print(f"Готово: {Path(keys_dir) / 'ss.txt'} ({result['ss_total']})")
    print(f"Готово: {Path(keys_dir) / 'vless_RU.txt'} ({result['vless_ru']})")
    print(f"Готово: {Path(keys_dir) / 'ss_RU.txt'} ({result['ss_ru']})")
=======
from pipeline_shared_tools import extract_keys_from_top15


try:
    import pipeline_config as config
except ImportError:
    config = None


def config_value(name: str, default):
    if config is None:
        return default
    return getattr(config, name, default)


def config_str(name: str, default) -> str:
    return str(config_value(name, default))


def count_key_rows(*paths: Path) -> int:
    endpoints = set()
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(
            encoding="utf-8",
            errors="ignore",
        ).splitlines():
            row = line.strip()
            if row and not row.startswith("#"):
                endpoints.add(row.split("#", 1)[0])
    return len(endpoints)


def parse_start_times(value):
    if value is None:
        return []

    if isinstance(value, str):
        raw_values = re.split(r"[,;\s]+", value.strip()) if value.strip() else []
    elif isinstance(value, (list, tuple, set)):
        raw_values = []
        for item in value:
            text = str(item).strip()
            if text:
                raw_values.extend(re.split(r"[,;\s]+", text))
    else:
        raw_values = [str(value).strip()]

    parsed = set()
    for raw_value in raw_values:
        try:
            hour_text, minute_text = raw_value.split(":", 1)
            hour = int(hour_text)
            minute = int(minute_text)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"неверное значение {raw_value!r}, нужен формат ЧЧ:ММ"
            ) from exc
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError(
                f"неверное значение {raw_value!r}, нужен формат ЧЧ:ММ"
            )
        parsed.add((hour, minute))
    return sorted(parsed)


def first_schedule_slot(schedule, now: datetime) -> datetime:
    current_minute = now.replace(second=0, microsecond=0)
    for hour, minute in schedule:
        candidate = now.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        if candidate >= current_minute:
            return candidate
    hour, minute = schedule[0]
    return (now + timedelta(days=1)).replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )


def following_schedule_slot(schedule, previous: datetime) -> datetime:
    for hour, minute in schedule:
        candidate = previous.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        if candidate > previous:
            return candidate
    hour, minute = schedule[0]
    return (previous + timedelta(days=1)).replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )


def run_extract_vless_keys():
    whitelist_top15 = Path("file/2TopLinksFromGit/whiteList_top15.txt")
    keys_dir = "file/3KeysFromGit"

    if not whitelist_top15.exists():
        raise FileNotFoundError(
            f"Не сформирован файл top15: {whitelist_top15}"
        )

    result = extract_keys_from_top15(
        whitelist_top15,
        Path(keys_dir),
        include_ss=False,
    )
    print(f"\nГотово: {Path(keys_dir) / 'vless.txt'} ({result['vless_total']})")
    print(f"Готово: {Path(keys_dir) / 'vless_RU.txt'} ({result['vless_ru']})")
    print(f"Готово: {Path(keys_dir) / 'trojan.txt'} ({result['trojan_total']})")
>>>>>>> authostart
    if result["failed"]:
        print("Не удалось скачать некоторые подписки:")
        for url, error in result["failed"]:
            print(f"- {url}: {error}")

<<<<<<< HEAD

def run_ping_check():
    vless_file = "file/3KeysFromGit/vless.txt"
    vless_ru_file = "file/3KeysFromGit/vless_RU.txt"
    ss_file = "file/3KeysFromGit/ss.txt"
    ss_ru_file = "file/3KeysFromGit/ss_RU.txt"
    xray_bin = "xrayFile/xray"
    output_dir = "file/4LiveKeys"
    concurrency = ask("Параллельных проверок", "100")
    timeout = "12"
    max_alive_vless = ask("Лимит живых vless (0 = без лимита)", "0")
    max_alive_ss = ask("Лимит живых ss (0 = без лимита)", "0")
=======
def run_ping_check():
    vless_file = "file/3KeysFromGit/vless.txt"
    vless_ru_file = "file/3KeysFromGit/vless_RU.txt"
    trojan_file = "file/3KeysFromGit/trojan.txt"
    xray_bin = "xrayFile/xray"
    output_dir = "file/4LiveKeys"
    concurrency = config_str("PING_CONCURRENCY", 100)
    timeout = config_str("PING_TIMEOUT", 12)
    max_alive_vless = config_str("MAX_ALIVE_VLESS", 0)
    max_alive_trojan = config_str("MAX_ALIVE_TROJAN", 50)

    published_base = config_str(
        "PUBLISHED_SUBSCRIPTIONS_BASE_URL",
        (
            "https://raw.githubusercontent.com/terik21/"
            "HiddifySubs-VlessKeys/main"
        ),
    )
    published_timeout = config_str("PUBLISHED_DOWNLOAD_TIMEOUT", 30)
    subprocess.run(
        [
            "python3",
            "src/merge_published_subscriptions.py",
            "--remote-base",
            published_base,
            "--timeout",
            published_timeout,
        ],
        check=True,
    )
    priority_vless = count_key_rows(
        Path("file/3KeysFromGit/published_main.txt")
    )
    priority_vless_ru = count_key_rows(
        Path("file/3KeysFromGit/published_WhiteKeys.txt"),
        Path("file/3KeysFromGit/published_WhiteKeys2.txt"),
    )
>>>>>>> authostart

    cmd = [
        "python3",
        "src/ping_keys_with_xray.py",
        "--vless-file",
        vless_file,
        "--vless-ru-file",
        vless_ru_file,
<<<<<<< HEAD
        "--ss-file",
        ss_file,
        "--ss-ru-file",
        ss_ru_file,
=======
        "--trojan-file",
        trojan_file,
>>>>>>> authostart
        "--xray-bin",
        xray_bin,
        "--output-dir",
        output_dir,
        "--concurrency",
        concurrency,
        "--timeout",
        timeout,
        "--max-alive-vless",
        max_alive_vless,
<<<<<<< HEAD
        "--max-alive-ss",
        max_alive_ss,
    ]
    subprocess.run(cmd, check=True)

def run_rerank_top_from_alive():
    input_dir = "file/4LiveKeys"
    output_dir = "file/5TopLiveKeys"
    xray_bin = "xrayFile/xray"
    concurrency = ask("Параллельных проверок", "100")
    timeout = "12"
    runs = ask("Кол-во прогонов для ранжирования", "3")
=======
        "--max-alive-trojan",
        max_alive_trojan,
        "--priority-vless-count",
        str(priority_vless),
        "--priority-vless-ru-count",
        str(priority_vless_ru),
        "--skip-ss",
    ]
    subprocess.run(cmd, check=True)

def run_rerank_top_from_alive(glob="vless*_ping_ok.txt"):
    input_dir = "file/4LiveKeys"
    output_dir = "file/5TopLiveKeys"
    xray_bin = "xrayFile/xray"
    concurrency = config_str("RERANK_CONCURRENCY", 100)
    timeout = config_str("RERANK_TIMEOUT", 12)
    runs = config_str("RERANK_RUNS", 3)
>>>>>>> authostart

    cmd = [
        "python3",
        "src/rerank_ping_ok_keys.py",
        "--input-dir",
        input_dir,
        "--output-dir",
        output_dir,
<<<<<<< HEAD
=======
        "--glob",
        glob,
>>>>>>> authostart
        "--xray-bin",
        xray_bin,
        "--concurrency",
        concurrency,
        "--timeout",
        timeout,
        "--runs",
        runs,
    ]
    subprocess.run(cmd, check=True)


def run_rewrite_toplive_descriptions():
    input_dir = "file/5TopLiveKeys"
<<<<<<< HEAD
    file_glob = "*_ping_ok.txt"
=======
    file_glob = "vless*_ping_ok.txt"
>>>>>>> authostart
    channel = "t.me/freekesha21"

    cmd = [
        "python3",
        "src/rewrite_toplive_descriptions.py",
        "--dir",
        input_dir,
        "--glob",
        file_glob,
        "--channel",
        channel,
    ]
    subprocess.run(cmd, check=True)


def run_write_git_from_toplive():
    cmd = ["python3", "src/write_git_publish_files.py"]
    subprocess.run(cmd, check=True)


<<<<<<< HEAD
def run_send_ss_to_telegram():
    cmd = ["python3", "src/send_ss_to_telegram.py"]
    subprocess.run(cmd, check=True)


def run_git_commit_and_notify():
    cmd = ["python3", "src/git_commit_push_and_notify.py"]
=======
def run_write_trojan_subscription():
    cmd = ["python3", "src/write_trojan_subscription.py"]
    subprocess.run(cmd, check=True)


def run_git_commit_push():
    cmd = ["python3", "src/git_commit_push.py"]
>>>>>>> authostart
    subprocess.run(cmd, check=True)


def build_steps():
    return [
<<<<<<< HEAD
        ("Сформировать JSON + top10", run_top10_only),
        ("Сформировать ключи из top10", run_keys_only),
        ("Проверка ключей через xray (ping) и запись живых", run_ping_check),
        ("3 прогона по живым ключам и отбор топ лучших", run_rerank_top_from_alive),
        ("Переписать описания top ключей (канал + номер + флаг)", run_rewrite_toplive_descriptions),
        ("Записать top live ключи в git файлы", run_write_git_from_toplive),
        ("Отправить SS ключи в Telegram", run_send_ss_to_telegram),
        ("Git commit + push + Telegram notify", run_git_commit_and_notify),
    ]


def main():
    steps = build_steps()
    print("Выберите шаг, с которого начать:")
    for i, (title, _) in enumerate(steps, start=1):
        print(f"{i}. {title}")

    choice = input(f"Введите номер шага (1-{len(steps)}): ").strip()
    if not choice.isdigit():
        print("Неверный выбор")
        sys.exit(1)

    start_idx = int(choice) - 1
    if start_idx < 0 or start_idx >= len(steps):
        print("Неверный выбор")
        sys.exit(1)

    for i, (title, fn) in enumerate(steps[start_idx:], start=start_idx + 1):
        print(f"\n[step {i}/{len(steps)}] {title}")
        fn()
=======
        ("Сформировать VLESS/Hysteria 2/Trojan ключи из top15", run_extract_vless_keys),
        (
            "Скачать опубликованные подписки и проверить все ключи через Xray",
            run_ping_check,
        ),
        ("3 прогона по живым VLESS ключам и отбор топ лучших", run_rerank_top_from_alive),
        ("Переписать описания top VLESS ключей (канал + номер + флаг)", run_rewrite_toplive_descriptions),
        ("Записать top live VLESS ключи в git файлы", run_write_git_from_toplive),
        ("Записать до 50 живых Trojan ключей в git/Trojan", run_write_trojan_subscription),
        ("Git commit + push", run_git_commit_push),
    ]


def config_start_step_idx(steps):
    start_step = config_value("START_STEP", None)
    if start_step is None:
        print("Не задан START_STEP в pipeline_config.py")
        sys.exit(1)

    try:
        return int(start_step) - 1
    except (TypeError, ValueError):
        print("Неверный START_STEP в pipeline_config.py")
        sys.exit(1)


def run_pipeline_once(steps):
    start_idx = config_start_step_idx(steps)

    print("VLESS/Hysteria 2 пайплайн без SS и Telegram:")
    for i, (title, _) in enumerate(steps, start=1):
        print(f"{i}. {title}")
    if start_idx < 0 or start_idx >= len(steps):
        print("Неверный выбор")
        sys.exit(1)

    print(f"\nСтартую с шага {start_idx + 1}")

    for i, (title, fn) in enumerate(steps[start_idx:], start=start_idx + 1):
        print(f"\n[step {i}/{len(steps)}] {title}")
        fn()


def main():
    steps = build_steps()
    try:
        schedule = parse_start_times(config_value("START_TIME", None))
    except ValueError as exc:
        print(f"Неверный START_TIME в pipeline_config.py: {exc}")
        sys.exit(1)

    if not schedule:
        print("START_TIME не задан: выполняю пайплайн один раз сразу")
        run_pipeline_once(steps)
        return

    schedule_text = ", ".join(
        f"{hour:02d}:{minute:02d}"
        for hour, minute in schedule
    )
    print(f"Ежедневное расписание пайплайна: {schedule_text}")
    target = first_schedule_slot(schedule, datetime.now())

    while True:
        wait_seconds = max(0.0, (target - datetime.now()).total_seconds())
        if wait_seconds > 0:
            print(f"Жду до {target:%Y-%m-%d %H:%M} для запуска пайплайна")
            time.sleep(wait_seconds)
        else:
            print(f"Запускаю точку расписания {target:%Y-%m-%d %H:%M}")

        try:
            run_pipeline_once(steps)
            print(f"Точка расписания {target:%Y-%m-%d %H:%M} завершена")
        except Exception as exc:
            print(
                f"[schedule error] запуск {target:%Y-%m-%d %H:%M} завершился "
                f"ошибкой {type(exc).__name__}: {exc}"
            )

        target = following_schedule_slot(schedule, target)
>>>>>>> authostart


if __name__ == "__main__":
    main()
