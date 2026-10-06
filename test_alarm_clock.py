"""Focused checks for alarm scheduling and command parsing."""

import unittest
from datetime import datetime, timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

from alarm_clock import (
    AlarmClock,
    _load_alarms,
    _persist_alarms,
    _apply_keyboard_action,
    handle_command,
    next_occurrence,
    parse_days,
    render_screen,
)


class AlarmClockTests(unittest.TestCase):
    def test_one_shot_time_already_passed_rolls_to_tomorrow(self):
        now = datetime(2026, 10, 6, 10, 0, 30)
        self.assertEqual(next_occurrence(9, 30, None, now), datetime(2026, 10, 7, 9, 30))

    def test_repeating_alarm_uses_next_selected_weekday(self):
        now = datetime(2026, 10, 6, 10, 0)  # Tuesday
        weekdays = parse_days("mon,wed,fri")
        self.assertEqual(next_occurrence(9, 0, weekdays, now), datetime(2026, 10, 7, 9, 0))

    def test_alarm_rings_once_and_is_removed(self):
        clock = AlarmClock()
        now = datetime(2026, 10, 6, 8, 0)
        alarm = clock.add(8, 1, None, now)
        self.assertIsNone(clock.tick(alarm.next_fire - timedelta(seconds=1)))
        self.assertEqual(clock.tick(alarm.next_fire), alarm)
        self.assertNotIn(alarm.alarm_id, clock.alarms)

    def test_weekly_alarm_advances_after_ringing(self):
        clock = AlarmClock()
        now = datetime(2026, 10, 6, 8, 0)
        alarm = clock.add(8, 1, frozenset({1, 3}), now)
        self.assertEqual(clock.tick(alarm.next_fire), alarm)
        clock.stop()
        self.assertEqual(alarm.next_fire, datetime(2026, 10, 8, 8, 1))

    def test_snooze_rings_again_after_five_minutes(self):
        clock = AlarmClock()
        now = datetime(2026, 10, 6, 8, 0)
        alarm = clock.add(8, 1, None, now)
        self.assertEqual(clock.tick(alarm.next_fire), alarm)
        self.assertTrue(clock.snooze(alarm.next_fire))
        self.assertIsNone(clock.tick(alarm.next_fire + timedelta(minutes=5) - timedelta(seconds=1)))
        self.assertEqual(clock.tick(alarm.next_fire + timedelta(minutes=5)), alarm)

    def test_keyboard_stop_dismisses_active_alarm(self):
        clock = AlarmClock()
        now = datetime(2026, 10, 6, 8, 0)
        alarm = clock.add(8, 1, None, now)
        clock.tick(alarm.next_fire)
        self.assertEqual(_apply_keyboard_action(clock, "stop", alarm.next_fire), "Alarm stopped.")
        self.assertIsNone(clock.active)

    def test_keyboard_snooze_uses_five_minute_delay(self):
        clock = AlarmClock()
        now = datetime(2026, 10, 6, 8, 0)
        alarm = clock.add(8, 1, None, now)
        clock.tick(alarm.next_fire)
        self.assertEqual(_apply_keyboard_action(clock, "snooze", alarm.next_fire), "Snoozed for 5 minutes.")
        self.assertEqual(clock.tick(alarm.next_fire + timedelta(minutes=5)), alarm)

    def test_invalid_time_is_rejected_cleanly(self):
        clock = AlarmClock()
        message = handle_command("add 25:90", clock, datetime(2026, 10, 6, 8, 0))
        self.assertIn("valid 24-hour time", message)
        self.assertFalse(clock.alarms)

    def test_plain_digital_time_appears_before_date(self):
        now = datetime(2026, 10, 6, 8, 5, 9)
        lines = render_screen(now, AlarmClock(), "Ready")
        time_line = next(index for index, line in enumerate(lines) if "08:05:09" in line)
        date_line = next(index for index, line in enumerate(lines) if "Tuesday, October 06, 2026" in line)
        self.assertLess(time_line, date_line)

    def test_alarm_schedule_persists_as_json(self):
        with TemporaryDirectory() as folder, patch.dict("os.environ", {"ALARM_CLOCK_HOME": folder}):
            original = AlarmClock()
            original.add(7, 30, frozenset({0, 2, 4}), datetime(2026, 10, 6, 8, 0))
            _persist_alarms(original)
            restored = AlarmClock()
            _load_alarms(restored)
            alarm = restored.alarms[1]
            self.assertEqual((alarm.hour, alarm.minute), (7, 30))
            self.assertEqual(alarm.weekdays, frozenset({0, 2, 4}))
            self.assertEqual(alarm.next_fire, original.alarms[1].next_fire)


if __name__ == "__main__":
    unittest.main()
