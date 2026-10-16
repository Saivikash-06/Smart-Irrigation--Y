"""
GreenPulse – Smart Irrigation and Garden Monitoring System
ESP32 MicroPython Firmware for Wokwi Simulation & Hardware

GPIO Assignments:
  - Potentiometer (Soil Moisture Sensor): GPIO 34 (ADC1_CH6)
  - LED (Water Pump Indicator):           GPIO 26 (Digital Output)
  - Pushbutton (Manual Watering Button):  GPIO 27 (Input with Internal Pull-up)
"""

import time

# MicroPython Hardware and Network Imports with IDE/Desktop fallbacks
try:
    import network
except ImportError:
    network = None  # type: ignore

try:
    import ujson as json
except ImportError:
    import json  # type: ignore

try:
    import urequests as requests
except ImportError:
    try:
        import requests  # type: ignore
    except ImportError:
        requests = None  # type: ignore

try:
    from machine import Pin, ADC
except ImportError:
    # Desktop IDE fallback mocks for static analysis and linting
    class Pin:  # type: ignore
        IN = 1
        OUT = 2
        PULL_UP = 3
        def __init__(self, pin, mode=None, pull=None):
            self.pin = pin
        def value(self, val=None):
            return 0

    class ADC:  # type: ignore
        ATTN_11DB = 3
        def __init__(self, pin):
            self.pin = pin
        def atten(self, att):
            pass
        def read(self):
            return 2048

# Provide time compatibility helpers if inspected in desktop Python
if not hasattr(time, "ticks_ms"):
    setattr(time, "ticks_ms", lambda: int(time.time() * 1000))
if not hasattr(time, "ticks_diff"):
    setattr(time, "ticks_diff", lambda a, b: a - b)
if not hasattr(time, "sleep_ms"):
    setattr(time, "sleep_ms", lambda ms: time.sleep(ms / 1000.0))

# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================
DEVICE_ID = "esp32-greenpulse-01"

# Wi-Fi Credentials (Default Wokwi-GUEST simulator Wi-Fi)
WIFI_SSID = "Wokwi-GUEST"
WIFI_PASSWORD = ""

# Backend API URL
# NOTE: If using Wokwi web simulator to connect to local PC:
# - Option 1: Use Wokwi IoT Gateway with host IP (e.g. "http://10.0.2.2:8000")
# - Option 2: Use your local LAN IP (e.g. "http://192.168.1.50:8000") with Wokwi Gateway
# - Option 3: Use a public tunnel like ngrok or Cloudflare tunnel (e.g. "https://xxxx.ngrok-free.app")
# Replace with your active backend host URL:
BACKEND_URL = "http://10.0.2.2:8000"

# Calibration Defaults (Potentiometer simulates 0-3.3V ADC)
# Potentiometer at 3.3V (ADC ~4095) represents Dry soil
# Potentiometer at 0V-1.2V (ADC ~1500) represents Wet soil
DRY_ADC = 4095
WET_ADC = 1500

# Irrigation Safety & Logic Parameters
DEFAULT_THRESHOLD = 30.0          # Below 30% triggers watering
HYSTERESIS = 5.0                  # Turn off when moisture >= threshold + 5%
DEFAULT_WATERING_DURATION = 10    # seconds per watering cycle
MIN_CYCLE_INTERVAL = 60           # seconds minimum wait between auto cycles
MAX_SAFETY_DURATION = 30          # seconds hard limit for any watering cycle

# Loop Timing
TELEMETRY_INTERVAL_MS = 3000      # Send sensor reading every 3 seconds
BUTTON_DEBOUNCE_MS = 250          # Button debounce threshold

# ==============================================================================
# HARDWARE INITIALIZATION
# ==============================================================================
# Potentiometer on GPIO 34 (ADC)
pot_adc = ADC(Pin(34))
pot_adc.atten(ADC.ATTN_11DB)       # 0 - 3.3V measurement range

# LED on GPIO 26 (Pump Indicator)
pump_led = Pin(26, Pin.OUT)
pump_led.value(0)                  # Start in safe OFF state

# Pushbutton on GPIO 27 (Internal Pull-Up, Active LOW)
btn_manual = Pin(27, Pin.IN, Pin.PULL_UP)

# ==============================================================================
# RUNTIME STATE
# ==============================================================================
state = {
    "pump_on": False,
    "automatic_mode": True,
    "moisture_threshold": DEFAULT_THRESHOLD,
    "watering_duration": DEFAULT_WATERING_DURATION,
    "watering_start_time": 0,
    "last_cycle_end_time": 0,
    "moisture_at_start": 0.0,
    "active_event_mode": "AUTO",
    "emergency_stop": False,
    "last_telemetry_ms": 0,
    "last_btn_press_ms": 0,
    "btn_prev_state": 1,
    "is_connected": False,
}


def log(msg):
    """Timestamped diagnostic console output."""
    print("[GreenPulse ESP32] " + msg)


def connect_wifi():
    """Initializes Wi-Fi connection with non-fatal retry."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        log("Connecting to Wi-Fi network: " + WIFI_SSID + "...")
        try:
            wlan.connect(WIFI_SSID, WIFI_PASSWORD)
            start = time.time()
            while not wlan.isconnected() and (time.time() - start) < 8:
                time.sleep(0.5)
        except Exception as e:
            log("Wi-Fi connection attempt failed: " + str(e))

    if wlan.isconnected():
        ip_info = wlan.ifconfig()
        log("Wi-Fi Connected successfully! IP Address: " + ip_info[0])
        state["is_connected"] = True
    else:
        log("Running in offline mode (Wi-Fi not connected). Hardware control is active.")
        state["is_connected"] = False


def read_moisture():
    """
    Reads potentiometer ADC value and applies calibration curve:
    moisture_percentage = (adc_value - dry_adc) / (wet_adc - dry_adc) * 100
    Clamped strictly between 0% and 100%.
    """
    try:
        raw_adc = pot_adc.read()
    except Exception as e:
        log("ADC Read Error: " + str(e))
        return 4095, 0.0, False

    # Validation: ADC must be within 12-bit range
    if raw_adc < 0 or raw_adc > 4095:
        log("WARNING: Invalid ADC reading detected (" + str(raw_adc) + ")")
        return raw_adc, 0.0, False

    denom = float(WET_ADC - DRY_ADC)
    if denom == 0:
        denom = 1.0

    pct = ((raw_adc - DRY_ADC) / denom) * 100.0
    pct = max(0.0, min(100.0, pct))
    return raw_adc, round(pct, 1), True


def start_pump(mode="AUTO", duration=DEFAULT_WATERING_DURATION, current_moisture=0.0):
    """Safely activates the pump LED and logs event start."""
    if state["emergency_stop"]:
        log("BLOCKED: Cannot start pump while Emergency Stop is active.")
        return False

    if state["pump_on"]:
        return True  # Already active

    # Enforce safety max duration
    duration = min(duration, MAX_SAFETY_DURATION)

    pump_led.value(1)
    state["pump_on"] = True
    state["watering_start_time"] = time.time()
    state["watering_duration"] = duration
    state["moisture_at_start"] = current_moisture
    state["active_event_mode"] = mode

    log(">>> PUMP ACTIVATED (" + mode + " MODE). Planned duration: " + str(duration) + "s. Soil Moisture: " + str(current_moisture) + "%")
    return True


def stop_pump(status="COMPLETED", current_moisture=0.0):
    """Safely deactivates pump LED and records watering cycle metrics."""
    if not state["pump_on"]:
        return

    pump_led.value(0)
    state["pump_on"] = False
    now = time.time()
    run_seconds = max(1, now - state["watering_start_time"])
    state["last_cycle_end_time"] = now

    # Estimated water: 0.02 L/sec (~1.2 Liters/minute)
    water_used = round(run_seconds * 0.02, 2)

    log("<<< PUMP DEACTIVATED (" + status + "). Total run time: " + str(run_seconds) + "s. Est. Water: " + str(water_used) + "L. Final Moisture: " + str(current_moisture) + "%")

    # Dispatch event to backend if connected
    send_event_to_backend(
        start_time=state["watering_start_time"],
        end_time=now,
        moisture_before=state["moisture_at_start"],
        moisture_after=current_moisture,
        mode=state["active_event_mode"],
        status=status,
        water_liters=water_used,
    )


def send_event_to_backend(start_time, end_time, moisture_before, moisture_after, mode, status, water_liters):
    """Sends recorded irrigation event to backend API."""
    if not state["is_connected"]:
        return
    try:
        url = BACKEND_URL + "/api/irrigation/events"
        payload = {
            "device_id": DEVICE_ID,
            "start_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_time)),
            "end_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end_time)),
            "moisture_before": moisture_before,
            "moisture_after": moisture_after,
            "irrigation_mode": mode,
            "status": status,
            "estimated_water_liters": water_liters,
        }
        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        res.close()
        log("Irrigation event uploaded to backend.")
    except Exception as e:
        log("Could not upload irrigation event: " + str(e))


def send_telemetry_and_check_commands(raw_adc, moisture):
    """Sends telemetry reading to backend and processes pending commands."""
    if not state["is_connected"]:
        return

    # 1. Send Sensor Reading
    try:
        url = BACKEND_URL + "/api/sensor/readings"
        payload = {
            "device_id": DEVICE_ID,
            "raw_adc_value": raw_adc,
            "moisture_percentage": moisture,
            "pump_status": "ON" if state["pump_on"] else "OFF",
            "irrigation_mode": "AUTO" if state["automatic_mode"] else "MANUAL",
        }
        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        res.close()
    except Exception as e:
        # Don't crash loop on network hiccups
        pass

    # 2. Check for Pending Commands from Dashboard
    try:
        url = BACKEND_URL + "/api/irrigation/commands/pending?device_id=" + DEVICE_ID
        res = requests.get(url)
        if res.status_code == 200:
            cmds = res.json()
            for cmd in cmds:
                exec_command(cmd)
        res.close()
    except Exception as e:
        pass


def exec_command(cmd):
    """Executes a command dispatched from the backend web dashboard."""
    cmd_id = cmd.get("id")
    command_str = cmd.get("command", "").upper()
    duration = cmd.get("duration_seconds", DEFAULT_WATERING_DURATION)

    log("Processing backend command: " + command_str + " (ID: " + str(cmd_id) + ")")

    if command_str in ("START", "START_WATERING"):
        start_pump("MANUAL", duration=duration, current_moisture=0.0)

    elif command_str in ("STOP", "STOP_WATERING"):
        stop_pump("MANUAL_STOP", current_moisture=0.0)

    elif command_str in ("SET_MODE_AUTO", "AUTO"):
        state["automatic_mode"] = True
        log("Irrigation mode switched to AUTOMATIC.")

    elif command_str in ("SET_MODE_MANUAL", "MANUAL"):
        state["automatic_mode"] = False
        log("Irrigation mode switched to MANUAL.")

    elif command_str == "EMERGENCY_STOP":
        state["emergency_stop"] = True
        stop_pump("EMERGENCY_STOP", current_moisture=0.0)
        log("EMERGENCY STOP ENGAGED! System locked.")

    # Acknowledge command completion
    try:
        ack_url = BACKEND_URL + "/api/irrigation/commands/ack?command_id=" + str(cmd_id) + "&status=EXECUTED"
        res = requests.post(ack_url)
        res.close()
    except Exception as e:
        log("Failed to acknowledge command: " + str(e))


def check_pushbutton(current_moisture):
    """Reads hardware pushbutton on GPIO 27 with software debouncing."""
    now_ms = time.ticks_ms()
    btn_val = btn_manual.value()  # 0 when pressed, 1 when released

    # Detect falling edge (1 -> 0)
    if btn_val == 0 and state["btn_prev_state"] == 1:
        if time.ticks_diff(now_ms, state["last_btn_press_ms"]) > BUTTON_DEBOUNCE_MS:
            state["last_btn_press_ms"] = now_ms
            log("Hardware Pushbutton Pressed on GPIO 27!")

            if state["pump_on"]:
                stop_pump("BUTTON_TOGGLE", current_moisture=current_moisture)
            else:
                start_pump("MANUAL", duration=DEFAULT_WATERING_DURATION, current_moisture=current_moisture)

    state["btn_prev_state"] = btn_val


# ==============================================================================
# MAIN CONTROL LOOP
# ==============================================================================
def main():
    log("==================================================")
    log("GreenPulse Smart Irrigation System Starting...")
    log("Hardware: ESP32 | Potentiometer(GPIO 34) | LED(GPIO 26) | Pushbutton(GPIO 27)")
    log("==================================================")

    # Initialize Network
    connect_wifi()

    while True:
        now_time = time.time()
        now_ms = time.ticks_ms()

        # 1. Read Soil Moisture Sensor (Potentiometer)
        raw_adc, moisture, is_valid = read_moisture()

        # 2. Check Pushbutton (Manual watering trigger)
        check_pushbutton(moisture)

        # 3. Automatic Irrigation Logic
        if is_valid and not state["emergency_stop"]:
            if state["automatic_mode"]:
                # Check if pump is currently running
                if state["pump_on"]:
                    elapsed = now_time - state["watering_start_time"]

                    # Stop conditions:
                    # Condition A: Soil moisture reached comfort hysteresis target
                    # Condition B: Max cycle duration elapsed
                    if moisture >= (state["moisture_threshold"] + HYSTERESIS):
                        stop_pump("MOISTURE_TARGET_REACHED", current_moisture=moisture)
                    elif elapsed >= state["watering_duration"]:
                        stop_pump("DURATION_LIMIT_REACHED", current_moisture=moisture)

                else:
                    # Pump is OFF. Check if auto watering condition is met:
                    # - Moisture below threshold (e.g. 30%)
                    # - Minimum interval between cycles has elapsed
                    time_since_last = now_time - state["last_cycle_end_time"]
                    if (moisture < state["moisture_threshold"]) and (time_since_last >= MIN_CYCLE_INTERVAL):
                        start_pump("AUTO", duration=state["watering_duration"], current_moisture=moisture)

            else:
                # Manual mode: still enforce maximum safety duration to protect pump
                if state["pump_on"]:
                    elapsed = now_time - state["watering_start_time"]
                    if elapsed >= state["watering_duration"]:
                        stop_pump("MANUAL_DURATION_LIMIT", current_moisture=moisture)

        elif not is_valid and state["pump_on"]:
            # Sensor error safe state: turn off pump immediately
            log("CRITICAL: Invalid sensor reading detected! Engaging safe-state stop.")
            stop_pump("SENSOR_FAULT_STOP", current_moisture=0.0)

        # 4. Telemetry and Cloud Synchronization
        if time.ticks_diff(now_ms, state["last_telemetry_ms"]) >= TELEMETRY_INTERVAL_MS:
            state["last_telemetry_ms"] = now_ms
            log("Telemetry: Moisture: " + str(moisture) + "% | ADC: " + str(raw_adc) + " | Pump: " + ("ON" if state["pump_on"] else "OFF") + " | Mode: " + ("AUTO" if state["automatic_mode"] else "MANUAL"))
            send_telemetry_and_check_commands(raw_adc, moisture)

        # Non-blocking pause
        time.sleep_ms(50)


if __name__ == "__main__":
    main()
