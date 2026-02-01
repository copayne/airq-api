"""Integration tests for alert system GraphQL operations."""

import pytest
from unittest.mock import patch
from app.models import User, Sensor, AlertThreshold, AlertHistory, SensorReading


@pytest.fixture
def alert_user(session):
    """Create a test user for alert tests."""
    user = User(
        email="alertuser@test.com",
        username="alertuser",
        role="user",
        is_active=True,
        email_verified=True,
    )
    user.set_password("testpass123")
    session.add(user)
    session.commit()
    return user


@pytest.fixture
def auth_token(alert_user):
    """Generate JWT token for the test user."""
    import os
    os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
    return alert_user.generate_jwt_token()


@pytest.fixture
def auth_graphql_executor(client, auth_token):
    """GraphQL executor with authentication."""
    def execute_query(query: str, variables: dict = None):
        response = client.post(
            "/graphql",
            json={"query": query, "variables": variables or {}},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {auth_token}",
            },
        )
        return response.get_json()
    return execute_query


@pytest.mark.integration
class TestAlertThresholdMutations:
    """Tests for alert threshold CRUD operations."""

    def test_upsert_creates_threshold(self, auth_graphql_executor):
        mutation = """
        mutation UpsertThreshold($input: UpsertAlertThresholdInput!) {
            upsertAlertThreshold(input: $input) {
                success
                message
                errors
                alertThreshold {
                    id
                    warningPpm
                    criticalPpm
                    cooldownMinutes
                    isEnabled
                }
            }
        }
        """
        result = auth_graphql_executor(mutation, {
            "input": {
                "warningPpm": 800,
                "criticalPpm": 1200,
                "cooldownMinutes": 15,
            }
        })
        data = result.get("data", {}).get("upsertAlertThreshold", {})
        assert data["success"] is True
        assert data["alertThreshold"]["warningPpm"] == 800
        assert data["alertThreshold"]["criticalPpm"] == 1200

    def test_upsert_rejects_invalid_ppm(self, auth_graphql_executor):
        mutation = """
        mutation UpsertThreshold($input: UpsertAlertThresholdInput!) {
            upsertAlertThreshold(input: $input) {
                success
                message
                errors
            }
        }
        """
        # warning >= critical should fail
        result = auth_graphql_executor(mutation, {
            "input": {
                "warningPpm": 1500,
                "criticalPpm": 1000,
            }
        })
        data = result.get("data", {}).get("upsertAlertThreshold", {})
        assert data["success"] is False

    def test_delete_threshold(self, auth_graphql_executor, session, alert_user):
        # Create threshold directly
        threshold = AlertThreshold(
            user_id=alert_user.id,
            warning_ppm=1000,
            critical_ppm=1500,
            cooldown_minutes=30,
        )
        session.add(threshold)
        session.commit()

        mutation = """
        mutation DeleteThreshold($id: ID!) {
            deleteAlertThreshold(id: $id) {
                success
                message
            }
        }
        """
        result = auth_graphql_executor(mutation, {"id": str(threshold.id)})
        data = result.get("data", {}).get("deleteAlertThreshold", {})
        assert data["success"] is True


@pytest.mark.integration
class TestAlertQueries:
    """Tests for alert query operations."""

    def test_alert_thresholds_query(self, auth_graphql_executor, session, alert_user):
        threshold = AlertThreshold(
            user_id=alert_user.id,
            warning_ppm=900,
            critical_ppm=1400,
            cooldown_minutes=20,
        )
        session.add(threshold)
        session.commit()

        query = """
        query {
            alertThresholds {
                id
                warningPpm
                criticalPpm
            }
        }
        """
        result = auth_graphql_executor(query)
        thresholds = result.get("data", {}).get("alertThresholds", [])
        assert len(thresholds) >= 1
        assert any(t["warningPpm"] == 900 for t in thresholds)

    def test_unacknowledged_count(self, auth_graphql_executor, session, alert_user, sample_sensor):
        # Create threshold and alert history entry
        threshold = AlertThreshold(
            user_id=alert_user.id,
            warning_ppm=1000,
            critical_ppm=1500,
            cooldown_minutes=30,
        )
        session.add(threshold)
        session.flush()

        reading = SensorReading(sensor_id=sample_sensor.id)
        session.add(reading)
        session.flush()

        alert = AlertHistory(
            user_id=alert_user.id,
            sensor_id=sample_sensor.id,
            reading_id=reading.id,
            threshold_id=threshold.id,
            co2_ppm=1100,
            severity="warning",
            channels_sent="browser",
            acknowledged=False,
        )
        session.add(alert)
        session.commit()

        query = """
        query {
            unacknowledgedAlertCount
        }
        """
        result = auth_graphql_executor(query)
        count = result.get("data", {}).get("unacknowledgedAlertCount", 0)
        assert count >= 1


@pytest.mark.integration
class TestSendTestAlert:
    """Tests for the send test alert mutation."""

    @patch("app.email_service.email_service.send_co2_alert", return_value=True)
    def test_send_test_alert_success(self, mock_send, auth_graphql_executor):
        mutation = """
        mutation {
            sendTestAlert {
                success
                message
            }
        }
        """
        result = auth_graphql_executor(mutation)
        data = result.get("data", {}).get("sendTestAlert", {})
        assert data["success"] is True
        assert "sent" in data["message"].lower()
        mock_send.assert_called_once()

    @patch("app.email_service.email_service.send_co2_alert", return_value=False)
    def test_send_test_alert_failure(self, mock_send, auth_graphql_executor):
        mutation = """
        mutation {
            sendTestAlert {
                success
                message
            }
        }
        """
        result = auth_graphql_executor(mutation)
        data = result.get("data", {}).get("sendTestAlert", {})
        assert data["success"] is False


@pytest.mark.integration
class TestAcknowledgeMutations:
    """Tests for alert acknowledgement."""

    def test_acknowledge_single_alert(self, auth_graphql_executor, session, alert_user, sample_sensor):
        threshold = AlertThreshold(
            user_id=alert_user.id,
            warning_ppm=1000,
            critical_ppm=1500,
            cooldown_minutes=30,
        )
        session.add(threshold)
        session.flush()

        reading = SensorReading(sensor_id=sample_sensor.id)
        session.add(reading)
        session.flush()

        alert = AlertHistory(
            user_id=alert_user.id,
            sensor_id=sample_sensor.id,
            reading_id=reading.id,
            threshold_id=threshold.id,
            co2_ppm=1600,
            severity="critical",
            channels_sent="email,browser",
            acknowledged=False,
        )
        session.add(alert)
        session.commit()

        mutation = """
        mutation AckAlert($id: ID!) {
            acknowledgeAlert(id: $id) {
                success
                message
            }
        }
        """
        result = auth_graphql_executor(mutation, {"id": str(alert.id)})
        data = result.get("data", {}).get("acknowledgeAlert", {})
        assert data["success"] is True

    def test_acknowledge_all(self, auth_graphql_executor, session, alert_user, sample_sensor):
        threshold = AlertThreshold(
            user_id=alert_user.id,
            warning_ppm=1000,
            critical_ppm=1500,
            cooldown_minutes=30,
        )
        session.add(threshold)
        session.flush()

        reading = SensorReading(sensor_id=sample_sensor.id)
        session.add(reading)
        session.flush()

        for i in range(3):
            alert = AlertHistory(
                user_id=alert_user.id,
                sensor_id=sample_sensor.id,
                reading_id=reading.id,
                threshold_id=threshold.id,
                co2_ppm=1100 + i * 100,
                severity="warning",
                channels_sent="browser",
                acknowledged=False,
            )
            session.add(alert)
        session.commit()

        mutation = """
        mutation {
            acknowledgeAllAlerts {
                success
                count
            }
        }
        """
        result = auth_graphql_executor(mutation)
        data = result.get("data", {}).get("acknowledgeAllAlerts", {})
        assert data["success"] is True
        assert data["count"] >= 3
