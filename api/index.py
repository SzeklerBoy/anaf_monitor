import json
from flask import Flask, jsonify, render_template_string
from dataclasses import dataclass
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
import requests

app = Flask(__name__)


@dataclass
class EndpointResult:
    id:     str
    name:   str
    url:    str
    status: str            # "Online" | "Offline"
    code:   Optional[int]  # HTTP status code if a response was received, else None
    reason: Optional[str]  # "Timeout" | "Connection Error" | str(code) | None

    def to_dict(self) -> dict:
        return {
            "id":     self.id,
            "name":   self.name,
            "url":    self.url,
            "status": self.status,
            "code":   self.code,
            "reason": self.reason,
        }


ENDPOINTS = [
    {"id": "xml_test",     "name": "XML test validation",
     "url": "https://www.anaf.ro/uploadxmi/"},
    {"id": "xml_test_pdf", "name": "XML to PDF test",
     "url": "https://www.anaf.ro/uploadxml/"},
    {"id": "oauth2_token",   "name": "SPV login",
     "url": "https://pfinternet.anaf.ro/my.policy"},
    {"id": "efactura_login", "name": "User registration ",
     "url": "https://www.anaf.ro/anaf/internet/ANAF/servicii_online/inregistrare_utilizatori"},
]


def check_endpoint(endpoint: dict) -> EndpointResult:
    """Issue one GET, apply classification rules, return EndpointResult."""
    url = endpoint["url"]
    try:
        resp = requests.get(url, timeout=2)
        code = resp.status_code
        if code == 404 or code >= 500:
            return EndpointResult(
                id=endpoint["id"],
                name=endpoint["name"],
                url=url,
                status="Offline",
                code=code,
                reason=str(code),
            )
        else:  # 100–499 excluding 404
            return EndpointResult(
                id=endpoint["id"],
                name=endpoint["name"],
                url=url,
                status="Online",
                code=code,
                reason=None,
            )
    except requests.Timeout:
        return EndpointResult(
            id=endpoint["id"],
            name=endpoint["name"],
            url=url,
            status="Offline",
            code=None,
            reason="Timeout",
        )
    except requests.RequestException:
        return EndpointResult(
            id=endpoint["id"],
            name=endpoint["name"],
            url=url,
            status="Offline",
            code=None,
            reason="Connection Error",
        )


def check_all_endpoints() -> list[EndpointResult]:
    """Run check_endpoint for all ENDPOINTS concurrently via ThreadPoolExecutor."""
    with ThreadPoolExecutor(max_workers=4) as executor:
        return list(executor.map(check_endpoint, ENDPOINTS))


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>ANAF Status Monitor</title>
  <style>
    *, *::before, *::after {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      background-color: #121212;
      color: #e0e0e0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                   Helvetica, Arial, sans-serif;
      min-height: 100vh;
      padding: 2rem 1rem;
    }

    header {
      text-align: center;
      margin-bottom: 2rem;
    }

    header h1 {
      font-size: 1.75rem;
      font-weight: 700;
      color: #ffffff;
      letter-spacing: 0.03em;
    }

    header p {
      margin-top: 0.4rem;
      font-size: 0.9rem;
      color: #9e9e9e;
    }

    /* ---------- notification button ---------- */
    #notif-btn {
      display: inline-block;
      margin-top: 1rem;
      padding: 0.45rem 1.1rem;
      background-color: #1e88e5;
      color: #ffffff;
      border: none;
      border-radius: 6px;
      font-size: 0.875rem;
      cursor: pointer;
      transition: background-color 0.2s ease;
    }

    #notif-btn:hover {
      background-color: #1565c0;
    }

    #notif-btn.hidden {
      display: none;
    }

    /* ---------- error indicator ---------- */
    #refresh-error {
      display: none;
      margin: 0 auto 1.5rem;
      max-width: 480px;
      padding: 0.6rem 1rem;
      background-color: #b71c1c;
      color: #ffcdd2;
      border-radius: 6px;
      font-size: 0.875rem;
      text-align: center;
    }

    #refresh-error.visible {
      display: block;
    }

    /* ---------- cards grid ---------- */
    #grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 1.25rem;
      max-width: 1200px;
      margin: 0 auto;
    }

    /* ---------- individual card ---------- */
    .card {
      background-color: #1e1e1e;
      border-radius: 10px;
      padding: 1.25rem 1.5rem 1rem;
      border-top: 4px solid transparent;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.45);
    }

    .card.online {
      border-top-color: #43a047;
    }

    .card.offline {
      border-top-color: #e53935;
    }

    .card-name {
      font-size: 1rem;
      font-weight: 600;
      color: #ffffff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .card-status {
      font-size: 1.1rem;
      font-weight: 700;
    }

    .card.online  .card-status { color: #66bb6a; }
    .card.offline .card-status { color: #ef5350; }

    .card-detail {
      font-size: 0.82rem;
      color: #757575;
    }

    .card-timestamp {
      font-size: 0.78rem;
      color: #616161;
      margin-top: 0.25rem;
    }

    /* ---------- footer timestamp ---------- */
    #timestamp-wrap {
      text-align: center;
      margin-top: 2.5rem;
      font-size: 0.85rem;
      color: #616161;
    }

    #timestamp {
      font-weight: 600;
      color: #9e9e9e;
    }
  </style>
</head>
<body>

  <header>
    <h1>🇷🇴 ANAF Status Monitor</h1>
    <p>Real-time availability of ANAF developer APIs</p>
    <button id="notif-btn" class="hidden" aria-label="Enable push notifications">
      🔔 Enable Notifications
    </button>
  </header>

  <div id="refresh-error" role="alert">
    ⚠️ Auto-refresh failed — showing last known data.
  </div>

  <div id="grid" aria-label="Service status cards"></div>

  <div id="timestamp-wrap">
    Last updated: <span id="timestamp">—</span>
  </div>

  <!-- Server-injected initial data -->
  <script>window.__INITIAL_DATA__ = {{ data | safe }};</script>

  <script>
    function cardHTML(ep) {
      const isOnline = ep.status === 'Online';
      const statusText = isOnline ? '✅ ONLINE' : '❌ OFFLINE';
      const borderClass = isOnline ? 'online' : 'offline';
      let detailHTML = '';
      if (isOnline && ep.code != null) {
        detailHTML = `<div class="card-detail">HTTP ${ep.code}</div>`;
      } else if (!isOnline && ep.reason) {
        detailHTML = `<div class="card-detail">${ep.reason}</div>`;
      }
      return `
        <div class="card ${borderClass}">
          <div class="card-name">${ep.name}</div>
          <div class="card-status">${statusText}</div>
          ${detailHTML}
        </div>`;
    }

    function renderCards(data) {
      const grid = document.getElementById('grid');
      if (!grid || !Array.isArray(data)) return;
      grid.innerHTML = data.map(ep => cardHTML(ep)).join('');
      document.getElementById('timestamp').textContent =
        new Date().toLocaleString();
    }

    const Notification_Manager = {
      STORAGE_KEY: 'anaf_status_v1',

      loadPrev() {
        try {
          const raw = localStorage.getItem(this.STORAGE_KEY);
          return raw ? JSON.parse(raw) : {};
        } catch (_) {
          return {};
        }
      },

      saveCurrent(data) {
        try {
          const map = {};
          for (const ep of data) { map[ep.id] = ep.status; }
          localStorage.setItem(this.STORAGE_KEY, JSON.stringify(map));
        } catch (_) { /* storage unavailable */ }
      },

      evaluate(data) {
        if (Notification.permission !== 'granted') return;
        const prev = this.loadPrev();
        for (const ep of data) {
          const prevStatus = prev[ep.id];
          if (prevStatus === undefined) continue; // first load: no notification
          if (prevStatus === ep.status) continue; // unchanged: no notification
          if (ep.status === 'Offline') {
            new Notification('❌ ANAF Outage!', {
              body: `${ep.name} is down (${ep.reason}).`
            });
          } else {
            new Notification('✅ ANAF is Back!', {
              body: `${ep.name} is accessible again.`
            });
          }
        }
        this.saveCurrent(data);
      },

      requestPermission() {
        Notification.requestPermission().then(() => this.syncUI());
      },

      syncUI() {
        const btn = document.getElementById('notif-btn');
        if (!btn) return;
        if (Notification.permission === 'default') {
          btn.classList.remove('hidden');
        } else {
          btn.classList.add('hidden');
        }
      },
    };

    function showRefreshError() {
      const el = document.getElementById('refresh-error');
      if (el) el.classList.add('visible');
    }

    function hideRefreshError() {
      const el = document.getElementById('refresh-error');
      if (el) el.classList.remove('visible');
    }

    async function refresh() {
      try {
        const res = await fetch('/api/status');
        if (!res.ok) throw new Error('non-2xx response');
        const data = await res.json();
        hideRefreshError();
        Notification_Manager.evaluate(data);
        renderCards(data);
      } catch (e) {
        showRefreshError();
      } finally {
        setTimeout(refresh, 60_000);
      }
    }

    renderCards(window.__INITIAL_DATA__);
    Notification_Manager.evaluate(window.__INITIAL_DATA__);
    setTimeout(refresh, 60_000);

    document.addEventListener('DOMContentLoaded', function() {
      Notification_Manager.syncUI();
      const btn = document.getElementById('notif-btn');
      if (btn) {
        btn.addEventListener('click', function() {
          Notification_Manager.requestPermission();
        });
      }
    });
  </script>

</body>
</html>"""


@app.route("/api/status")
def status():
    results = check_all_endpoints()
    return jsonify([r.to_dict() for r in results])


@app.route("/")
def index():
    results = check_all_endpoints()
    json_payload = json.dumps([r.to_dict() for r in results])
    return render_template_string(HTML_TEMPLATE, data=json_payload)
