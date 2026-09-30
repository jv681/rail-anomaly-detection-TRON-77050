"""
dashboard/app.py
----------------
Flask + SocketIO web dashboard for real-time rail defect visualization.

Run:
    pip install flask flask-socketio
    python dashboard/app.py

Then open: http://127.0.0.1:5000
"""

from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
from datetime import datetime
from collections import deque
import json
import threading
import random

app = Flask(__name__)
app.config["SECRET_KEY"] = "rail_defect_dashboard_2024"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ─────────────────────────────────────────────
# In-memory storage (last 200 detections)
# ─────────────────────────────────────────────
MAX_HISTORY = 200
detection_history = deque(maxlen=MAX_HISTORY)

SEVERITY_COLOR = {
    "CRITICAL": "#ff2d55",
    "HIGH":     "#ff9500",
    "MEDIUM":   "#ffcc00",
    "LOW":      "#34c759",
}

CLASS_ICON = {
    "crack":           "⚡",
    "rail_defect":     "🔧",
    "fastener_defect": "🔩",
    "obstacle":        "⚠️",
    "broken_rail":     "💥",
}

stats = {
    "total": 0,
    "by_class": {},
    "by_hour": {},
    "last_detection": None,
}

# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/history")
def get_history():
    return jsonify(list(detection_history))


@app.route("/api/stats")
def get_stats():
    return jsonify(stats)


# ─────────────────────────────────────────────
# WebSocket: receive from bridge.py, broadcast to browser
# ─────────────────────────────────────────────

@socketio.on("detection")
def handle_detection(data):
    """Called by bridge.py when STM32 sends a detection."""
    cls   = data.get("class", "unknown")
    conf  = data.get("confidence", 0.0)
    sev   = data.get("severity", "LOW")
    ts    = data.get("timestamp", datetime.now().isoformat())
    bbox  = data.get("bbox", [])
    src   = data.get("source", "stm32")

    entry = {
        "class":      cls,
        "label":      cls.replace("_", " ").title(),
        "confidence": conf,
        "severity":   sev,
        "color":      SEVERITY_COLOR.get(sev, "#8e8e93"),
        "icon":       CLASS_ICON.get(cls, "❓"),
        "bbox":       bbox,
        "timestamp":  ts,
        "source":     src,
        "id":         stats["total"] + 1,
    }

    detection_history.append(entry)

    # Update stats
    stats["total"] += 1
    stats["by_class"][cls] = stats["by_class"].get(cls, 0) + 1
    hour_key = datetime.fromisoformat(ts).strftime("%H:00") if ts else "00:00"
    stats["by_hour"][hour_key] = stats["by_hour"].get(hour_key, 0) + 1
    stats["last_detection"] = ts

    # Broadcast to all connected browsers
    socketio.emit("new_detection", entry, broadcast=True)

    # Send alert for HIGH/CRITICAL
    if sev in ("HIGH", "CRITICAL"):
        socketio.emit("alert", {
            "message": f"{'🚨' if sev == 'CRITICAL' else '⚠️'} {sev} DEFECT: {entry['label']} ({conf:.0%} confidence)",
            "severity": sev,
            "color": SEVERITY_COLOR[sev],
        }, broadcast=True)


@socketio.on("connect")
def on_connect():
    """Send current history and stats when a browser connects."""
    emit("history", list(detection_history))
    emit("stats_update", stats)
    print(f"  🌐 Browser connected")


@socketio.on("disconnect")
def on_disconnect():
    print(f"  🌐 Browser disconnected")


# ─────────────────────────────────────────────
# Optional: inject a demo detection via POST
# ─────────────────────────────────────────────

@app.route("/api/demo", methods=["POST"])
def demo_inject():
    """POST to /api/demo to inject a fake detection (for testing)."""
    classes = ["crack", "rail_defect", "fastener_defect", "obstacle", "broken_rail"]
    severity_map = {
        "crack": "HIGH", "broken_rail": "CRITICAL",
        "rail_defect": "MEDIUM", "fastener_defect": "MEDIUM", "obstacle": "HIGH"
    }
    cls = random.choice(classes)
    data = {
        "class": cls,
        "confidence": round(random.uniform(0.72, 0.99), 3),
        "severity": severity_map[cls],
        "bbox": [round(random.uniform(0.1, 0.4), 3) for _ in range(4)],
        "timestamp": datetime.now().isoformat(),
        "source": "demo",
    }
    handle_detection(data)
    return jsonify({"status": "ok", "injected": data})


if __name__ == "__main__":
    print("[RAILGUARD] Rail Defect Dashboard starting...")
    print("   Open in browser: http://127.0.0.1:5000")
    print("   To test without STM32: POST to http://127.0.0.1:5000/api/demo")
    print("   Or run: python bridge.py --demo\n")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
