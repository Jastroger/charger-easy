from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class WebConfig:
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8080
    title: str = "Juice Charger Easy"


class WebDashboardServer:
    def __init__(self, runtime: Any, config: WebConfig, logger: Any) -> None:
        self.runtime = runtime
        self.config = config
        self.logger = logger
        handler = self._handler_factory()
        self.httpd = ThreadingHTTPServer((config.host, config.port), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="charger-easy-web", daemon=True)

    @property
    def url(self) -> str:
        host, port = self.httpd.server_address[:2]
        display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
        return f"http://{display_host}:{port}/"

    def start(self) -> None:
        self.thread.start()
        self.logger.info("Webansicht gestartet: %s", self.url)

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def _handler_factory(self):
        runtime = self.runtime
        title = self.config.title
        logger = self.logger

        class Handler(BaseHTTPRequestHandler):
            server_version = "ChargerEasyWeb/1.0"

            def do_GET(self) -> None:
                path = urlparse(self.path).path
                if path in {"/", "/index.html"}:
                    self._send_text(HTTPStatus.OK, render_dashboard(title), "text/html; charset=utf-8")
                    return
                if path == "/api/state":
                    self._send_json(HTTPStatus.OK, runtime.get_web_state())
                    return
                if path == "/health":
                    self._send_json(HTTPStatus.OK, {"status": "ok"})
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

            def do_POST(self) -> None:
                path = urlparse(self.path).path
                body = self._read_json_body()
                if body is None:
                    return

                if path == "/api/mode":
                    mode = str(body.get("mode", "")).strip().lower()
                    if not runtime.set_mode(mode, source="web"):
                        self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_mode"})
                        return
                    self._send_json(HTTPStatus.OK, runtime.get_web_state())
                    return

                if path == "/api/instant-current":
                    if "current" not in body:
                        self._send_json(HTTPStatus.BAD_REQUEST, {"error": "missing_current"})
                        return
                    if not runtime.set_instant_current(body["current"], source="web"):
                        self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_current"})
                        return
                    self._send_json(HTTPStatus.OK, runtime.get_web_state())
                    return

                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

            def log_message(self, fmt: str, *args: Any) -> None:
                logger.debug("Web: " + fmt, *args)

            def _read_json_body(self) -> dict[str, Any] | None:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_content_length"})
                    return None
                if length > 8192:
                    self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "body_too_large"})
                    return None
                raw_body = self.rfile.read(length).decode("utf-8") if length else "{}"
                try:
                    body = json.loads(raw_body)
                except json.JSONDecodeError:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
                    return None
                if not isinstance(body, dict):
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "json_object_required"})
                    return None
                return body

            def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
                self._send_text(status, json.dumps(payload), "application/json; charset=utf-8")

            def _send_text(self, status: HTTPStatus, body: str, content_type: str) -> None:
                encoded = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(encoded)

        return Handler


def render_dashboard(title: str) -> str:
    return f"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #eef3f7;
      --panel: #ffffff;
      --ink: #16202a;
      --muted: #667586;
      --line: #d7e0e8;
      --green: #1f9d66;
      --blue: #246bfe;
      --amber: #c47a12;
      --red: #d33d3d;
      --shadow: 0 18px 42px rgba(21, 37, 56, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: linear-gradient(180deg, #dcebf5 0%, var(--bg) 42%, #f8fbfd 100%);
      color: var(--ink);
    }}
    main {{
      width: min(1160px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 36px;
    }}
    header {{
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 22px;
    }}
    h1 {{
      margin: 0;
      font-size: 48px;
      line-height: 0.95;
      letter-spacing: 0;
    }}
    .subline {{
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 15px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 9px;
      min-height: 38px;
      padding: 8px 12px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.78);
      font-weight: 700;
      white-space: nowrap;
    }}
    .dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--muted);
      box-shadow: 0 0 0 4px rgba(102, 117, 134, 0.14);
    }}
    .dot.on {{ background: var(--green); box-shadow: 0 0 0 4px rgba(31, 157, 102, 0.16); }}
    .dot.warn {{ background: var(--amber); box-shadow: 0 0 0 4px rgba(196, 122, 18, 0.16); }}
    .layout {{
      display: grid;
      grid-template-columns: 1fr 360px;
      gap: 16px;
    }}
    section, .card {{
      background: rgba(255, 255, 255, 0.9);
      border: 1px solid rgba(215, 224, 232, 0.9);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    section {{
      padding: 18px;
    }}
    .hero {{
      min-height: 278px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      overflow: hidden;
      position: relative;
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.94), rgba(241, 247, 251, 0.94));
    }}
    .current {{
      display: flex;
      align-items: baseline;
      gap: 10px;
      margin-top: 14px;
    }}
    .current strong {{
      font-size: 132px;
      line-height: 0.88;
      letter-spacing: 0;
    }}
    .current span {{
      font-size: 28px;
      color: var(--muted);
      font-weight: 800;
    }}
    .reason {{
      color: var(--muted);
      font-size: 15px;
      max-width: 620px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 16px;
    }}
    .card {{
      padding: 14px;
      min-height: 92px;
      box-shadow: none;
    }}
    .label {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
    }}
    .value {{
      margin-top: 9px;
      font-size: 27px;
      font-weight: 850;
      line-height: 1.05;
      overflow-wrap: anywhere;
    }}
    .small {{
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
    }}
    .controls {{
      display: grid;
      gap: 14px;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 18px;
      letter-spacing: 0;
    }}
    .segments {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
    }}
    button {{
      min-height: 42px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f8fbfd;
      color: var(--ink);
      font-weight: 850;
      cursor: pointer;
    }}
    button.active {{
      color: white;
      border-color: var(--blue);
      background: var(--blue);
      box-shadow: 0 10px 26px rgba(36, 107, 254, 0.24);
    }}
    button:disabled {{
      cursor: not-allowed;
      opacity: 0.6;
    }}
    .slider-row {{
      display: grid;
      grid-template-columns: 1fr 76px;
      gap: 12px;
      align-items: center;
    }}
    input[type="range"] {{
      width: 100%;
      accent-color: var(--blue);
    }}
    input[type="number"] {{
      width: 76px;
      height: 42px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      font: inherit;
      font-weight: 800;
      text-align: right;
    }}
    .status-list {{
      display: grid;
      gap: 10px;
    }}
    .row {{
      display: flex;
      justify-content: space-between;
      gap: 14px;
      padding: 9px 0;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
    }}
    .row:last-child {{ border-bottom: 0; }}
    .row strong {{
      color: var(--ink);
      text-align: right;
      overflow-wrap: anywhere;
    }}
    .error {{
      display: none;
      margin-top: 14px;
      color: var(--red);
      font-weight: 800;
    }}
    @media (max-width: 900px) {{
      header {{ align-items: flex-start; flex-direction: column; }}
      .layout {{ grid-template-columns: 1fr; }}
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      h1 {{ font-size: 40px; }}
      .current strong {{ font-size: 110px; }}
    }}
    @media (max-width: 520px) {{
      main {{ width: min(100% - 20px, 1160px); padding-top: 18px; }}
      section {{ padding: 14px; }}
      .grid {{ grid-template-columns: 1fr; }}
      .segments {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 32px; }}
      .current strong {{ font-size: 86px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>{title}</h1>
        <p class="subline">Live-Status, PV-Modus und Sofortladestrom</p>
      </div>
      <div class="pill"><span id="liveDot" class="dot"></span><span id="liveText">Verbinde...</span></div>
    </header>

    <div class="layout">
      <div>
        <section class="hero">
          <div>
            <div class="label">Effektiver Ladestrom</div>
            <div class="current"><strong id="effectiveCurrent">--</strong><span>A</span></div>
            <div id="reason" class="reason">Noch kein Status empfangen.</div>
          </div>
          <div class="grid">
            <div class="card"><div class="label">Modus</div><div id="mode" class="value">--</div></div>
            <div class="card"><div class="label">PV-Ueberschuss</div><div id="surplus" class="value">--</div><div class="small">W</div></div>
            <div class="card"><div class="label">Netzleistung</div><div id="gridPower" class="value">--</div><div class="small">W</div></div>
            <div class="card"><div class="label">Zielstrom</div><div id="targetCurrent" class="value">--</div><div class="small">A</div></div>
          </div>
        </section>

        <div class="grid">
          <div class="card"><div class="label">CP-State</div><div id="cpState" class="value">--</div></div>
          <div class="card"><div class="label">Hardware-Max</div><div id="hwMax" class="value">--</div><div class="small">A</div></div>
          <div class="card"><div class="label">RLC</div><div id="rlc" class="value">--</div><div class="small">%</div></div>
          <div class="card"><div class="label">Override</div><div id="override" class="value">--</div></div>
        </div>
      </div>

      <div class="controls">
        <section>
          <h2>Modus</h2>
          <div class="segments">
            <button data-mode="off">Aus</button>
            <button data-mode="pv">PV</button>
            <button data-mode="instant">Sofort</button>
          </div>
        </section>

        <section>
          <h2>Sofortladestrom</h2>
          <div class="slider-row">
            <input id="currentSlider" type="range" min="0" max="32" step="1" value="6">
            <input id="currentInput" type="number" min="0" max="32" step="1" value="6">
          </div>
          <div class="small">Wird im Modus Sofort verwendet. Hardware- und RLC-Limits bleiben aktiv.</div>
        </section>

        <section>
          <h2>Details</h2>
          <div class="status-list">
            <div class="row"><span>Fahrzeug</span><strong id="vehicle">--</strong></div>
            <div class="row"><span>Laedt</span><strong id="charging">--</strong></div>
            <div class="row"><span>PV-Daten</span><strong id="pvFresh">--</strong></div>
            <div class="row"><span>Letzter Status</span><strong id="timestamp">--</strong></div>
          </div>
          <div id="error" class="error"></div>
        </section>
      </div>
    </div>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    const buttons = [...document.querySelectorAll("[data-mode]")];
    const slider = $("currentSlider");
    const input = $("currentInput");
    const error = $("error");
    let pendingCurrent = null;

    function fmt(value, digits = 0) {{
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
      return Number(value).toFixed(digits);
    }}

    function yesNo(value) {{
      return value ? "Ja" : "Nein";
    }}

    function showError(message) {{
      error.textContent = message || "";
      error.style.display = message ? "block" : "none";
    }}

    async function postJson(path, payload) {{
      showError("");
      const response = await fetch(path, {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(payload)
      }});
      if (!response.ok) throw new Error("Befehl wurde nicht angenommen");
      return response.json();
    }}

    async function setMode(mode) {{
      buttons.forEach((button) => button.disabled = true);
      try {{
        await postJson("/api/mode", {{ mode }});
        await refresh();
      }} catch (err) {{
        showError(err.message);
      }} finally {{
        buttons.forEach((button) => button.disabled = false);
      }}
    }}

    async function setCurrent(value) {{
      pendingCurrent = value;
      try {{
        await postJson("/api/instant-current", {{ current: value }});
        await refresh();
      }} catch (err) {{
        showError(err.message);
      }} finally {{
        pendingCurrent = null;
      }}
    }}

    function updateUi(state) {{
      const charging = Boolean(state.is_charging);
      const stale = Boolean(state.pv_input_stale);
      $("liveDot").className = "dot " + (charging ? "on" : stale ? "warn" : "");
      $("liveText").textContent = charging ? "Laedt" : stale ? "PV-Daten warten" : "Online";
      $("effectiveCurrent").textContent = fmt(state.effective_current_A, 1);
      $("reason").textContent = state.limit_reason || "none";
      $("mode").textContent = state.effective_mode || state.mode || "--";
      $("surplus").textContent = fmt(state.pv_surplus_w, 0);
      $("gridPower").textContent = fmt(state.grid_power_w, 0);
      $("targetCurrent").textContent = fmt(state.target_current_A, 1);
      $("cpState").textContent = state.cp_state || "--";
      $("hwMax").textContent = fmt(state.hw_max_current, 0);
      $("rlc").textContent = fmt(state.rlc_percentage, 0);
      $("override").textContent = yesNo(state.hardware_override_free_charge);
      $("vehicle").textContent = state.vehicle_connected ? "Verbunden" : "Nicht verbunden";
      $("charging").textContent = yesNo(state.is_charging);
      $("pvFresh").textContent = state.pv_input_stale ? "Veraltet" : "Aktuell";
      $("timestamp").textContent = state.timestamp || "--";

      buttons.forEach((button) => button.classList.toggle("active", button.dataset.mode === state.mode));
      if (pendingCurrent === null) {{
        const current = Math.round(Number(state.instant_current_A ?? 6));
        slider.value = current;
        input.value = current;
      }}
    }}

    async function refresh() {{
      try {{
        const response = await fetch("/api/state", {{ cache: "no-store" }});
        if (!response.ok) throw new Error("Status nicht erreichbar");
        updateUi(await response.json());
        showError("");
      }} catch (err) {{
        $("liveDot").className = "dot warn";
        $("liveText").textContent = "Offline";
        showError(err.message);
      }}
    }}

    buttons.forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
    slider.addEventListener("input", () => input.value = slider.value);
    slider.addEventListener("change", () => setCurrent(Number(slider.value)));
    input.addEventListener("change", () => {{
      const value = Math.max(0, Math.min(32, Number(input.value || 0)));
      input.value = value;
      slider.value = value;
      setCurrent(value);
    }});

    refresh();
    setInterval(refresh, 2000);
  </script>
</body>
</html>"""
