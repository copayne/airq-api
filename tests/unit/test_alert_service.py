"""Unit tests for the CO2 alert service."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from app.alert_service import (
    _determine_severity,
    _is_in_cooldown,
    _send_notifications,
    check_and_send_alerts,
)
from app.models import AlertThreshold, AlertCooldown


@pytest.mark.unit
class TestDetermineSeverity:
    """Table-driven tests for severity determination."""

    @pytest.mark.parametrize(
        "co2_ppm, warning, critical, expected",
        [
            (400, 1000, 1500, None),
            (999, 1000, 1500, None),
            (1000, 1000, 1500, "warning"),
            (1200, 1000, 1500, "warning"),
            (1499, 1000, 1500, "warning"),
            (1500, 1000, 1500, "critical"),
            (2000, 1000, 1500, "critical"),
            (800, 800, 1000, "warning"),
            (1000, 800, 1000, "critical"),
        ],
    )
    def test_severity_levels(self, co2_ppm, warning, critical, expected):
        threshold = MagicMock(spec=AlertThreshold)
        threshold.warning_ppm = warning
        threshold.critical_ppm = critical
        assert _determine_severity(co2_ppm, threshold) == expected


@pytest.mark.unit
class TestCooldownLogic:
    """Table-driven tests for cooldown enforcement."""

    @pytest.mark.parametrize(
        "last_alert_minutes_ago, cooldown_minutes, last_severity, current_severity, expected_in_cooldown",
        [
            # No cooldown record → not in cooldown (handled by None check, tested separately)
            # Within cooldown, same severity → blocked
            (10, 30, "warning", "warning", True),
            (10, 30, "critical", "critical", True),
            # Cooldown expired → not blocked
            (31, 30, "warning", "warning", False),
            (60, 30, "critical", "critical", False),
            # Escalation: warning → critical within cooldown → not blocked
            (10, 30, "warning", "critical", False),
            # De-escalation: critical → warning within cooldown → blocked
            (10, 30, "critical", "warning", True),
        ],
    )
    def test_cooldown_enforcement(
        self, last_alert_minutes_ago, cooldown_minutes, last_severity, current_severity, expected_in_cooldown
    ):
        with patch("app.alert_service.AlertCooldown") as MockCooldown:
            cooldown = MagicMock(spec=AlertCooldown)
            cooldown.last_alert_time = datetime.utcnow() - timedelta(minutes=last_alert_minutes_ago)
            cooldown.last_severity = last_severity
            MockCooldown.query.filter_by.return_value.first.return_value = cooldown

            result = _is_in_cooldown(
                user_id=1, sensor_id=1, cooldown_minutes=cooldown_minutes, current_severity=current_severity
            )
            assert result == expected_in_cooldown

    def test_no_cooldown_record_returns_false(self):
        with patch("app.alert_service.AlertCooldown") as MockCooldown:
            MockCooldown.query.filter_by.return_value.first.return_value = None
            result = _is_in_cooldown(user_id=1, sensor_id=1, cooldown_minutes=30, current_severity="warning")
            assert result is False


@pytest.mark.unit
class TestCheckAndSendAlerts:
    """Tests for the main alert orchestration function."""

    @patch("app.alert_service._process_alerts")
    def test_exceptions_are_caught(self, mock_process):
        """Alert failures must never propagate."""
        mock_process.side_effect = RuntimeError("database exploded")
        # Should not raise
        check_and_send_alerts(sensor_id=1, reading_id=1, co2_ppm=2000)

    @patch("app.alert_service._process_alerts")
    def test_delegates_to_process_alerts(self, mock_process):
        check_and_send_alerts(sensor_id=5, reading_id=10, co2_ppm=1200)
        mock_process.assert_called_once_with(5, 10, 1200)


@pytest.mark.unit
class TestSendNotifications:
    """Tests for email status tracking in _send_notifications."""

    @pytest.mark.parametrize(
        "email_success, expected_email_status, expected_has_email_channel",
        [
            (True, "sent", True),
            (False, "failed", False),
        ],
    )
    @patch("app.alert_service._send_email_alert")
    def test_email_status_tracking(
        self, mock_send_email, email_success, expected_email_status, expected_has_email_channel
    ):
        mock_send_email.return_value = email_success
        threshold = MagicMock(spec=AlertThreshold)
        threshold.user_id = 1

        channels, email_status = _send_notifications(threshold, "Living Room", 1200, "warning")

        assert email_status == expected_email_status
        assert ("email" in channels) == expected_has_email_channel
        assert "browser" in channels
