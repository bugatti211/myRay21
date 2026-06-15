#!/usr/bin/env python3
from pathlib import Path
import sys
import subprocess
import importlib.util
from datetime import datetime, timedelta
import time

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

_shared_tools_path = SRC / "pipeline_shared_tools.py"
_shared_tools_spec = importlib.util.spec_from_file_location("pipeline_shared_tools", _shared_tools_path)
if _shared_tools_spec is None or _shared_tools_spec.loader is None:
    raise RuntimeError(f"Cannot load shared tools from: {_shared_tools_path}")
_shared_tools = importlib.util.module_from_spec(_shared_tools_spec)
_shared_tools_spec.loader.exec_module(_shared_tools)
build_json_and_top10 = _shared_tools.build_json_and_top10
extract_keys_from_top10 = _shared_tools.extract_keys_from_top10


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


def wait_until_configured_start_time():
    start_time = config_value("START_TIME", None)
    if start_time is None or str(start_time).strip() == "":
        return

    try:
        hour_text, minute_text = str(start_time).strip().split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError
    except ValueError:
        print('Неверный START_TIME в pipeline_config.py, нужен формат "ЧЧ:ММ"')
        sys.exit(1)

    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)

    wait_seconds = (target - now).total_seconds()
    print(f"Жду до {target:%Y-%m-%d %H:%M} для запуска пайплайна")
    time.sleep(wait_seconds)


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
    trojan_ru_sources = "file/2TopLinksFromGit/whiteList_top10.txt"

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
        Path(trojan_ru_sources),
    )
    print(f"\nГотово: {Path(keys_dir) / 'vless.txt'} ({result['vless_total']})")
    print(f"Готово: {Path(keys_dir) / 'ss.txt'} ({result['ss_total']})")
    print(f"Готово: {Path(keys_dir) / 'vless_RU.txt'} ({result['vless_ru']})")
    if result["failed"]:
        print("Не удалось скачать некоторые подписки:")
        for url, error in result["failed"]:
            print(f"- {url}: {error}")


def run_ping_check():
    vless_file = "file/3KeysFromGit/vless.txt"
    vless_ru_file = "file/3KeysFromGit/vless_RU.txt"
    ss_file = "file/3KeysFromGit/ss.txt"
    xray_bin = "xrayFile/xray"
    output_dir = "file/4LiveKeys"
    concurrency = config_str("PING_CONCURRENCY", 100)
    timeout = config_str("PING_TIMEOUT", 12)
    max_alive_vless = config_str("MAX_ALIVE_VLESS", 0)
    max_alive_ss = config_str("MAX_ALIVE_SS", 0)

    cmd = [
        "python3",
        "src/ping_keys_with_xray.py",
        "--vless-file",
        vless_file,
        "--vless-ru-file",
        vless_ru_file,
        "--ss-file",
        ss_file,
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
        "--max-alive-ss",
        max_alive_ss,
    ]
    subprocess.run(cmd, check=True)

def run_rerank_top_from_alive():
    input_dir = "file/4LiveKeys"
    output_dir = "file/5TopLiveKeys"
    xray_bin = "xrayFile/xray"
    concurrency = config_str("RERANK_CONCURRENCY", 100)
    timeout = config_str("RERANK_TIMEOUT", 12)
    runs = config_str("RERANK_RUNS", 3)

    cmd = [
        "python3",
        "src/rerank_ping_ok_keys.py",
        "--input-dir",
        input_dir,
        "--output-dir",
        output_dir,
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
    file_glob = "*_ping_ok.txt"
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


def run_send_ss_to_telegram():
    cmd = ["python3", "src/send_ss_to_telegram.py"]
    subprocess.run(cmd, check=True)


def run_git_commit_and_notify():
    cmd = ["python3", "src/git_commit_push_and_notify.py"]
    subprocess.run(cmd, check=True)


def build_steps():
    return [
        ("Сформировать JSON + top10", run_top10_only),
        ("Сформировать ключи из top10", run_keys_only),
        ("Проверка ключей через xray (ping) и запись живых", run_ping_check),
        ("3 прогона по живым ключам и отбор топ лучших", run_rerank_top_from_alive),
        ("Переписать описания top ключей (канал + номер + флаг)", run_rewrite_toplive_descriptions),
        ("Записать top live ключи в git файлы", run_write_git_from_toplive),
        ("Отправить SS ключи в Telegram", run_send_ss_to_telegram),
        ("Git commit + push + Telegram notify", run_git_commit_and_notify),
    ]


def ask_manual_start_step(steps):
    print("Выберите шаг, с которого начать:")
    for i, (title, _) in enumerate(steps, start=1):
        print(f"{i}. {title}")

    choice = input(f"Введите номер шага (1-{len(steps)}): ").strip()
    if not choice.isdigit():
        print("Неверный выбор")
        sys.exit(1)

    return int(choice) - 1


def config_start_step_idx(steps):
    start_step = config_value("START_STEP", None)
    if start_step is None:
        return ask_manual_start_step(steps)

    try:
        return int(start_step) - 1
    except (TypeError, ValueError):
        print("Неверный START_STEP в pipeline_config.py")
        sys.exit(1)


def ask_run_mode():
    print("Выберите режим запуска:")
    print("1. Запустить прямо сейчас и выбрать шаг вручную")
    print("2. Запустить по данным из pipeline_config.py")

    choice = input("Введите 1 или 2: ").strip()
    if choice == "1":
        return "manual_now"
    if choice == "2":
        return "config"

    print("Неверный выбор")
    sys.exit(1)


def main():
    steps = build_steps()
    run_mode = ask_run_mode()

    if run_mode == "manual_now":
        start_idx = ask_manual_start_step(steps)
    else:
        wait_until_configured_start_time()
        start_idx = config_start_step_idx(steps)

    print("Шаги пайплайна:")
    for i, (title, _) in enumerate(steps, start=1):
        print(f"{i}. {title}")
    if start_idx < 0 or start_idx >= len(steps):
        print("Неверный выбор")
        sys.exit(1)

    print(f"\nСтартую с шага {start_idx + 1}")

    for i, (title, fn) in enumerate(steps[start_idx:], start=start_idx + 1):
        print(f"\n[step {i}/{len(steps)}] {title}")
        fn()


if __name__ == "__main__":
    main()
