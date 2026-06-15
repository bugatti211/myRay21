#!/usr/bin/env python3
import argparse
from pathlib import Path
import importlib.util


ROOT = Path(__file__).resolve().parent
TOOLS_PATH = ROOT / "pipeline_shared_tools.py"
SPEC = importlib.util.spec_from_file_location("pipeline_shared_tools", TOOLS_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load shared tools from: {TOOLS_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
extract_keys_from_top10 = MODULE.extract_keys_from_top10


def main():
    parser = argparse.ArgumentParser(description="Скачивает ключи из top10 и делит на vless/ss + RU.")
    parser.add_argument("--top10", default="file/2TopLinksFromGit/2026-05-11_top10.txt")
    parser.add_argument("--keys-dir", default="file/3KeysFromGit")
    parser.add_argument("--force-ru-sources", default="file/1AllLinksFromGit/whiteList.txt")
    parser.add_argument("--trojan-ru-sources", default="file/2TopLinksFromGit/whiteList_top10.txt")
    args = parser.parse_args()

    result = extract_keys_from_top10(
        Path(args.top10),
        Path(args.keys_dir),
        Path(args.force_ru_sources),
        Path(args.trojan_ru_sources),
    )
    print(f"Готово: {Path(args.keys_dir) / 'vless.txt'} ({result['vless_total']})")
    print(f"Готово: {Path(args.keys_dir) / 'ss.txt'} ({result['ss_total']})")
    print(f"Готово: {Path(args.keys_dir) / 'vless_RU.txt'} ({result['vless_ru']})")
    if result["failed"]:
        print("Не удалось скачать некоторые подписки:")
        for url, error in result["failed"]:
            print(f"- {url}: {error}")


if __name__ == "__main__":
    main()
