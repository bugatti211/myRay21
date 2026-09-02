"""Filter VLESS and Hysteria 2 links by literal IP networks.

This module intentionally does not perform DNS lookups: a domain name cannot be
matched reliably against a static list of IP ranges.
"""

from bisect import bisect_right
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple, Union
from urllib.parse import urlsplit


SUPPORTED_SCHEMES = frozenset(("vless", "hysteria2", "hy2"))

IpAddress = Union[IPv4Address, IPv6Address]
Interval = Tuple[int, int]


@dataclass(frozen=True)
class AddressMatcher:
    """Fast IP membership check over merged IPv4 and IPv6 intervals."""

    ipv4_starts: Tuple[int, ...]
    ipv4_ends: Tuple[int, ...]
    ipv6_starts: Tuple[int, ...]
    ipv6_ends: Tuple[int, ...]

    @staticmethod
    def _merge(intervals: Iterable[Interval]) -> Tuple[Tuple[int, ...], Tuple[int, ...]]:
        merged: List[List[int]] = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        return (
            tuple(interval[0] for interval in merged),
            tuple(interval[1] for interval in merged),
        )

    @classmethod
    def from_networks(cls, networks: Iterable[object]) -> "AddressMatcher":
        ipv4: List[Interval] = []
        ipv6: List[Interval] = []
        for network in networks:
            interval = (int(network.network_address), int(network.broadcast_address))
            (ipv4 if network.version == 4 else ipv6).append(interval)
        ipv4_starts, ipv4_ends = cls._merge(ipv4)
        ipv6_starts, ipv6_ends = cls._merge(ipv6)
        return cls(ipv4_starts, ipv4_ends, ipv6_starts, ipv6_ends)

    def contains(self, address: IpAddress) -> bool:
        if address.version == 4:
            starts, ends = self.ipv4_starts, self.ipv4_ends
        else:
            starts, ends = self.ipv6_starts, self.ipv6_ends
        index = bisect_right(starts, int(address)) - 1
        return index >= 0 and int(address) <= ends[index]

    @property
    def interval_count(self) -> int:
        return len(self.ipv4_starts) + len(self.ipv6_starts)


@dataclass
class FilterStats:
    total: int = 0
    matched: int = 0
    outside_networks: int = 0
    domain_or_invalid: int = 0
    unsupported_protocol: int = 0


def load_network_matcher(path: Path) -> AddressMatcher:
    networks = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8", errors="strict").splitlines(),
        start=1,
    ):
        value = raw_line.split("#", 1)[0].strip()
        if not value:
            continue
        try:
            networks.append(ip_network(value, strict=False))
        except ValueError as exc:
            raise ValueError(f"{path}:{line_number}: invalid IP network {value!r}") from exc
    if not networks:
        raise ValueError(f"no IP networks found in {path}")
    return AddressMatcher.from_networks(networks)


def extract_server_ip(uri: str) -> Tuple[Union[IpAddress, None], str]:
    scheme = uri.partition("://")[0].lower()
    if scheme not in SUPPORTED_SCHEMES:
        return None, "unsupported_protocol"
    try:
        host = urlsplit(uri).hostname
        return ip_address(host), "literal_ip"
    except (TypeError, ValueError):
        return None, "domain_or_invalid"


def filter_keys_by_network(
    rows: Sequence[str],
    matcher: AddressMatcher,
) -> Tuple[List[str], FilterStats]:
    matched_rows: List[str] = []
    stats = FilterStats()
    for row in rows:
        stats.total += 1
        address, result = extract_server_ip(row)
        if result == "unsupported_protocol":
            stats.unsupported_protocol += 1
            continue
        if address is None:
            stats.domain_or_invalid += 1
            continue
        if matcher.contains(address):
            stats.matched += 1
            matched_rows.append(row)
        else:
            stats.outside_networks += 1
    return matched_rows, stats
