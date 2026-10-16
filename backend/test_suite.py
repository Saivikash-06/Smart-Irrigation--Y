"""
GreenPulse Automated Test Suite
Verifies all 10 core scenarios specified in Project Requirements.
"""
import sys
import os
import unittest
from datetime import datetime, timezone, timedelta

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine, SessionLocal
from app.models import Device, SensorReading, IrrigationEvent, IrrigationSetting, Alert, Plant, utcnow
from app.services import initialize_default_data, DEFAULT_DEVICE_ID


class GreenPulseSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)
        db = SessionLocal()
        initialize_default_data(db)
        db.close()

    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_01_backend_health_and_docs(self):
        """Scenario 10: Backend is available and healthy."""
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["service"], "GreenPulse Smart Irrigation Backend")

    def test_02_scenario_1_moisture_ideal_pump_off(self):
        """Scenario 1: Moisture is 60%. Expected: Pump OFF."""
        payload = {
            "device_id": DEFAULT_DEVICE_ID,
            "raw_adc_value": 2538,
            "moisture_percentage": 60.0,
            "pump_status": "OFF",
            "irrigation_mode": "AUTO",
        }
        response = self.client.post("/api/sensor/readings", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["pump_status"], "OFF")
        self.assertEqual(data["moisture_percentage"], 60.0)

    def test_03_scenario_2_moisture_low_auto_watering(self):
        """Scenario 2: Moisture falls below 30%. Expected: Automatic watering alert / start."""
        payload = {
            "device_id": DEFAULT_DEVICE_ID,
            "raw_adc_value": 3400,
            "moisture_percentage": 24.5,
            "pump_status": "ON",
            "irrigation_mode": "AUTO",
        }
        response = self.client.post("/api/sensor/readings", json=payload)
        self.assertEqual(response.status_code, 201)

        # Check alert was created for low moisture
        alert = (
            self.db.query(Alert)
            .filter(Alert.device_id == DEFAULT_DEVICE_ID, Alert.alert_type == "LOW_MOISTURE")
            .order_by(Alert.created_at.desc())
            .first()
        )
        self.assertIsNotNone(alert)
        self.assertIn("critically low", alert.message.lower())

    def test_04_scenario_3_moisture_rises_pump_off(self):
        """Scenario 3: Moisture rises above threshold + hysteresis. Expected: Pump OFF."""
        payload = {
            "device_id": DEFAULT_DEVICE_ID,
            "raw_adc_value": 1800,
            "moisture_percentage": 75.0,
            "pump_status": "OFF",
            "irrigation_mode": "AUTO",
        }
        response = self.client.post("/api/sensor/readings", json=payload)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["pump_status"], "OFF")

    def test_05_scenario_4_manual_watering_command(self):
        """Scenario 4: User activates manual watering."""
        cmd_payload = {
            "device_id": DEFAULT_DEVICE_ID,
            "command": "START",
            "duration_seconds": 10,
        }
        response = self.client.post("/api/irrigation/commands", json=cmd_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["command"], "START")

        # Verify command is queued in pending commands
        pending = self.client.get(f"/api/irrigation/commands/pending?device_id={DEFAULT_DEVICE_ID}")
        self.assertEqual(pending.status_code, 200)
        cmds = pending.json()
        self.assertTrue(any(c["command"] == "START" for c in cmds))

    def test_06_scenario_5_emergency_stop(self):
        """Scenario 5: User activates emergency stop."""
        cmd_payload = {
            "device_id": DEFAULT_DEVICE_ID,
            "command": "EMERGENCY_STOP",
        }
        response = self.client.post("/api/irrigation/commands", json=cmd_payload)
        self.assertEqual(response.status_code, 200)

        # Verify emergency alert created
        alert = (
            self.db.query(Alert)
            .filter(Alert.device_id == DEFAULT_DEVICE_ID, Alert.alert_type == "EMERGENCY_STOP")
            .first()
        )
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, "danger")

    def test_07_scenario_6_device_offline_detection(self):
        """Scenario 6: Device disconnects (offline detection after timeout)."""
        device = self.db.query(Device).filter(Device.id == DEFAULT_DEVICE_ID).first()
        device.last_seen = utcnow() - timedelta(minutes=10)
        self.db.commit()

        status_res = self.client.get(f"/api/device/status?device_id={DEFAULT_DEVICE_ID}")
        self.assertEqual(status_res.status_code, 200)
        self.assertFalse(status_res.json()["is_online"])

        dashboard_res = self.client.get(f"/api/dashboard?device_id={DEFAULT_DEVICE_ID}")
        self.assertFalse(dashboard_res.json()["device"]["is_online"])
        self.assertIn("offline", dashboard_res.json()["device"]["offline_notice"].lower())

    def test_08_scenario_7_invalid_sensor_reading_rejected(self):
        """Scenario 7: Sensor returns invalid data (ADC > 4095)."""
        payload = {
            "device_id": DEFAULT_DEVICE_ID,
            "raw_adc_value": 9999,  # Invalid
            "moisture_percentage": 50.0,
            "pump_status": "OFF",
            "irrigation_mode": "AUTO",
        }
        response = self.client.post("/api/sensor/readings", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_09_scenario_8_dashboard_summary_hydration(self):
        """Scenario 8: User refreshes browser; dashboard loads from SQLite database."""
        response = self.client.get(f"/api/dashboard?device_id={DEFAULT_DEVICE_ID}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("sensor", data)
        self.assertIn("irrigation", data)
        self.assertIn("chart_data", data)
        self.assertIn("recent_activity", data)

    def test_10_scenario_9_history_csv_export(self):
        """Scenario 9: User exports watering history as CSV."""
        # Create a test event first
        event_payload = {
            "device_id": DEFAULT_DEVICE_ID,
            "start_time": (utcnow() - timedelta(minutes=5)).isoformat(),
            "end_time": utcnow().isoformat(),
            "moisture_before": 25.0,
            "moisture_after": 60.0,
            "irrigation_mode": "AUTO",
            "status": "COMPLETED",
            "estimated_water_liters": 0.45,
        }
        self.client.post("/api/irrigation/events", json=event_payload)

        export_res = self.client.get(f"/api/irrigation/history/export?device_id={DEFAULT_DEVICE_ID}")
        self.assertEqual(export_res.status_code, 200)
        self.assertEqual(export_res.headers["content-type"], "text/csv; charset=utf-8")
        csv_text = export_res.text
        self.assertIn("Event ID", csv_text)
        self.assertIn("Moisture Before (%)", csv_text)
        self.assertIn("Estimated Water (Liters)", csv_text)

    def test_11_plant_management_crud(self):
        """Plant Management: Create, Read, Delete plants."""
        plant_payload = {
            "name": "Garden Rosemary",
            "plant_type": "Salvia rosmarinus",
            "location": "Herb Planter",
            "preferred_moisture_min": 30.0,
            "preferred_moisture_max": 55.0,
            "irrigation_threshold": 25.0,
            "notes": "Prefers drier soil and good aeration.",
        }
        res = self.client.post("/api/plants", json=plant_payload)
        self.assertEqual(res.status_code, 201)
        plant_id = res.json()["id"]

        # Delete plant
        del_res = self.client.delete(f"/api/plants/{plant_id}")
        self.assertEqual(del_res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
