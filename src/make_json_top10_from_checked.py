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
build_json_and_top10 = MODULE.build_json_and_top10


def main():
    parser = argparse.ArgumentParser(description="Формирует JSON и top10 из проверенного файла подписок.")
    parser.add_argument("--input", default="file/1AllLinksFromGit/default.txt")
    parser.add_argument("--whitelist-input", default="file/1AllLinksFromGit/whiteList.txt")
    parser.add_argument("--output-dir", default="file/2TopLinksFromGit")
    parser.add_argument("--default-name", default="default")
    parser.add_argument("--whitelist-name", default="whiteList")
    args = parser.parse_args()

    default_result = build_json_and_top10(
        Path(args.input),
        Path(args.output_dir),
        args.default_name,
    )
    whitelist_result = build_json_and_top10(
        Path(args.whitelist_input),
        Path(args.output_dir),
        args.whitelist_name,
    )
    print(f"[default] Готово: {default_result['json_path']}")
    print(f"[default] Готово: {default_result['top10_path']}")
    print(f"[default] Обработано подписок: {default_result['records']}")
    print(f"[whiteList] Готово: {whitelist_result['json_path']}")
    print(f"[whiteList] Готово: {whitelist_result['top10_path']}")
    print(f"[whiteList] Обработано подписок: {whitelist_result['records']}")


if __name__ == "__main__":
    main()
