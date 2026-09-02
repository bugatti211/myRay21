#!/usr/bin/env python3
"""Publish the live Trojan experiment without changing its descriptions."""

from pathlib import Path

import write_git_publish_files as publisher


SOURCE = Path("file/4LiveKeys/trojan_ping_ok.txt")
TARGET = Path("git/Trojan")


def main() -> int:
    if not TARGET.parent.exists():
        print(f"[error] git dir not found: {TARGET.parent}")
        return 1
    rows = [row for row in publisher.iter_links(SOURCE) if row.startswith("trojan://")]
    publisher.write_target(TARGET, publisher.dedupe_keep_order(rows))
    print(f"[ok] written {TARGET} ({len(rows)} keys)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
