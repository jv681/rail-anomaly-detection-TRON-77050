"""
bridge.py
---------
Reads detection results from STM32N657-DK over UART (USB virtual COM port)
and forwards them to the Flask dashboard via WebSocket.

Run alongside the dashboard:
    python bridge.py

Requirements:
    pip install pyserial flask-socketio

STM32 firmware should send one JSON line per detection, e.g.:
    {"class":"crack","confidence":0.94,"bbox":[x,y,w,h]}
"""

import serial
import serial.tools.list_ports
import json
import time
import threading
import argparse
from datetime import datetime

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
BAUD_RATE    = 115200
DASHBOARD_URL = "http://127.0.0.1:5000"  # Flask dashboard URL

# Severity mapping (used for alerts)
SEVERITY = {
    "crack"           : "HIGH",
    "broken_rail"     : "CRITICAL",
    "rail_defect"     : "MEDIUM",
    "fastener_defect" : "MEDIUM",
    "obstacle"        : "HIGH",
}

CLASS_NAMES = ["crack", "rail_defect", "fastener_defect", "obstacle", "broken_rail"]


def find_stm32_port():
    """Auto-detect STM32 virtual COM port."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        desc = (port.description or "").lower()
        if "stm32" in desc or "stlink" in desc or "virtual" in desc:
            print(f"  🔍 Auto-detected STM32 port: {port.device} ({port.description})")
            return port.device
    # Fallback: list all and let user pick
    print("\n  Available COM ports:")
    for i, port in enumerate(ports):
        print(f"    [{i}] {port.device} — {port.description}")
    if ports:
        choice = input("  Enter port number to use: ").strip()
        return ports[int(choice)].device
    return None


def parse_stm32_line(line: str):
    """
    Parse a line from STM32.
    Supports JSON format: {"class":"crack","confidence":0.94}
    Also supports simple text: "crack 0.94"
    """
    line = line.strip()
    if not line:
        return None

    # Try JSON first
    try:
        data = json.loads(line)
        class_id = data.get("class_id", -1)
        class_name = data.get("class", CLASS_NAMES[class_id] if 0 <= class_id < len(CLASS_NAMES) else "unknown")
        confidence = float(data.get("confidence", 0.0))
        bbox = data.get("bbox", [])
        return {
            "class": class_name,
            "confidence": round(confidence, 3),
            "severity": SEVERITY.get(class_name, "LOW"),
            "bbox": bbox,
            "timestamp": datetime.now().isoformat(),
            "source": "stm32"
        }
    except json.JSONDecodeError:
        pass

    # Try simple "classname confidence" format
    parts = line.split()
    if len(parts) >= 2:
        try:
            class_name = parts[0].lower()
            confidence = float(parts[1])
            return {
                "class": class_name,
                "confidence": round(confidence, 3),
                "severity": SEVERITY.get(class_name, "LOW"),
                "bbox": [],
                "timestamp": datetime.now().isoformat(),
                "source": "stm32"
            }
        except ValueError:
            pass

    return None


def run_bridge(port: str, socketio_client):
    """Main loop: read from STM32, emit to dashboard."""
    print(f"\n🔌 Connecting to STM32 on {port} at {BAUD_RATE} baud...")
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=2)
        print(f"✅ Connected! Listening for detections...\n")
    except serial.SerialException as e:
        print(f"❌ Failed to open {port}: {e}")
        return

    while True:
        try:
            raw = ser.readline().decode("utf-8", errors="ignore")
            detection = parse_stm32_line(raw)
            if detection:
                print(f"  📡 {detection['class']:20s} | {detection['confidence']:.2%} | {detection['severity']}")
                socketio_client.emit("detection", detection)
        except serial.SerialException:
            print("⚠️  Serial connection lost. Reconnecting in 3s...")
            time.sleep(3)
            try:
                ser.close()
                ser.open()
            except Exception:
                break
        except KeyboardInterrupt:
            print("\n👋 Bridge stopped.")
            break

    ser.close()


def run_demo_mode(socketio_client):
    """
    Demo mode: simulate STM32 detections for testing the dashboard
    without physical hardware.
    """
    import random
    print("🎭 Running in DEMO MODE (simulating STM32 detections)")
    print("   Use this to test the dashboard without physical hardware.\n")

    classes = list(SEVERITY.keys())
    while True:
        cls = random.choice(classes)
        conf = round(random.uniform(0.70, 0.99), 3)
        detection = {
            "class": cls,
            "confidence": conf,
            "severity": SEVERITY[cls],
            "bbox": [
                round(random.uniform(0, 0.5), 3),
                round(random.uniform(0, 0.5), 3),
                round(random.uniform(0.1, 0.4), 3),
                round(random.uniform(0.1, 0.4), 3),
            ],
            "timestamp": datetime.now().isoformat(),
            "source": "demo"
        }
        print(f"  🎭 {detection['class']:20s} | {detection['confidence']:.2%} | {detection['severity']}")
        socketio_client.emit("detection", detection)
        time.sleep(random.uniform(1.0, 3.0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="STM32 → Dashboard Bridge")
    parser.add_argument("--port",  type=str, help="COM port (e.g. COM3 or /dev/ttyACM0)")
    parser.add_argument("--demo",  action="store_true", help="Run in demo mode (no hardware needed)")
    args = parser.parse_args()

    # Connect to Flask-SocketIO dashboard
    try:
        import socketio as sio_lib
        client = sio_lib.SimpleClient()
        client.connect(DASHBOARD_URL)
    except Exception as e:
        print(f"⚠️  Could not connect to dashboard: {e}")
        print(f"   Make sure the dashboard is running first: python dashboard/app.py")
        exit(1)

    if args.demo:
        run_demo_mode(client)
    else:
        port = args.port or find_stm32_port()
        if not port:
            print("❌ No COM port found. Use --demo to test without hardware.")
            exit(1)
        run_bridge(port, client)
