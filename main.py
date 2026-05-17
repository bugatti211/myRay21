#!/usr/bin/env python3
from pathlib import Path
import sys
import subprocess
import importlib.util

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
    if result["failed"]:
        print("Не удалось скачать некоторые подписки:")
        for url, error in result["failed"]:
            print(f"- {url}: {error}")


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

    cmd = [
        "python3",
        "src/ping_keys_with_xray.py",
        "--vless-file",
        vless_file,
        "--vless-ru-file",
        vless_ru_file,
        "--ss-file",
        ss_file,
        "--ss-ru-file",
        ss_ru_file,
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
    concurrency = ask("Параллельных проверок", "100")
    timeout = "12"
    runs = ask("Кол-во прогонов для ранжирования", "3")

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


if __name__ == "__main__":
    main()
