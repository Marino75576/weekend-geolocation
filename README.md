# IP Geolocation Loader

Loads IPv4-to-country CSV data into memory and answers `lookup(ip)` in
O(log n) via binary search on integer-encoded start addresses.

```python
from ip_geolocation_loader import IPGeolocationLoader

loader = IPGeolocationLoader()
loader.load_string("10.0.0.0,10.0.0.255,US\n10.0.1.0,10.0.1.255,CA\n")
print(loader.lookup("10.0.0.5"))  # "US"
print(loader.lookup("10.0.1.5"))  # "CA"
print(loader.lookup("8.8.8.8"))   # None
```

Also exported: `ip_to_int("1.2.3.4") -> int` and `int_to_ip(n) -> str`.

## Why

Geolocation feeds ship as large CSVs of `(start_ip, end_ip, country)`. A
linear scan per query is too slow at millions of rows; a database is
overkill when the dataset fits in RAM. This library converts addresses to
32-bit integers, sorts once, and binary-searches. The trade-off is memory:
the whole index lives in a Python list of tuples. For a few hundred thousand
ranges that is a few megabytes; for tens of millions you want a database.

## Edge cases you will hit

- **IPv4 only.** `ip_to_int("::1")` raises `ValueError`. Adding IPv6 would
  mean 128-bit integers and a separate code path; if you need it, use a
  real database.
- **Leading zeros are rejected.** `"01.2.3.4"` raises `ValueError`. They are
  legal per some parsers but historically octal in others; one rule is better
  than two.
- **Overlapping ranges.** Lookup finds the rightmost range whose start is `<=`
  the query and checks whether its end covers the query. If two ranges overlap
  and both contain the address, the one with the later start wins. Real feeds
  should not overlap; if yours do, de-duplicate before loading.
- **Header rows.** A row whose first cell is not a valid IPv4 address is
treated as a header and skipped. This handles `start_ip,end_ip,country`
  without a schema flag.
- **Empty loader.** `lookup` returns `None`; it does not raise.
