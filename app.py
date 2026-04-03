from __future__ import annotations

import os
import random
import uuid
from datetime import datetime

import requests as http_requests
from flask import (
    Flask,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = "smart-trolley-secret-key-2025-v3"
CORS(app, origins=["http://localhost:5000"])

# ESP32 trolley hardware configuration
ESP32_IP = os.environ.get("ESP32_IP", "192.168.4.1")
ESP32_BASE_URL = f"http://{ESP32_IP}"
ESP32_TIMEOUT = 2  # seconds

PNR_DATABASE = {
    "1234567890": {"gate": "A12", "flight": "AI-101", "destination": "Delhi", "time": "18:30"},
    "9876543210": {"gate": "B7", "flight": "SG-205", "destination": "Mumbai", "time": "19:15"},
    "5555555555": {"gate": "C3", "flight": "6E-789", "destination": "Bangalore", "time": "20:00"},
    "1111111111": {"gate": "D15", "flight": "UK-456", "destination": "Kolkata", "time": "17:45"},
}

TRANSACTIONS: list[dict] = []

trolley_state = {
    "connected": False,
    "distance": 0.0,
    "mode": "Idle",
    "state": "Idle",  # "Active" or "Idle" depending on whether mode is active
    "pnr": "None",
    "battery": 100,
    "target": {},
}


@app.route("/")
def welcome():
    return render_template("welcome.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        if email and password:
            session["logged_in"] = True
            session["user_email"] = email
            return redirect(url_for("modes"))
    return render_template("login.html")


@app.route("/guest")
def guest():
    session["logged_in"] = True
    session["user_email"] = "guest@airport.com"
    return redirect(url_for("modes"))


@app.route("/register")
def register():
    return "Registration page (Coming Soon)"


@app.route("/modes")
def modes():
    if not session.get("logged_in"):
        return redirect(url_for("welcome"))
    return render_template(
        "modes.html",
        user_email=session["user_email"],
        paid=session.get("paid", False),
        trolley_state=trolley_state,
    )


@app.route("/payment")
def payment():
    if not session.get("logged_in"):
        return redirect(url_for("welcome"))
    return render_template(
        "payement.html",
        user_email=session["user_email"],
        paid=session.get("paid", False),
    )


@app.route("/self-inside")
def self_inside():
    if not session.get("logged_in") or not session.get("paid"):
        return redirect(url_for("payment"))
    return render_template("self_moving_inside.html", user_email=session["user_email"])


@app.route("/self-outside")
def self_outside():
    if not session.get("logged_in") or not session.get("paid"):
        return redirect(url_for("payment"))
    return render_template("self_moving_outside.html", user_email=session["user_email"])


@app.route("/follow")
def follow():
    if not session.get("logged_in") or not session.get("paid"):
        return redirect(url_for("payment"))
    return render_template("follow_mode.html", user_email=session["user_email"])


@app.route("/control")
def control():
    if not session.get("logged_in") or not session.get("paid"):
        return redirect(url_for("payment"))
    return render_template(
        "trolley_control.html",
        user_email=session["user_email"],
        esp32_ip=ESP32_IP,
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("welcome"))


# -----------------------
# APIs (original polling)
# -----------------------
@app.route("/api/status")
def status():
    if trolley_state["connected"]:
        try:
            r = http_requests.get(f"{ESP32_BASE_URL}/status", timeout=ESP32_TIMEOUT)
            esp_status = r.text.strip().upper()
            
            # If ESP32 is saying STOP, Idle, or INVALID, we are not actively driving
            if esp_status in ("IDLE", "STOP", "INVALID CODE"):
                trolley_state["state"] = "Idle"
            else:
                trolley_state["state"] = "Active"
        except Exception:
            pass # Keep previous state if ESP32 is busy blocking
            
    return jsonify(trolley_state)


@app.route("/api/connect", methods=["POST"])
def connect():
    trolley_state["connected"] = True
    trolley_state["distance"] = round(random.uniform(0.5, 5.0), 2)
    trolley_state["battery"] = random.randint(75, 100)
    return jsonify({"status": "success", "trolley_data": trolley_state})


@app.route("/api/disconnect", methods=["POST"])
def disconnect():
    trolley_state["connected"] = False
    return jsonify({"status": "success"})


@app.route("/api/pnr/search", methods=["POST"])
def pnr_search():
    data = request.json or {}
    pnr = (data.get("pnr") or "").strip()

    if len(pnr) != 10 or not pnr.isdigit():
        return jsonify({"status": "error", "message": "Invalid PNR"}), 400

    info = PNR_DATABASE.get(pnr)
    if not info:
        info = {"gate": f"A{random.randint(1, 20)}", "flight": "UNKNOWN"}

    return jsonify(
        {
            "status": "success",
            "gate": info["gate"],
            "flight": info.get("flight", "N/A"),
        }
    )


@app.route("/api/mode/self-inside", methods=["POST"])
def self_inside_api():
    data = request.json or {}
    gate = data.get("gate", "Unknown")
    pnr = data.get("pnr", "None")
    
    trolley_state["mode"] = "PNR Following"
    trolley_state["state"] = "Active"
    trolley_state["pnr"] = pnr
    trolley_state["target"] = {"gate": gate}
    
    # Hit ESP32 with the PNR
    _send_esp32(f"/code?val={pnr}")
    
    return jsonify({"status": "success", "message": f"Moving to gate {gate}"})


@app.route("/api/mode/self-outside", methods=["POST"])
def self_outside_api():
    data = request.json or {}
    trolley_state["mode"] = "self-outside"
    trolley_state["target"] = data
    return jsonify({"status": "success", "message": "Navigating to destination"})


@app.route("/api/mode/follow", methods=["POST"])
def follow_api():
    data = request.json or {}
    activate = data.get("activate", True)
    
    trolley_state["mode"] = "Follow Mode" if activate else "Idle"
    trolley_state["state"] = "Active" if activate else "Idle"
    trolley_state["pnr"] = "None"


    # Use explicit state param to avoid toggle desync
    state_val = "1" if activate else "0"
    esp_ok = _send_esp32(f"/AUTO?state={state_val}")

    return jsonify({
        "status": "success",
        "esp32_reached": esp_ok,
        "message": f"Following mode {'activated' if activate else 'deactivated'}",
    })


@app.route("/api/payment/process", methods=["POST"])
def process_payment():
    if not session.get("logged_in"):
        return jsonify({"status": "error"}), 401

    data = request.json or {}
    user = session.get("user_email")
    amount = data.get("amount", 0)
    method = data.get("method", "card")

    transaction = {
        "id": str(uuid.uuid4())[:8],
        "user": user,
        "amount": amount,
        "method": method,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status": "Success",
    }

    TRANSACTIONS.append(transaction)
    session["paid"] = True

    return jsonify({"status": "success", "transaction": transaction})


@app.route("/transactions")
def transactions():
    if not session.get("logged_in"):
        return redirect(url_for("welcome"))

    user = session.get("user_email")
    user_txns = [t for t in TRANSACTIONS if t["user"] == user]
    return render_template("transactions.html", transactions=user_txns, user_email=user)


@app.route("/invoice/<txn_id>")
def download_invoice(txn_id: str):
    if not session.get("logged_in"):
        return redirect(url_for("welcome"))

    txn = next((t for t in TRANSACTIONS if t["id"] == txn_id), None)
    if not txn:
        return "Invoice not found", 404

    html = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                padding: 40px;
            }}
            h1 {{
                color: #111;
            }}
            .box {{
                border: 1px solid #ddd;
                padding: 20px;
                margin-top: 20px;
            }}
            .row {{
                margin-bottom: 10px;
            }}
        </style>
    </head>
    <body>
        <h1>Smart Trolley — Payment Invoice</h1>
        <div class="box">
            <div class="row"><strong>Invoice ID:</strong> {txn["id"]}</div>
            <div class="row"><strong>Date:</strong> {txn["time"]}</div>
            <div class="row"><strong>User:</strong> {txn["user"]}</div>
            <div class="row"><strong>Payment Method:</strong> {txn["method"]}</div>
            <div class="row"><strong>Amount Paid:</strong> ₹{txn["amount"]}</div>
            <div class="row"><strong>Status:</strong> {txn["status"]}</div>
        </div>
    </body>
    </html>
    """

    response = make_response(html)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"attachment; filename=invoice_{txn_id}.pdf"
    return response


# -----------------------
# ESP32 proxy helpers
# -----------------------
def _send_esp32(path: str) -> bool:
    """Send a GET request to the ESP32 and return True on success."""
    try:
        r = http_requests.get(f"{ESP32_BASE_URL}{path}", timeout=ESP32_TIMEOUT)
        return r.status_code in (200, 204)
    except Exception:
        return False


# Map web-app command names to the actual ESP32 single-letter endpoints
_ESP32_CMD_MAP = {
    "forward":    "/F",
    "backward":   "/B",
    "left":       "/L",
    "right":      "/R",
    "stop":       "/S",
    "follow_on":  "/AUTO?state=1",
    "follow_off": "/AUTO?state=0",
}


@app.route("/api/esp32/command", methods=["POST"])
def esp32_command():
    """Generic proxy — forward a command to the ESP32 trolley."""
    data = request.json or {}
    cmd = data.get("command", "").strip().lower()

    if cmd not in _ESP32_CMD_MAP:
        return jsonify({"status": "error", "message": f"Unknown command: {cmd}"}), 400

    esp_path = _ESP32_CMD_MAP[cmd]
    ok = _send_esp32(esp_path)

    if cmd == "follow_on":
        trolley_state["mode"] = "Follow Mode"
        trolley_state["state"] = "Active"
        trolley_state["pnr"] = "None"
    elif cmd == "follow_off":
        trolley_state["mode"] = "Idle"
        trolley_state["state"] = "Idle"
        trolley_state["pnr"] = "None"
    elif cmd == "stop":
        trolley_state["mode"] = "Idle"
        trolley_state["state"] = "Idle"
    elif cmd in ("forward", "backward", "left", "right"):
        trolley_state["mode"] = "Manual Mode"
        trolley_state["state"] = "Active"
        trolley_state["pnr"] = "None"

    return jsonify({
        "status": "success" if ok else "warning",
        "esp32_reached": ok,
        "command": cmd,
        "esp32_endpoint": esp_path,
        "message": f"{'Sent' if ok else 'Queued (ESP32 offline)'}: {cmd}",
    })


@app.route("/api/esp32/ping")
def esp32_ping():
    """Check whether the ESP32 is reachable."""
    ok = _send_esp32("/")
    trolley_state["connected"] = ok
    return jsonify({"reachable": ok, "ip": ESP32_IP})


@app.route("/api/esp32/rssi")
def esp32_rssi():
    """Proxy the live RSSI/distance data from ESP32."""
    try:
        r = http_requests.get(f"{ESP32_BASE_URL}/rssi", timeout=ESP32_TIMEOUT)
        return jsonify(r.json())
    except Exception:
        return jsonify({"best": -100, "angle": 0, "dist": -1})


@app.route("/api/esp32/ip", methods=["POST"])
def set_esp32_ip():
    """Let the user update the ESP32 IP at runtime."""
    global ESP32_IP, ESP32_BASE_URL
    data = request.json or {}
    new_ip = (data.get("ip") or "").strip()
    if not new_ip:
        return jsonify({"status": "error", "message": "IP required"}), 400
    ESP32_IP = new_ip
    ESP32_BASE_URL = f"http://{ESP32_IP}"
    return jsonify({"status": "success", "ip": ESP32_IP})


if __name__ == "__main__":
    os.makedirs("templates", exist_ok=True)
    # Host 0.0.0.0 allows other devices on the same network (e.g. mobile phone) to connect
    app.run(host="0.0.0.0", debug=True, port=5000)
