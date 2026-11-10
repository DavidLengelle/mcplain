"""The only reader of the visitor address: it trusts only the address written by our own relays"""

import ipaddress
from collections.abc import Iterable

FORWARDED_FOR = "x-forwarded-for"
IPV6_PREFIX = 64
MAX_ENTRIES = 32
ZONE_SEPARATOR = "%"


def forwarded_entries(values: Iterable[str]) -> list[str]:
    """Return every address of the X-Forwarded-For headers, in order, the oldest on the left"""

    entries: list[str] = []
    for value in values:
        for part in value.split(","):
            item = part.strip()
            if item:
                entries.append(item)
    return entries


def normalize_ip(text: str | None) -> str | None:
    """Return an IPv4 address, or the /64 network of an IPv6 address, or None for anything else"""

    if text is None:
        return None
    candidate = text.strip().strip("[]").split(ZONE_SEPARATOR)[0]
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.IPv6Network((address, IPV6_PREFIX), strict=False))
    return str(address)


def visitor_ip(forwarded_for: Iterable[str], peer: str | None, hops: int) -> str | None:
    """Return the visitor address: the entry our first relay appended, counted from the right; with 0 hops, the peer"""

    if hops == 0:
        return normalize_ip(peer)
    entries = forwarded_entries(forwarded_for)
    if len(entries) < hops or len(entries) > MAX_ENTRIES:
        return None
    return normalize_ip(entries[len(entries) - hops])
