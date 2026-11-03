import unittest

from ui_helpers import calculate_window_profile, format_elapsed_time


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


class ResponsiveWindowProfileTests(unittest.TestCase):
    def test_2k_or_4k_screen_keeps_readable_window_under_740_by_900(self):
        self.assertEqual(calculate_window_profile(2560, 1400), (740, 900, False))
        self.assertEqual(calculate_window_profile(3840, 2100), (740, 900, False))

    def test_1366_by_768_laptop_uses_available_height_and_compact_mode(self):
        self.assertEqual(calculate_window_profile(1366, 728), (740, 708, True))

    def test_narrow_screen_keeps_window_inside_available_width(self):
        self.assertEqual(calculate_window_profile(800, 900), (740, 880, False))
        self.assertEqual(calculate_window_profile(640, 700), (616, 680, True))

    def test_window_never_exceeds_maximum_size(self):
        width, height, _ = calculate_window_profile(7680, 4320)
        self.assertLessEqual(width, 740)
        self.assertLessEqual(height, 900)


if __name__ == "__main__":
    unittest.main()
