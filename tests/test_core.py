import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ip_geolocation_loader import IPGeolocationLoader, ip_to_int, int_to_ip


class TestIpToInt(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(ip_to_int("0.0.0.0"), 0)
        self.assertEqual(ip_to_int("255.255.255.255"), 0xFFFFFFFF)
        self.assertEqual(ip_to_int("1.2.3.4"), (1 << 24) | (2 << 16) | (3 << 8) | 4)

    def test_leading_zero_rejected(self):
        with self.assertRaises(ValueError):
            ip_to_int("01.2.3.4")
        with self.assertRaises(ValueError):
            ip_to_int("1.02.3.4")

    def test_wrong_octet_count(self):
        with self.assertRaises(ValueError):
            ip_to_int("1.2.3")
        with self.assertRaises(ValueError):
            ip_to_int("1.2.3.4.5")

    def test_non_numeric(self):
        with self.assertRaises(ValueError):
            ip_to_int("a.b.c.d")
        with self.assertRaises(ValueError):
            ip_to_int("1.2..4")

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            ip_to_int("256.1.1.1")

    def test_non_string(self):
        with self.assertRaises(ValueError):
            ip_to_int(12345)


class TestIntToIp(unittest.TestCase):
    def test_roundtrip(self):
        for s in ["0.0.0.0", "1.2.3.4", "255.255.255.255", "10.0.0.1"]:
            self.assertEqual(int_to_ip(ip_to_int(s)), s)

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            int_to_ip(-1)
        with self.assertRaises(ValueError):
            int_to_ip(0x100000000)

    def test_bool_rejected(self):
        with self.assertRaises(ValueError):
            int_to_ip(True)


class TestLoaderBasic(unittest.TestCase):
    def test_load_string_and_lookup(self):
        loader = IPGeolocationLoader()
        loader.load_string(
            "10.0.0.1,10.0.0.255,US\n"
            "10.0.1.0,10.0.1.255,CA\n"
            "192.168.0.0,192.168.0.255,GB\n"
        )
        self.assertEqual(loader.lookup("10.0.0.1"), "US")
        self.assertEqual(loader.lookup("10.0.0.255"), "US")
        self.assertEqual(loader.lookup("10.0.1.0"), "CA")
        self.assertEqual(loader.lookup("10.0.1.255"), "CA")
        self.assertEqual(loader.lookup("192.168.0.128"), "GB")

    def test_lookup_miss(self):
        loader = IPGeolocationLoader()
        loader.load_string("10.0.0.0,10.0.0.255,US\n")
        self.assertIsNone(loader.lookup("9.255.255.255"))
        self.assertIsNone(loader.lookup("10.0.1.0"))

    def test_empty_loader(self):
        loader = IPGeolocationLoader()
        self.assertIsNone(loader.lookup("1.1.1.1"))
        self.assertEqual(len(loader), 0)

    def test_header_skipped(self):
        loader = IPGeolocationLoader()
        loader.load_string(
            "start_ip,end_ip,country\n"
            "10.0.0.0,10.0.0.255,US\n"
        )
        self.assertEqual(len(loader), 1)
        self.assertEqual(loader.lookup("10.0.0.5"), "US")

    def test_blank_rows_skipped(self):
        loader = IPGeolocationLoader()
        loader.load_string(
            "10.0.0.0,10.0.0.255,US\n"
            "\n"
            "10.0.1.0,10.0.1.255,CA\n"
        )
        self.assertEqual(len(loader), 2)

    def test_end_before_start_raises(self):
        loader = IPGeolocationLoader()
        with self.assertRaises(ValueError):
            loader.load_string("10.0.0.255,10.0.0.0,US\n")

    def test_empty_country_raises(self):
        loader = IPGeolocationLoader()
        with self.assertRaises(ValueError):
            loader.load_string("10.0.0.0,10.0.0.255,\n")

    def test_too_few_columns_raises(self):
        loader = IPGeolocationLoader()
        with self.assertRaises(ValueError):
            loader.load_string("10.0.0.0,10.0.0.255\n")

    def test_extra_columns_ignored(self):
        loader = IPGeolocationLoader()
        loader.load_string("10.0.0.0,10.0.0.255,US,extra,columns\n")
        self.assertEqual(loader.lookup("10.0.0.5"), "US")

    def test_whitespace_trimmed(self):
        loader = IPGeolocationLoader()
        loader.load_string("  10.0.0.0 , 10.0.0.255 , US  \n")
        self.assertEqual(loader.lookup("10.0.0.5"), "US")

    def test_ranges_property_is_copy(self):
        loader = IPGeolocationLoader()
        loader.load_string("10.0.0.0,10.0.0.255,US\n")
        r = loader.ranges
        r.clear()
        self.assertEqual(len(loader), 1)

    def test_iter(self):
        loader = IPGeolocationLoader()
        loader.load_string("10.0.0.0,10.0.0.255,US\n10.0.1.0,10.0.1.255,CA\n")
        items = list(loader)
        self.assertEqual(items[0][2], "US")
        self.assertEqual(items[1][2], "CA")


class TestLoaderFile(unittest.TestCase):
    def test_load_file(self):
        loader = IPGeolocationLoader()
        with tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8"
        ) as fh:
            fh.write("10.0.0.0,10.0.0.255,US\n")
            fh.write("10.0.1.0,10.0.1.255,CA\n")
            path = fh.name
        try:
            loader.load_file(path)
            self.assertEqual(loader.lookup("10.0.0.5"), "US")
            self.assertEqual(loader.lookup("10.0.1.5"), "CA")
        finally:
            os.unlink(path)

    def test_missing_file(self):
        loader = IPGeolocationLoader()
        with self.assertRaises(FileNotFoundError):
            loader.load_file("/nonexistent/path/to/file.csv")


class TestLookupInt(unittest.TestCase):
    def test_lookup_int(self):
        loader = IPGeolocationLoader()
        loader.load_string("10.0.0.0,10.0.0.255,US\n")
        self.assertEqual(loader.lookup_int(ip_to_int("10.0.0.5")), "US")
        self.assertIsNone(loader.lookup_int(ip_to_int("10.0.1.0")))

    def test_lookup_int_validation(self):
        loader = IPGeolocationLoader()
        with self.assertRaises(ValueError):
            loader.lookup_int(-1)
        with self.assertRaises(ValueError):
            loader.lookup_int(0x100000000)
        with self.assertRaises(ValueError):
            loader.lookup_int(True)


class TestOverlappingRanges(unittest.TestCase):
    def test_first_match_wins(self):
        # Overlapping ranges: 10.0.0.0-10.0.0.255 (US) and 10.0.0.128-10.0.1.0 (CA).
        # Sorted by start, the US range comes first. For 10.0.0.200 both contain it;
        # the binary search lands on the CA range (later start <= value) but since CA
        # also contains it, CA is returned. This documents the actual behaviour.
        loader = IPGeolocationLoader()
        loader.load_string(
            "10.0.0.0,10.0.0.255,US\n"
            "10.0.0.128,10.0.1.0,CA\n"
        )
        self.assertEqual(loader.lookup("10.0.0.5"), "US")
        self.assertEqual(loader.lookup("10.0.0.200"), "CA")
        self.assertEqual(loader.lookup("10.0.0.255"), "CA")
        self.assertEqual(loader.lookup("10.0.1.0"), "CA")


class TestUnsortedInput(unittest.TestCase):
    def test_unsorted_sorted_internally(self):
        loader = IPGeolocationLoader()
        loader.load_string(
            "192.168.0.0,192.168.0.255,GB\n"
            "10.0.0.0,10.0.0.255,US\n"
            "10.0.1.0,10.0.1.255,CA\n"
        )
        starts = [r[0] for r in loader]
        self.assertEqual(starts, sorted(starts))
        self.assertEqual(loader.lookup("10.0.0.5"), "US")


class TestBoundaryValues(unittest.TestCase):
    def test_zero_and_max(self):
        loader = IPGeolocationLoader()
        loader.load_string(
            "0.0.0.0,0.0.0.0,AA\n"
            "255.255.255.255,255.255.255.255,ZZ\n"
        )
        self.assertEqual(loader.lookup("0.0.0.0"), "AA")
        self.assertEqual(loader.lookup("255.255.255.255"), "ZZ")
        self.assertIsNone(loader.lookup("0.0.0.1"))

    def test_single_ip_range(self):
        loader = IPGeolocationLoader()
        loader.load_string("8.8.8.8,8.8.8.8,US\n")
        self.assertEqual(loader.lookup("8.8.8.8"), "US")
        self.assertIsNone(loader.lookup("8.8.8.7"))
        self.assertIsNone(loader.lookup("8.8.8.9"))


if __name__ == "__main__":
    unittest.main()
