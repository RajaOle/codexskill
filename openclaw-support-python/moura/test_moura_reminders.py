#!/usr/bin/env python3
"""Smoke tests for Moura reminder target validation."""

from __future__ import annotations

import unittest
import sqlite3
from datetime import datetime, timezone
from unittest.mock import patch

import moura_reminders


class MouraReminderTargetTest(unittest.TestCase):
    def make_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        moura_reminders.init_db(conn)
        return conn

    def create_test_reminder(self, conn: sqlite3.Connection, target: str = "+6285643497070") -> int:
        result = moura_reminders.create_reminder(
            conn,
            {
                "created_by_phone": "+6285643497070",
                "target": target,
                "due_at": "2099-07-11T10:00:00+07:00",
                "timezone": "Asia/Jakarta",
                "message": "Test reminder",
            },
        )
        return int(result["id"])

    def test_normalizes_direct_phone_target(self) -> None:
        self.assertEqual(moura_reminders.normalize_target("6285643497070"), "+6285643497070")

    def test_allows_configured_group_target(self) -> None:
        group_id = "120363410560838501@g.us"
        with patch("moura_reminders.configured_moura_groups", return_value={group_id}):
            self.assertEqual(moura_reminders.normalize_target(group_id), group_id)

    def test_rejects_unconfigured_group_target(self) -> None:
        with patch("moura_reminders.configured_moura_groups", return_value=set()):
            with self.assertRaisesRegex(ValueError, "not configured"):
                moura_reminders.normalize_target("120363410560838501@g.us")

    def test_daily_recurrence_uses_next_local_time(self) -> None:
        after = datetime(2026, 7, 10, 1, 0, tzinfo=timezone.utc)

        due = moura_reminders.next_daily_due(["09:00", "14:00", "20:00"], "Asia/Jakarta", after)

        self.assertEqual(due.isoformat(), "2026-07-10T02:00:00+00:00")

    def test_daily_recurrence_rolls_to_tomorrow(self) -> None:
        after = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)

        due = moura_reminders.next_daily_due(["09:00", "14:00", "20:00"], "Asia/Jakarta", after)

        self.assertEqual(due.isoformat(), "2026-07-11T02:00:00+00:00")

    def test_daily_random_uses_next_day_part_window(self) -> None:
        after = datetime(2026, 7, 10, 0, 30, tzinfo=timezone.utc)

        with patch("moura_reminders.random.randint", return_value=0):
            due = moura_reminders.next_daily_window_due(
                ["morning", "noon", "afternoon"],
                "Asia/Jakarta",
                after,
            )

        self.assertEqual(due.isoformat(), "2026-07-10T01:00:00+00:00")

    def test_daily_random_moves_inside_active_window(self) -> None:
        after = datetime(2026, 7, 10, 2, 0, tzinfo=timezone.utc)

        with patch("moura_reminders.random.randint", return_value=0):
            due = moura_reminders.next_daily_window_due(
                ["morning", "noon", "afternoon"],
                "Asia/Jakarta",
                after,
            )

        self.assertEqual(due.isoformat(), "2026-07-10T02:01:00+00:00")

    def test_daily_random_reschedule_skips_active_window_after_send(self) -> None:
        after = datetime(2026, 7, 10, 2, 46, tzinfo=timezone.utc)

        with patch("moura_reminders.random.randint", return_value=0):
            due = moura_reminders.next_daily_window_due(
                ["morning", "noon", "afternoon"],
                "Asia/Jakarta",
                after,
                allow_active_window=False,
            )

        self.assertEqual(due.isoformat(), "2026-07-10T05:00:00+00:00")

    def test_cancel_pending_reminders_by_group_target(self) -> None:
        group_id = "120363410560838501@g.us"
        with self.make_conn() as conn, patch("moura_reminders.configured_moura_groups", return_value={group_id}):
            reminder_id = self.create_test_reminder(conn, target=group_id)

            result = moura_reminders.cancel_reminders(
                conn,
                {
                    "created_by_phone": "+6285643497070",
                    "target": group_id,
                    "reason": "Stop remindernya bawel",
                },
            )

            row = conn.execute("SELECT status FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
            self.assertEqual(result["canceled"], 1)
            self.assertEqual(row["status"], "canceled")

    def test_update_pending_reminder_message(self) -> None:
        with self.make_conn() as conn:
            reminder_id = self.create_test_reminder(conn)

            result = moura_reminders.update_reminder(
                conn,
                {
                    "created_by_phone": "+6285643497070",
                    "id": reminder_id,
                    "message": "Updated reminder",
                },
            )

            row = conn.execute("SELECT message, status FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
            self.assertTrue(result["ok"])
            self.assertEqual(row["message"], "Updated reminder")
            self.assertEqual(row["status"], "pending")

    def test_list_reminders_requires_authorized_requester(self) -> None:
        with self.make_conn() as conn:
            self.create_test_reminder(conn)

            with self.assertRaisesRegex(PermissionError, "not an authorized"):
                moura_reminders.list_reminders_for_payload(
                    conn,
                    {
                        "created_by_phone": "+6281111111111",
                        "status": "all",
                    },
                )

    def test_update_rejects_unauthorized_requester(self) -> None:
        with self.make_conn() as conn:
            reminder_id = self.create_test_reminder(conn)

            with self.assertRaisesRegex(PermissionError, "not an authorized"):
                moura_reminders.update_reminder(
                    conn,
                    {
                        "created_by_phone": "+6281111111111",
                        "id": reminder_id,
                        "message": "Nope",
                    },
                )


if __name__ == "__main__":
    unittest.main()
