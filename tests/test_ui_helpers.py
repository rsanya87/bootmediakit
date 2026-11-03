import unittest

from ui_helpers import format_elapsed_time


class ElapsedTimeFormattingTests(unittest.TestCase):
    def test_zero_is_displayed_as_zero_minutes_and_seconds(self):
        self.assertEqual(format_elapsed_time(0), "00:00")

    def test_sub_minute_duration(self):
        self.assertEqual(format_elapsed_time(59_000), "00:59")

    def test_minute_boundary(self):
        self.assertEqual(format_elapsed_time(60_000), "01:00")

    def test_duration_over_an_hour_uses_hours_minutes_seconds(self):
        self.assertEqual(format_elapsed_time(3_723_000), "01:02:03")

    def test_negative_duration_is_clamped_to_zero(self):
        self.assertEqual(format_elapsed_time(-10_000), "00:00")

    def test_fractional_second_is_truncated(self):
        self.assertEqual(format_elapsed_time(2_999), "00:02")


if __name__ == "__main__":
    unittest.main()
