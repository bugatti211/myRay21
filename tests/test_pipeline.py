import asyncio
import base64
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SRC))

import main as orchestrator
import build_wltest_subscription as wltest
import merge_published_subscriptions as published_merge
import ping_keys_with_xray as checker
import pipeline_shared_tools as shared
import rerank_ping_ok_keys as rerank
import write_git_publish_files as publisher
import network_filter

class SubscriptionSelectionTests(unittest.TestCase):
    def test_schedule_accepts_multiple_times_and_removes_duplicates(self):
        self.assertEqual(
            orchestrator.parse_start_times(
                ["21:30", "08:03", "14:00", "08:03"]
            ),
            [(8, 3), (14, 0), (21, 30)],
        )
        self.assertEqual(
            orchestrator.parse_start_times("08:03, 14:00;21:30"),
            [(8, 3), (14, 0), (21, 30)],
        )

    def test_schedule_selects_same_minute_then_next_daily_slot(self):
        schedule = [(8, 3), (14, 0), (21, 30)]
        now = orchestrator.datetime(2026, 7, 24, 14, 0, 42)
        first = orchestrator.first_schedule_slot(schedule, now)
        second = orchestrator.following_schedule_slot(schedule, first)
        last = orchestrator.following_schedule_slot(
            schedule,
            orchestrator.datetime(2026, 7, 24, 21, 30),
        )

        self.assertEqual(
            first,
            orchestrator.datetime(2026, 7, 24, 14, 0),
        )
        self.assertEqual(
            second,
            orchestrator.datetime(2026, 7, 24, 21, 30),
        )
        self.assertEqual(
            last,
            orchestrator.datetime(2026, 7, 25, 8, 3),
        )

    def test_schedule_rejects_invalid_time(self):
        with self.assertRaises(ValueError):
            orchestrator.parse_start_times(["08:03", "25:00"])

    def test_orchestrator_has_only_supported_pipeline(self):
        steps = orchestrator.build_steps()
        self.assertEqual(len(steps), 7)
        self.assertIs(steps[-2][1], orchestrator.run_wltest)
        self.assertIs(steps[-1][1], orchestrator.run_git_commit_push)
        self.assertFalse(any("Telegram" in title or title.startswith("Отправить SS") for title, _ in steps))


class KeyProcessingTests(unittest.TestCase):
    def test_process_cleanup_ignores_already_exited_xray(self):
        class ExitedProcess:
            returncode = None

            def terminate(self):
                raise ProcessLookupError("already exited")

            async def wait(self):
                return 0

        asyncio.run(checker.stop_process(ExitedProcess()))

    def test_ping_worker_exception_does_not_abort_other_keys(self):
        calls = 0

        async def unstable_check(key, kind, xray_bin, socks_port, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ProcessLookupError("already exited")
            return True

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "alive.txt"
            with patch.object(checker, "check_one", unstable_check):
                alive = asyncio.run(
                    checker.run_checks(
                        [
                            "vless://first@example.com:443",
                            "vless://second@example.com:443",
                        ],
                        "test",
                        Path("xray"),
                        1,
                        1.0,
                        20_000,
                        output,
                    )
                )

        self.assertEqual(len(alive), 1)
        self.assertTrue(alive[0].startswith("vless://second@"))

    def test_wltest_can_collect_matching_ips_from_explicit_source_lists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            default_sources = root / "default.txt"
            white_sources = root / "whiteList.txt"
            default_sources.write_text(
                "https://default.example/sub\n",
                encoding="utf-8",
            )
            white_sources.write_text(
                "https://white.example/sub\n",
                encoding="utf-8",
            )
            networks = root / "networks.txt"
            networks.write_text("10.10.0.0/16\n", encoding="utf-8")

            payloads = {
                "https://default.example/sub": [
                    "vless://default@10.10.1.1:443#match",
                    "vless://outside@10.20.1.1:443#outside",
                ],
                "https://white.example/sub": [
                    "hysteria2://secret@10.10.2.2:443/#match",
                    "vless://domain@example.com:443#domain",
                    "trojan://old@10.10.3.3:443#ignored",
                ],
            }

            result = asyncio.run(
                wltest.collect_network_candidates(
                    (default_sources, white_sources),
                    networks,
                    download_concurrency=2,
                    download_retries=0,
                    fetcher=lambda url: payloads[url],
                )
            )

        self.assertEqual(len(result["urls"]), 2)
        self.assertEqual(len(result["supported_keys"]), 4)
        self.assertEqual(len(result["matched_keys"]), 2)
        self.assertTrue(result["matched_keys"][0].startswith("vless://"))
        self.assertTrue(result["matched_keys"][1].startswith("hysteria2://"))

    def test_wltest_defaults_to_whitelist_sources_only(self):
        self.assertEqual(
            wltest.DEFAULT_SOURCE_FILES,
            (Path("file/1AllLinksFromGit/whiteList.txt"),),
        )

    def test_wltest_writes_every_network_match_without_ping(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sources = root / "sources.txt"
            networks = root / "networks.txt"
            output = root / "WLTest"
            work_dir = root / "work"
            sources.write_text("https://source.example/sub\n", encoding="utf-8")
            networks.write_text("10.0.0.0/24\n", encoding="utf-8")
            rows = [
                "vless://one@10.0.0.1:443#one",
                "hysteria2://two@10.0.0.2:443/#two",
                "vless://outside@10.0.1.1:443#outside",
            ]

            report = asyncio.run(
                wltest.build_wltest(
                    source_files=(sources,),
                    networks_file=networks,
                    work_dir=work_dir,
                    output_path=output,
                    download_concurrency=1,
                    download_retries=0,
                    fetcher=lambda url: rows,
                )
            )
            written = list(publisher.iter_links(output))

        self.assertEqual(len(written), 2)
        self.assertFalse(report["ping_enabled"])
        self.assertEqual(report["output_keys"], 2)

    def test_network_filter_matches_literal_ip_and_supported_protocols(self):
        matcher = network_filter.AddressMatcher.from_networks(
            [
                network_filter.ip_network("10.20.30.0/24"),
                network_filter.ip_network("2001:db8::/32"),
            ]
        )
        rows = [
            "vless://id@10.20.30.40:443#match-v4",
            "hysteria2://secret@[2001:db8::7]:443/#match-v6",
            "hy2://secret@10.20.31.1:443/#outside",
            "vless://id@example.com:443#domain",
            "trojan://secret@10.20.30.50:443#old-protocol",
        ]

        matched, stats = network_filter.filter_keys_by_network(rows, matcher)

        self.assertEqual(matched, rows[:2])
        self.assertEqual(stats.matched, 2)
        self.assertEqual(stats.outside_networks, 1)
        self.assertEqual(stats.domain_or_invalid, 1)
        self.assertEqual(stats.unsupported_protocol, 1)

    def test_published_subscriptions_are_downloaded_and_prepended(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            keys_dir = root / "keys"
            local_git = root / "git"
            keys_dir.mkdir()
            local_git.mkdir()
            (keys_dir / "vless.txt").write_text(
                "vless://new-main@example.net:443#new\n",
                encoding="utf-8",
            )
            (keys_dir / "vless_RU.txt").write_text(
                "vless://new-white@example.net:443#new\n",
                encoding="utf-8",
            )

            payloads = {
                "main": "vless://old-main@example.com:443#old\n",
                "WhiteKeys": "vless://old-white@example.com:443#old\n",
                "WhiteKeys2": (
                    "hysteria2://secret@old-white2.example.com:443/#old\n"
                ),
            }
            downloaded = []

            def fake_fetch(url, timeout):
                name = url.rsplit("/", 1)[-1]
                downloaded.append(name)
                return payloads[name]

            result = published_merge.refresh_published_subscriptions(
                remote_base="https://subscriptions.example",
                keys_dir=keys_dir,
                local_git_dir=local_git,
                timeout=1,
                fetcher=fake_fetch,
            )
            main_rows = (keys_dir / "vless.txt").read_text(
                encoding="utf-8"
            ).splitlines()
            ru_rows = (keys_dir / "vless_RU.txt").read_text(
                encoding="utf-8"
            ).splitlines()

        self.assertEqual(downloaded, ["main", "WhiteKeys", "WhiteKeys2"])
        self.assertEqual(result["previous_main"], 1)
        self.assertEqual(result["previous_white"], 1)
        self.assertEqual(result["previous_white2"], 1)
        self.assertTrue(main_rows[0].startswith("vless://old-main@"))
        self.assertTrue(ru_rows[0].startswith("vless://old-white@"))
        self.assertTrue(ru_rows[1].startswith("hysteria2://"))

    def test_local_name_migration_unions_days_without_losing_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            git_dir = Path(temp_dir)
            publisher.write_target(
                git_dir / "1Mond",
                [
                    "vless://one@example.com:443#one",
                    "vless://duplicate@example.com:443#first",
                ],
            )
            publisher.write_target(
                git_dir / "2Tues",
                [
                    "vless://duplicate@example.com:443#second",
                    "vless://two@example.com:443#two",
                ],
            )
            publisher.write_target(
                git_dir / "RU_other",
                [
                    "vless://duplicate@example.com:443#also-white2",
                    "hysteria2://secret@example.com:443/#RU",
                ],
            )
            publisher.write_target(
                git_dir / "WhiteKeys",
                [
                    "vless://duplicate@example.com:443#white",
                    "vless://duplicate@example.com:443#duplicate-description",
                    "trojan://old@example.com:443#unsupported",
                ],
            )

            result = published_merge.migrate_local_subscription_names(git_dir)
            main_rows = list(publisher.iter_links(git_dir / "main"))
            white2_rows = list(publisher.iter_links(git_dir / "WhiteKeys2"))

        self.assertEqual(len(main_rows), 2)
        self.assertEqual(len(white2_rows), 1)
        self.assertIn("main", result["created"])
        self.assertIn("WhiteKeys2", result["created"])
        self.assertIn("WhiteKeys", result["normalized"])
        self.assertIn("WhiteKeys2", result["normalized"])
        self.assertFalse((git_dir / "1Mond").exists())
        self.assertFalse((git_dir / "2Tues").exists())
        self.assertFalse((git_dir / "RU_other").exists())

    def test_published_subscription_migration_uses_day_and_ru_other(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            keys_dir = root / "keys"
            local_git = root / "git"
            keys_dir.mkdir()
            local_git.mkdir()
            (keys_dir / "vless.txt").write_text("", encoding="utf-8")
            (keys_dir / "vless_RU.txt").write_text("", encoding="utf-8")

            payloads = {
                "1Mond": "vless://legacy-main@example.com:443#old\n",
                "WhiteKeys": "vless://white@example.com:443#old\n",
                "RU_other": "vless://legacy-white2@example.com:443#old\n",
            }

            def fake_fetch(url, timeout):
                name = url.rsplit("/", 1)[-1]
                if name in payloads:
                    return payloads[name]
                raise RuntimeError("not found")

            result = published_merge.refresh_published_subscriptions(
                remote_base="https://subscriptions.example",
                keys_dir=keys_dir,
                local_git_dir=local_git,
                timeout=1,
                fetcher=fake_fetch,
            )

        self.assertEqual(result["previous_main"], 1)
        self.assertEqual(result["previous_white"], 1)
        self.assertEqual(result["previous_white2"], 1)

    def test_hysteria2_uri_builds_xray_outbound(self):
        cert_pin = "ab" * 32
        outbound = checker.parse_hysteria2(
            "hysteria2://user%3Apass@example.com:443,5000-5002/"
            f"?sni=cdn.example.com&alpn=h3&obfs=salamander&obfs-password=mask"
            f"&pinSHA256={cert_pin}&hop-interval=20#RU"
        )

        self.assertEqual(outbound["protocol"], "hysteria")
        self.assertEqual(outbound["settings"]["version"], 2)
        self.assertEqual(outbound["settings"]["port"], 443)
        stream = outbound["streamSettings"]
        self.assertEqual(stream["hysteriaSettings"]["auth"], "user:pass")
        self.assertEqual(stream["tlsSettings"]["serverName"], "cdn.example.com")
        self.assertEqual(stream["tlsSettings"]["pinnedPeerCertSha256"], cert_pin)
        self.assertEqual(
            stream["finalmask"]["quicParams"]["udpHop"]["ports"],
            "443,5000-5002",
        )
        self.assertEqual(
            stream["finalmask"]["udp"][0]["settings"]["password"],
            "mask",
        )

    def test_hy2_gecko_and_default_port(self):
        outbound = checker.parse_hysteria2(
            "hy2://secret@example.com/?obfs=gecko&obfs-password=mask&insecure=1"
        )
        self.assertEqual(outbound["settings"]["port"], 443)
        settings = outbound["streamSettings"]["finalmask"]["udp"][0]["settings"]
        self.assertEqual(settings["packetSize"], "512-1200")
        self.assertNotIn("allowInsecure", outbound["streamSettings"]["tlsSettings"])

    def test_base64_subscription_and_description_duplicates(self):
        raw = "\n".join(
            [
                "vless://id@example.com:443?security=tls#US",
                "vless://id@example.com:443?security=tls#DE",
                "hysteria2://secret@example.org:443/?sni=example.org#RU",
            ]
        )
        encoded = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
        keys = shared.extract_key_lines(encoded)
        self.assertEqual(len(keys), 2)

    def test_extraction_routes_keys_by_ru_marker_and_ignores_trojan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            top15 = root / "whiteList_top15.txt"
            top15.write_text("https://source.example/sub\n", encoding="utf-8")
            output = root / "keys"

            with patch.object(
                shared,
                "fetch_lines",
                return_value=[
                    "hysteria2://secret@example.com:443/?sni=example.com#DE",
                    "vless://id@example.net:443?security=tls#RUSSIA",
                    "trojan://secret@example.net:443#ignored",
                ],
            ):
                result = shared.extract_keys_from_top15(
                    top15,
                    output,
                    include_ss=False,
                )

            ordinary_rows = (output / "vless.txt").read_text(encoding="utf-8").splitlines()
            ru_rows = (output / "vless_RU.txt").read_text(encoding="utf-8").splitlines()

        self.assertEqual(result["vless_ru"], 1)
        self.assertEqual(result["vless_total"], 1)
        self.assertTrue(ordinary_rows[0].startswith("hysteria2://"))
        self.assertTrue(ru_rows[0].startswith("vless://"))

    def test_publisher_deduplicates_by_connection_uri(self):
        rows = [
            "vless://id@example.com:443#one",
            "vless://id@example.com:443#two",
            "hy2://secret@example.org:443/?sni=example.org#three",
        ]
        unique = publisher.dedupe_keep_order(rows)
        self.assertEqual(len(unique), 2)
        self.assertEqual(
            publisher.connection_id(rows[0]),
            publisher.connection_id(rows[1]),
        )

    def test_publisher_preserves_live_old_keys_and_removes_legacy_targets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            primary = root / "top"
            live = root / "live"
            legacy = root / "legacy"
            git_dir = root / "git"
            for directory in (primary, live, legacy, git_dir):
                directory.mkdir()

            (primary / "vless_ping_ok.txt").write_text(
                "vless://new-main@example.com:443#US\n",
                encoding="utf-8",
            )
            (primary / "vless_RU_ping_ok.txt").write_text(
                "vless://new-white@example.com:443#top\n",
                encoding="utf-8",
            )
            (live / "vless_ping_ok.txt").write_text(
                "\n".join(
                    [
                        "vless://new-main@example.com:443#new",
                        "vless://old-main@example.com:443#still-alive",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (live / "vless_RU_ping_ok.txt").write_text(
                "\n".join(
                    [
                        "vless://new-white@example.com:443#different-description",
                        "vless://old-white@example.com:443#still-alive",
                        "vless://white2@example.com:443#RU",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (legacy / "published_main.txt").write_text(
                "vless://old-main@example.com:443#published\n",
                encoding="utf-8",
            )
            (legacy / "published_WhiteKeys.txt").write_text(
                "vless://old-white@example.com:443#published\n",
                encoding="utf-8",
            )
            for legacy_name in ("1Mond", "RU_other"):
                (git_dir / legacy_name).write_text(
                    "legacy\n",
                    encoding="utf-8",
                )

            with (
                patch.object(publisher, "PRIMARY_SOURCE_DIR", primary),
                patch.object(publisher, "FALLBACK_SOURCE_DIR", live),
                patch.object(publisher, "LEGACY_SOURCE_DIR", legacy),
                patch.object(publisher, "GIT_DIR", git_dir),
            ):
                result = publisher.main()
                main_rows = list(publisher.iter_links(git_dir / "main"))
                white = list(publisher.iter_links(git_dir / "WhiteKeys"))
                white2 = list(publisher.iter_links(git_dir / "WhiteKeys2"))

        self.assertEqual(result, 0)
        self.assertEqual(len(main_rows), 2)
        self.assertEqual(len(white), 2)
        self.assertEqual(len(white2), 1)
        self.assertFalse((git_dir / "1Mond").exists())
        self.assertFalse((git_dir / "RU_other").exists())
        self.assertTrue(
            {publisher.connection_id(row) for row in white}.isdisjoint(
                publisher.connection_id(row) for row in white2
            )
        )

    def test_rerank_reuses_one_safe_worker_port(self):
        used_ports = []

        async def fake_probe(key, xray_bin, socks_port, timeout):
            used_ports.append(socks_port)
            return 25.0

        with patch.object(rerank, "probe_once", fake_probe):
            result = asyncio.run(
                rerank.measure_key(
                    "vless://id@example.com:443",
                    runs=3,
                    xray_bin=Path("xray"),
                    timeout=1.0,
                    socks_port=65_000,
                )
            )

        self.assertEqual(result["success_runs"], 3)
        self.assertEqual(used_ports, [65_000, 65_000, 65_000])

    def test_alive_limit_does_not_drop_priority_published_keys(self):
        async def fake_check(key, kind, xray_bin, socks_port, timeout):
            return True

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "alive.txt"
            with patch.object(checker, "check_one", fake_check):
                alive = asyncio.run(
                    checker.run_checks(
                        [
                            "vless://old-one@example.com:443",
                            "vless://old-two@example.com:443",
                            "vless://new@example.com:443",
                        ],
                        "test",
                        Path("xray"),
                        1,
                        1.0,
                        20_000,
                        output,
                        max_alive=1,
                        priority_count=2,
                    )
                )

        self.assertEqual(len(alive), 2)
        self.assertTrue(all("old-" in key for key in alive))


if __name__ == "__main__":
    unittest.main()
