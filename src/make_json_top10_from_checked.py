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
    parser.add_argument("--output-dir", default="file/2TopLinksFromGit")
    args = parser.parse_args()

    result = build_json_and_top10(Path(args.input), Path(args.output_dir))
    print(f"Готово: {result['json_path']}")
    print(f"Готово: {result['top10_path']}")
    print(f"Обработано подписок: {result['records']}")


if __name__ == "__main__":
    main()
