"""
Server Monitor Dashboard - Flask Application
Domain: Server-Monitor.traceez.com
"""

import os
import sys
import functools
from datetime import datetime

# 讓 web/app.py 可以 import 根目錄的 config（共用 .env）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pymssql
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash
)

# 載入根目錄的 .env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "sm-dashboard-k8x#2q!f7$zp")
app.config["PERMANENT_SESSION_LIFETIME"] = 3600  # 1 hour

# ---------------------------------------------------------------------------
# Auth config
# ---------------------------------------------------------------------------
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "54389507@TT")

# ---------------------------------------------------------------------------
# Database config (共用 MONITOR_DB 設定)
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "server":   os.environ.get("MONITOR_DB_HOST", "3.105.244.207"),
    "database": os.environ.get("MONITOR_DB_NAME", "ServerMonitor"),
    "user":     os.environ.get("MONITOR_DB_USER", "sinomostw"),
    "password": os.environ.get("MONITOR_DB_PASSWORD", "02Tracker"),
    "charset":  "utf8",
    "timeout":  10,
}

DASHBOARD_SQL = """
SELECT
    c.CategoryName,
    s.Id, s.ServiceName, s.MonitorType, s.Domain,
    ss.LastCheckTime, ss.LastStatus, ss.ConsecutiveFailCount,
    ss.LastErrorMessage, ss.LastResponseTimeMs
FROM Monitor_Service s
JOIN Monitor_Category c ON s.CategoryId = c.Id
LEFT JOIN Monitor_ServiceStatus ss ON s.Id = ss.ServiceId
ORDER BY c.Id, s.Id
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def login_required(view):
    """Decorator that redirects unauthenticated users to the login page."""
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def get_db_connection():
    """Return a new pymssql connection using DB_CONFIG."""
    return pymssql.connect(**DB_CONFIG)


def fetch_dashboard_data():
    """Query the database and return structured dashboard data.

    Returns a dict:
        {
            "categories": { "CategoryName": [ {service_dict}, ... ], ... },
            "total": int,
            "ok": int,
            "fail": int,
            "updated_at": str,
        }
    """
    categories: dict[str, list] = {}
    total = ok_count = fail_count = 0

    try:
        conn = get_db_connection()
        cursor = conn.cursor(as_dict=True)
        cursor.execute(DASHBOARD_SQL)
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            cat = row["CategoryName"] or "Uncategorized"
            if cat not in categories:
                categories[cat] = []

            status = row["LastStatus"]
            if status is not None:
                status = status.strip() if isinstance(status, str) else str(status)

            last_check = row["LastCheckTime"]
            if last_check:
                last_check = last_check.strftime("%Y-%m-%d %H:%M:%S")

            resp_time = row["LastResponseTimeMs"]
            if resp_time is not None:
                resp_time = int(resp_time)

            consec_fail = row["ConsecutiveFailCount"]
            if consec_fail is not None:
                consec_fail = int(consec_fail)

            service = {
                "id":                   row["Id"],
                "service_name":         row["ServiceName"],
                "monitor_type":         row["MonitorType"],
                "domain":               row["Domain"],
                "last_check_time":      last_check,
                "last_status":          status,
                "consecutive_fail":     consec_fail,
                "last_error":           row["LastErrorMessage"],
                "response_time_ms":     resp_time,
            }

            categories[cat].append(service)
            total += 1
            if status and status.upper() == "OK":
                ok_count += 1
            elif status and status.upper() == "FAIL":
                fail_count += 1

    except Exception as exc:
        # On DB failure, return empty data with an error flag
        return {
            "categories": {},
            "total": 0,
            "ok": 0,
            "fail": 0,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": str(exc),
        }

    return {
        "categories": categories,
        "total": total,
        "ok": ok_count,
        "fail": fail_count,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USER and password == ADMIN_PASS:
            session["logged_in"] = True
            session.permanent = True
            return redirect(url_for("dashboard"))
        flash("帳號或密碼錯誤", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    data = fetch_dashboard_data()
    return render_template("dashboard.html", data=data)


@app.route("/api/dashboard")
@login_required
def api_dashboard():
    """JSON endpoint for AJAX auto-refresh."""
    data = fetch_dashboard_data()
    return jsonify(data)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=False)
