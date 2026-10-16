# GreenPulse – Wokwi ESP32 Circuit Simulation Guide

This folder contains the complete circuit definition (`diagram.json`) and MicroPython firmware (`main.py`) for the GreenPulse Smart Irrigation & Garden Monitoring System.

---

## 1. Hardware Components & GPIO Assignments

| Component | Function | Pins / Connection | Details |
| :--- | :--- | :--- | :--- |
| **ESP32 DevKit** | IoT Microcontroller | 3V3, GND, GPIO 34, 26, 27 | Runs MicroPython |
| **Potentiometer** | Simulates Soil Moisture Sensor | Outer: 3V3 & GND<br>Middle: **GPIO 34** (ADC) | 12-bit ADC (0–4095). High voltage = Dry soil, Low voltage = Wet soil. |
| **Green LED** | Represents Irrigation Pump | Anode: 220Ω resistor to **GPIO 26**<br>Cathode: GND | Lights up when pump is active |
| **220Ω Resistor** | Protects LED | In series between GPIO 26 and LED anode | Current-limiting protection |
| **Pushbutton** | Manual Watering Trigger | Terminal 1: **GPIO 27**<br>Terminal 2: GND | Configured with internal pull-up resistor (active LOW) |

> **Note on Soil Moisture Simulation**: The potentiometer simulates the analog output of a capacitive/resistive soil moisture probe. Rotating the potentiometer dials changes the simulated soil moisture between 0% (bone dry) and 100% (saturated).

---

## 2. Running in Wokwi (Web Simulator or VS Code Extension)

### Option A: Online at wokwi.com
1. Go to [wokwi.com](https://wokwi.com/projects/new/esp32) and select **MicroPython on ESP32**.
2. Replace `diagram.json` with the contents of [diagram.json](diagram.json).
3. Replace `main.py` with the contents of [main.py](main.py).
4. Click the green **Play** button to begin simulation.

### Option B: Local Simulation via Wokwi VS Code Extension
1. Install the official "Wokwi Simulator" extension in VS Code.
2. Open the `wokwi/` folder.
3. Press `F1` and select **Wokwi: Start Simulator**.

---

## 3. Network Configuration & Backend Communication

In Wokwi simulation, the ESP32 connects to the virtual Wi-Fi access point:
- **SSID**: `Wokwi-GUEST`
- **Password**: *(leave blank)*

### Connecting the Simulated ESP32 to Your Local FastAPI Backend
Because Wokwi runs in a browser sandbox, it cannot directly reach `http://localhost:8000` on your physical computer without a bridge. Use one of these standard methods:

#### Method 1: Wokwi IoT Gateway (Recommended for Local Dev)
1. Download and run the **Wokwi IoT Gateway** executable from the Wokwi documentation.
2. In `wokwi/main.py`, set:
   ```python
   BACKEND_URL = "http://10.0.2.2:8000"
   # or your local machine IP e.g. "http://192.168.1.100:8000"
   ```
3. Start the FastAPI backend on port 8000: `python run_server.py`.
4. Run the Wokwi simulation. The ESP32 will transmit live telemetry to your local backend.

#### Method 2: Public Tunnel (ngrok / Cloudflare Tunnel / localtunnel)
If you don't use the Wokwi Gateway, expose port 8000 publicly:
```powershell
npx localtunnel --port 8000
# or: ngrok http 8000
```
Then update `BACKEND_URL` in `wokwi/main.py`:
```python
BACKEND_URL = "https://your-public-url.ngrok-free.app"
```

#### Method 3: GreenPulse Web Demo Mode (No Network Setup Required)
The GreenPulse web dashboard includes an interactive **Demo Mode** toggle with 1-click test scenarios (Scenario 1 through 7) so you can evaluate the complete frontend, backend, database, and safety logic without needing network bridges.

---

## 4. Testing Hardware Behavior

1. **Auto Watering**:
   - Turn potentiometer clockwise towards dry range (ADC > 3200, Moisture < 30%).
   - The LED on GPIO 26 turns **ON**.
   - MicroPython console prints: `>>> PUMP ACTIVATED (AUTO MODE)`.
2. **Auto Stop on Moisture Recovery**:
   - Turn potentiometer counter-clockwise towards wet range (Moisture > 35%).
   - The LED turns **OFF** immediately due to hysteresis.
   - MicroPython console prints: `<<< PUMP DEACTIVATED (MOISTURE_TARGET_REACHED)`.
3. **Manual Pushbutton**:
   - Press the Blue pushbutton on GPIO 27.
   - The pump LED toggles ON for the configured 10-second duration.
   - Pressing again toggles it OFF.
