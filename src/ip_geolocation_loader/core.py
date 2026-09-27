"""Load and index IPv4-to-country CSV data for fast range lookup.

The loader parses a CSV of (start_ip, end_ip, country_code) rows, converts
the dotted-quad addresses to 32-bit integers, sorts by start address, and
exposes a binary-search lookup. Only IPv4 is supported; the brief is small
and IPv6 would roughly double the code for a feature the tests do not need.
"""

from __future__ import annotations

import csv
import io
import os
from typing import Iterator, List, Optional, Tuple


def ip_to_int(ip: str) -> int:
    """Convert a dotted-quad IPv4 string to a 32-bit unsigned integer.

    Raises ValueError on malformed input. We reject empty fields, extra
    octets, and out-of-range octets so that callers cannot silently get a
    wrong integer from garbage input.
    """
    if not isinstance(ip, str):
        raise ValueError("ip must be a string")
    parts = ip.split(".")
    if len(parts) != 4:
        raise ValueError("invalid IPv4 address: %r" % (ip,))
    value = 0
    for part in parts:
        if not part or not part.isdigit():
            raise ValueError("invalid IPv4 address: %r" % (ip,))
        # Disallow leading zeros like '01' — they are legal per some parsers
        # but ambiguous (octal in legacy systems) and we want one rule.
        if len(part) > 1 and part[0] == "0":
            raise ValueError("invalid IPv4 address: %r" % (ip,))
        octet = int(part)
        if octet < 0 or octet > 255:
            raise ValueError("invalid IPv4 address: %r" % (ip,))
        value = (value << 8) | octet
    return value


def int_to_ip(value: int) -> str:
    """Inverse of ip_to_int."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("value must be an int")
    if value < 0 or value > 0xFFFFFFFF:
        raise ValueError("value out of range: %d" % (value,))
    return "%d.%d.%d.%d" % (
        (value >> 24) & 0xFF,
        (value >> 16) & 0xFF,
        (value >> 8) & 0xFF,
        value & 0xFF,
    )


class IPGeolocationLoader:
    """In-memory index of IPv4 ranges keyed by start address.

    The CSV is expected to have at least three columns per row:
    start_ip, end_ip, country_code. A header row is detected and skipped if
    its first cell does not parse as an IPv4 address. This keeps the loader
    tolerant of the two common CSV conventions without needing a schema
    argument.

    Ranges may overlap; lookup returns the first range whose [start, end]
    interval contains the query, in sorted-by-start order. Overlapping ranges
    are unusual in real geolocation feeds but the behaviour is defined so the
    caller gets a deterministic answer.
    """

    def __init__(self) -> None:
        # Each entry: (start_int, end_int, country_code). Sorted by start_int.
        self._ranges: List[Tuple[int, int, str]] = []

    @property
    def ranges(self) -> List[Tuple[int, int, str]]:
        """Return a shallow copy of the internal range list.

        Copying avoids callers mutating the index through the returned list.
        The tuples themselves are immutable so a shallow copy is enough.
        """
        return list(self._ranges)

    def load_file(self, path: str) -> None:
        """Load ranges from a CSV file on disk."""
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        with open(path, "r", encoding="utf-8", newline="") as fh:
            self.load_stream(fh)

    def load_string(self, text: str) -> None:
        """Load ranges from a CSV string. Useful for tests and embedded data."""
        self.load_stream(io.StringIO(text))

    def load_stream(self, stream) -> None:
        """Load ranges from an iterable of CSV lines (file or StringIO)."""
        reader = csv.reader(stream)
        new_ranges: List[Tuple[int, int, str]] = []
        for row in reader:
            if not row:
                continue
            # Skip blank-ish rows that csv may emit as [''].
            if len(row) == 1 and row[0].strip() == "":
                continue
            if len(row) < 3:
                raise ValueError("row must have at least 3 columns: %r" % (row,))
            start_raw = row[0].strip()
            end_raw = row[1].strip()
            country = row[2].strip()
            # Header detection: if the first cell is not a valid IP, treat the
            # whole row as a header and skip it. This handles 'start_ip,...'
            # without a schema flag.
            try:
                start = ip_to_int(start_raw)
            except ValueError:
                continue
            end = ip_to_int(end_raw)
            if end < start:
                raise ValueError(
                    "end_ip %s before start_ip %s" % (end_raw, start_raw)
                )
            if not country:
                raise ValueError("empty country code in row: %r" % (row,))
            new_ranges.append((start, end, country))
        new_ranges.sort(key=lambda r: r[0])
        self._ranges = new_ranges

    def lookup(self, ip: str) -> Optional[str]:
        """Return the country code for an IPv4 string, or None if no range contains it."""
        return self.lookup_int(ip_to_int(ip))

    def lookup_int(self, value: int) -> Optional[str]:
        """Lookup by integer address. Returns None if not found."""
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("value must be an int")
        if value < 0 or value > 0xFFFFFFFF:
            raise ValueError("value out of range: %d" % (value,))
        ranges = self._ranges
        if not ranges:
            return None
        # Binary search for the rightmost range whose start <= value.
        lo = 0
        hi = len(ranges) - 1
        best = -1
        while lo <= hi:
            mid = (lo + hi) // 2
            start = ranges[mid][0]
            if start <= value:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        if best < 0:
            return None
        start, end, country = ranges[best]
        if value <= end:
            return country
        return None

    def __len__(self) -> int:
        return len(self._ranges)

    def __iter__(self) -> Iterator[Tuple[int, int, str]]:
        return iter(self._ranges)
