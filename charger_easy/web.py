from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from html import escape
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
    return DASHBOARD_TEMPLATE.replace("__TITLE__", escape(title))


DASHBOARD_TEMPLATE = """<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <style>
    :root {
      color-scheme: light;
      --page: #dfe5e8;
      --screen: #11181d;
      --screen-soft: #16242b;
      --surface: #f4f7f7;
      --surface-strong: #ffffff;
      --ink: #f7fbfb;
      --ink-dark: #0f171b;
      --muted: #8ba0a7;
      --muted-dark: #607178;
      --line: rgba(255, 255, 255, 0.12);
      --line-dark: #cfd9dd;
      --green: #20d49b;
      --green-dark: #0e8c67;
      --blue: #2c6ee8;
      --yellow: #f4bd50;
      --red: #e45b5b;
      --shadow: 0 22px 52px rgba(8, 14, 18, 0.26);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        linear-gradient(180deg, #f6f8f9 0, var(--page) 58%, #cfd8dc 100%);
      color: var(--ink);
      -webkit-tap-highlight-color: transparent;
    }
    button, input { font: inherit; }
    input {
      user-select: text;
      -webkit-user-select: text;
    }
    main {
      width: min(1240px, calc(100% - 28px));
      margin: 0 auto;
      padding: 18px 0 30px;
    }
    .kiosk {
      min-height: calc(100vh - 48px);
      border: 1px solid rgba(10, 20, 24, 0.24);
      border-radius: 8px;
      background: #20272b;
      box-shadow: var(--shadow);
      padding: 14px;
    }
    .screen {
      min-height: calc(100vh - 78px);
      border-radius: 6px;
      background: var(--screen);
      overflow: hidden;
      position: relative;
      user-select: none;
      -webkit-user-select: none;
    }
    .screen::before {
      content: "";
      position: absolute;
      inset: 0;
      pointer-events: none;
      background:
        linear-gradient(90deg, rgba(255,255,255,0.04), transparent 18%, transparent 82%, rgba(255,255,255,0.035)),
        linear-gradient(180deg, rgba(255,255,255,0.08), transparent 210px);
    }
    .screen-inner {
      position: relative;
      z-index: 1;
      display: grid;
      grid-template-rows: auto 1fr auto;
      min-height: calc(100vh - 78px);
      padding: 22px;
      gap: 16px;
    }
    .topbar {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 18px;
      align-items: center;
    }
    h1 {
      margin: 0;
      font-size: clamp(30px, 4vw, 54px);
      line-height: 0.95;
      letter-spacing: 0;
    }
    .subline {
      margin: 8px 0 0;
      color: var(--muted);
      font-size: clamp(15px, 1.4vw, 19px);
    }
    .status-chip {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 11px;
      min-height: 48px;
      min-width: 142px;
      padding: 10px 15px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.07);
      color: var(--ink);
      font-weight: 900;
      white-space: nowrap;
    }
    .dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: var(--muted);
      box-shadow: 0 0 0 6px rgba(139, 160, 167, 0.18);
    }
    .dot.on { background: var(--green); box-shadow: 0 0 0 6px rgba(32, 212, 155, 0.18); }
    .dot.warn { background: var(--yellow); box-shadow: 0 0 0 6px rgba(244, 189, 80, 0.18); }
    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 326px;
      gap: 16px;
      min-height: 0;
    }
    .stage-panel, .control-panel, .data-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.055);
      backdrop-filter: blur(10px);
    }
    .stage-panel {
      display: grid;
      grid-template-rows: auto minmax(310px, 1fr) auto;
      gap: 16px;
      min-width: 0;
      padding: 20px;
    }
    .headline {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 16px;
      align-items: start;
    }
    .eyebrow {
      color: var(--green);
      font-size: 13px;
      font-weight: 950;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .status-title {
      margin: 8px 0 0;
      color: var(--ink);
      font-size: clamp(31px, 3.6vw, 50px);
      line-height: 1.02;
      letter-spacing: 0;
    }
    .status-copy {
      margin: 10px 0 0;
      max-width: 690px;
      color: #b5c4c9;
      font-size: clamp(16px, 1.6vw, 20px);
      line-height: 1.38;
    }
    .mode-badge {
      min-width: 140px;
      padding: 12px 14px;
      border-radius: 8px;
      border: 1px solid rgba(32, 212, 155, 0.28);
      background: rgba(32, 212, 155, 0.12);
      color: var(--green);
      text-align: center;
      font-size: 17px;
      font-weight: 950;
    }
    .status-rail {
      display: grid;
      gap: 10px;
      justify-items: end;
      align-content: start;
    }
    .override-notice {
      width: min(270px, 100%);
      padding: 11px 13px;
      border-radius: 8px;
      border: 1px solid rgba(244, 189, 80, 0.42);
      background: rgba(244, 189, 80, 0.13);
      color: #f6d78a;
      font-size: 13px;
      font-weight: 800;
      line-height: 1.3;
    }
    .override-notice[hidden] {
      display: none;
    }
    .override-notice strong {
      display: block;
      margin-bottom: 4px;
      color: var(--yellow);
      font-size: 14px;
      line-height: 1.2;
    }
    .visual {
      display: grid;
      grid-template-columns: minmax(300px, 0.76fr) minmax(400px, 1.24fr);
      gap: 16px;
      align-items: stretch;
      min-height: 0;
    }
    .readout {
      display: grid;
      align-content: center;
      min-width: 0;
      overflow: hidden;
      padding: 20px 18px;
      border-radius: 8px;
      background: var(--surface);
      color: var(--ink-dark);
    }
    .readout-label {
      color: var(--muted-dark);
      font-size: 13px;
      font-weight: 900;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .amp {
      display: flex;
      align-items: baseline;
      gap: 8px;
      margin-top: 16px;
      min-width: 0;
      white-space: nowrap;
    }
    .amp strong {
      min-width: 0;
      font-size: clamp(82px, 9.2vw, 126px);
      line-height: 0.84;
      letter-spacing: 0;
      font-variant-numeric: tabular-nums;
    }
    .amp span {
      color: var(--muted-dark);
      font-size: clamp(24px, 2.4vw, 36px);
      font-weight: 950;
    }
    .current-subline {
      margin-top: 14px;
      color: var(--muted-dark);
      font-size: 18px;
      line-height: 1.35;
    }
    .charge-bar {
      margin-top: 24px;
    }
    .bar-head {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      color: var(--muted-dark);
      font-size: 14px;
      font-weight: 900;
      margin-bottom: 10px;
    }
    .track {
      height: 18px;
      overflow: hidden;
      border-radius: 999px;
      background: #d5dee2;
      border: 1px solid #c6d0d5;
    }
    .fill {
      width: 0%;
      height: 100%;
      border-radius: 999px;
      background: var(--green-dark);
      transition: width 240ms ease;
    }
    .diagram-card {
      position: relative;
      min-height: 320px;
      border-radius: 8px;
      background: #e7edef;
      color: var(--ink-dark);
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, 0.18);
      user-select: none;
      -webkit-user-select: none;
    }
    .diagram-card::before {
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(180deg, rgba(255,255,255,0.7), rgba(255,255,255,0.1)),
        repeating-linear-gradient(0deg, rgba(15, 23, 27, 0.04), rgba(15, 23, 27, 0.04) 1px, transparent 1px, transparent 38px),
        repeating-linear-gradient(90deg, rgba(15, 23, 27, 0.035), rgba(15, 23, 27, 0.035) 1px, transparent 1px, transparent 38px);
    }
    .diagram {
      position: relative;
      z-index: 1;
      width: 100%;
      height: 100%;
      min-height: 320px;
      display: block;
      pointer-events: none;
    }
    .svg-label {
      font: 800 15px Inter, system-ui, sans-serif;
      fill: #24333a;
    }
    .svg-small {
      font: 700 12px Inter, system-ui, sans-serif;
      fill: #6a7b82;
    }
    .svg-pill {
      fill: rgba(255, 255, 255, 0.78);
      stroke: #d6e0e4;
      stroke-width: 1;
    }
    .flow-line {
      fill: none;
      stroke: #8da0a8;
      stroke-width: 8;
      stroke-linecap: round;
      stroke-dasharray: 1 18;
    }
    .flow-line.active {
      stroke: var(--green-dark);
      stroke-dasharray: 18 14;
      animation: flow 1.3s linear infinite;
    }
    .flow-line.grid-import.active { stroke: var(--yellow); }
    .flow-line.paused { stroke: #9eaeb5; }
    .cable-base {
      fill: none;
      stroke: #1b2b32;
      stroke-width: 9;
      stroke-linecap: round;
      stroke-linejoin: round;
    }
    .cable-flow {
      fill: none;
      stroke: transparent;
      stroke-width: 4;
      stroke-linecap: round;
      stroke-linejoin: round;
      stroke-dasharray: 1 16;
    }
    .cable-flow.active {
      stroke: var(--green);
      stroke-dasharray: 14 12;
      animation: flow 1.1s linear infinite;
    }
    .node {
      fill: #ffffff;
      stroke: #c4d0d6;
      stroke-width: 2;
    }
    .node.dark { fill: #142126; stroke: #142126; }
    .node.green { fill: var(--green); stroke: var(--green-dark); }
    .car-icon {
      fill: none;
      stroke: #26383f;
      stroke-width: 5;
      stroke-linecap: round;
      stroke-linejoin: round;
    }
    .car-icon path {
      vector-effect: non-scaling-stroke;
    }
    .car-shadow {
      fill: none;
      stroke: rgba(38, 56, 63, 0.1);
      stroke-width: 18;
      stroke-linecap: round;
      vector-effect: non-scaling-stroke;
    }
    .charge-port {
      fill: var(--green);
      stroke: var(--green-dark);
      stroke-width: 2;
    }
    @keyframes flow {
      to { stroke-dashoffset: -32; }
    }
    .facts {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }
    .fact {
      min-height: 76px;
      padding: 13px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.06);
    }
    .fact .label, .data-card .label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 950;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }
    .fact strong {
      display: block;
      margin-top: 8px;
      color: var(--ink);
      font-size: 23px;
      line-height: 1.08;
      overflow-wrap: anywhere;
    }
    .control-panel {
      align-self: stretch;
      padding: 16px;
      background: #f7faf9;
      color: var(--ink-dark);
    }
    .control-panel h2 {
      margin: 0 0 14px;
      font-size: 24px;
      line-height: 1.1;
      letter-spacing: 0;
    }
    .mode-buttons {
      display: grid;
      gap: 10px;
    }
    .mode-button {
      min-height: 74px;
      display: grid;
      grid-template-columns: 46px 1fr;
      gap: 13px;
      align-items: center;
      width: 100%;
      border: 1px solid var(--line-dark);
      border-radius: 8px;
      background: #ffffff;
      color: var(--ink-dark);
      cursor: pointer;
      text-align: left;
      padding: 12px;
      user-select: none;
      -webkit-user-select: none;
      touch-action: manipulation;
      transition: transform 140ms ease, background 140ms ease, border-color 140ms ease, color 140ms ease;
    }
    .mode-button:hover {
      transform: translateY(-1px);
      border-color: #aebdc4;
    }
    .mode-button .icon {
      display: grid;
      place-items: center;
      width: 46px;
      height: 46px;
      border-radius: 8px;
      background: #e8eef1;
      color: #43535a;
      font-weight: 950;
    }
    .mode-button strong {
      display: block;
      font-size: 17px;
      line-height: 1.08;
    }
    .mode-button .text {
      display: block;
      min-width: 0;
    }
    .mode-button .desc {
      display: block;
      margin-top: 5px;
      color: var(--muted-dark);
      font-size: 13px;
      font-weight: 750;
      line-height: 1.28;
    }
    .mode-button.active {
      background: #123129;
      border-color: #123129;
      color: #ffffff;
      box-shadow: 0 12px 24px rgba(18, 49, 41, 0.2);
    }
    .mode-button.active .icon {
      background: var(--green);
      color: #06261b;
    }
    .mode-button.active .desc { color: rgba(255, 255, 255, 0.76); }
    .mode-button:disabled {
      cursor: not-allowed;
      opacity: 0.62;
      transform: none;
    }
    .current-control {
      margin-top: 18px;
      padding-top: 18px;
      border-top: 1px solid var(--line-dark);
    }
    .current-control label {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      color: var(--muted-dark);
      font-weight: 900;
      margin-bottom: 12px;
    }
    .current-control label strong {
      color: var(--ink-dark);
      font-size: 24px;
      font-variant-numeric: tabular-nums;
    }
    .slider-row {
      display: grid;
      grid-template-columns: 1fr 82px;
      gap: 12px;
      align-items: center;
    }
    input[type="range"] {
      width: 100%;
      accent-color: var(--green-dark);
    }
    input[type="number"] {
      width: 82px;
      height: 48px;
      border: 1px solid var(--line-dark);
      border-radius: 8px;
      padding: 8px;
      background: #ffffff;
      color: var(--ink-dark);
      font-weight: 900;
      text-align: right;
    }
    .hint {
      margin-top: 12px;
      color: var(--muted-dark);
      font-size: 14px;
      line-height: 1.35;
    }
    .error {
      display: none;
      margin-top: 14px;
      padding: 10px 12px;
      border: 1px solid rgba(228, 91, 91, 0.32);
      border-radius: 8px;
      background: #fff0f0;
      color: #b32626;
      font-weight: 900;
    }
    .data-grid {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
    }
    .data-card {
      min-height: 78px;
      padding: 12px;
      background: rgba(255, 255, 255, 0.06);
    }
    .data-card .value {
      margin-top: 7px;
      color: var(--ink);
      font-size: 22px;
      font-weight: 950;
      line-height: 1.05;
      overflow-wrap: anywhere;
      font-variant-numeric: tabular-nums;
    }
    .data-card .value.good { color: var(--green); }
    .data-card .value.warn { color: var(--yellow); }
    .unit {
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.25;
    }
    @media (max-width: 1050px) {
      .layout { grid-template-columns: 1fr; }
      .visual { grid-template-columns: 1fr; }
      .diagram-card, .diagram { min-height: 300px; }
      .control-panel { align-self: auto; }
      .data-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    }
    @media (max-width: 720px) {
      main { width: min(100% - 14px, 1240px); padding: 8px 0 18px; }
      .kiosk { padding: 8px; }
      .screen-inner { min-height: calc(100vh - 34px); padding: 14px; }
      .topbar, .headline { grid-template-columns: 1fr; }
      .status-chip, .mode-badge, .status-rail { justify-self: start; }
      .status-rail { justify-items: start; }
      .facts, .data-grid { grid-template-columns: 1fr; }
      .stage-panel { padding: 14px; }
      .control-panel { padding: 14px; }
      .slider-row { grid-template-columns: 1fr; }
      input[type="number"] { width: 100%; text-align: left; }
      .mode-button { min-height: 70px; }
    }
  </style>
</head>
<body>
  <main>
    <div class="kiosk">
      <div class="screen">
        <div class="screen-inner">
          <header class="topbar">
            <div>
              <h1>__TITLE__</h1>
              <p class="subline">AC-Ladepunkt mit PV-Überschussregelung</p>
            </div>
            <div class="status-chip"><span id="liveDot" class="dot"></span><span id="liveText">Verbinde...</span></div>
          </header>

          <div class="layout">
            <section id="hero" class="stage-panel">
              <div class="headline">
                <div>
                  <div class="eyebrow">Ladefreigabe</div>
                  <h2 id="statusTitle" class="status-title">Bereit zum Laden</h2>
                  <p id="statusCopy" class="status-copy">Die Ladesäule wartet auf den aktuellen Status.</p>
                </div>
                <div class="status-rail">
                  <div id="modeBadge" class="mode-badge">--</div>
                  <div id="hardwareOverrideNotice" class="override-notice" hidden>
                    <strong>Hardware-FreeCharge aktiv</strong>
                    <span>Der physische Schalter kann die Softwarevorgabe übersteuern.</span>
                  </div>
                </div>
              </div>

              <div class="visual">
                <div class="readout">
                  <div class="readout-label">Aktueller Ladestrom</div>
                  <div class="amp"><strong id="effectiveCurrent">--</strong><span>A</span></div>
                  <div id="currentSubline" class="current-subline">Hardware- und Sicherheitslimits bleiben aktiv.</div>
                  <div class="charge-bar">
                    <div class="bar-head"><span>Freigabe vom Maximum</span><strong id="meterPercent">--</strong></div>
                    <div class="track"><div id="meterFill" class="fill"></div></div>
                  </div>
                </div>

                <div class="diagram-card" aria-label="Energiefluss">
                  <svg class="diagram" viewBox="18 50 704 310" role="img" aria-labelledby="diagramTitle">
                    <title id="diagramTitle">Energiefluss zwischen PV, Netz, Charger und Fahrzeug</title>
                    <rect class="node" x="42" y="72" width="126" height="70" rx="8"></rect>
                    <text class="svg-label" x="105" y="103" text-anchor="middle">PV</text>
                    <text class="svg-small" x="105" y="123" text-anchor="middle">Überschuss</text>

                    <rect class="node" x="42" y="238" width="126" height="70" rx="8"></rect>
                    <text class="svg-label" x="105" y="269" text-anchor="middle">Netz</text>
                    <text class="svg-small" x="105" y="289" text-anchor="middle">Import / Export</text>

                    <path id="flowPv" class="flow-line" d="M168 107 C205 107 228 127 252 156"></path>
                    <path id="flowGrid" class="flow-line grid-import" d="M168 273 C205 273 229 250 252 228"></path>

                    <rect class="node dark" x="246" y="88" width="104" height="204" rx="8"></rect>
                    <rect x="269" y="112" width="58" height="52" rx="4" fill="#ffffff"></rect>
                    <rect x="275" y="121" width="46" height="34" rx="3" fill="#25343b"></rect>
                    <circle class="node green" cx="298" cy="202" r="21"></circle>
                    <path d="M298 188 L286 207 H298 L292 221 L312 196 H300 Z" fill="#ffffff"></path>
                    <text class="svg-label" x="298" y="330" text-anchor="middle">Ladesäule</text>

                    <!-- Car pictogram based on Tabler Icons "car" (MIT): https://tabler.io/icons/icon/car -->
                    <path class="car-shadow" d="M422 336 H676"></path>
                    <g class="car-icon" transform="translate(410 102) scale(12)">
                      <path d="M5 17a2 2 0 1 0 4 0a2 2 0 1 0 -4 0"></path>
                      <path d="M15 17a2 2 0 1 0 4 0a2 2 0 1 0 -4 0"></path>
                      <path d="M5 17h-2v-6l2 -5h9l4 5h1a2 2 0 0 1 2 2v4h-2m-4 0h-6m-6 -6h15m-6 0v-5"></path>
                    </g>
                    <circle class="charge-port" cx="438" cy="244" r="16"></circle>
                    <path class="cable-base" d="M350 202 C382 202 400 232 438 244"></path>
                    <path id="flowCable" class="cable-flow" d="M350 202 C382 202 400 232 438 244"></path>

                    <rect class="svg-pill" x="440" y="108" width="148" height="24" rx="12"></rect>
                    <text class="svg-small" x="514" y="125" text-anchor="middle">AC 230 V · 1 Phase</text>
                  </svg>
                </div>
              </div>

              <div class="facts">
                <div class="fact"><div class="label">Fahrzeug</div><strong id="vehicle">--</strong></div>
                <div class="fact"><div class="label">Zielstrom</div><strong><span id="targetCurrent">--</span> A</strong></div>
                <div class="fact"><div class="label">PV-Status</div><strong id="pvStatus">--</strong></div>
              </div>
            </section>

            <aside class="control-panel">
              <h2>Lademodus</h2>
              <div class="mode-buttons">
                <button class="mode-button" data-mode="off">
                  <span class="icon">II</span>
                  <span class="text"><strong>Laden pausieren</strong><span class="desc">Stoppt die Ladefreigabe.</span></span>
                </button>
                <button class="mode-button" data-mode="pv">
                  <span class="icon">PV</span>
                  <span class="text"><strong>PV-Überschuss</strong><span class="desc">Startet automatisch mit Solarstrom.</span></span>
                </button>
                <button class="mode-button" data-mode="instant">
                  <span class="icon">A</span>
                  <span class="text"><strong>Sofort laden</strong><span class="desc">Nutzt den eingestellten Strom.</span></span>
                </button>
              </div>

              <div class="current-control">
                <label for="currentSlider">
                  <span>Sofortladestrom</span>
                  <strong><span id="instantCurrentLabel">--</span> A</strong>
                </label>
                <div class="slider-row">
                  <input id="currentSlider" type="range" min="0" max="32" step="1" value="6">
                  <input id="currentInput" type="number" min="0" max="32" step="1" value="6">
                </div>
                <div class="hint">Gilt für „Sofort laden“. Hardware-Maximum und RLC-Begrenzung bleiben aktiv.</div>
              </div>

              <div id="error" class="error"></div>
            </aside>
          </div>

          <div class="data-grid">
            <div class="data-card"><div class="label">PV-Überschuss</div><div id="surplus" class="value">--</div><div id="surplusUnit" class="unit">W verfügbar</div></div>
            <div class="data-card"><div class="label">Netzleistung</div><div id="gridPower" class="value">--</div><div id="gridUnit" class="unit">W Import / Export</div></div>
            <div class="data-card"><div class="label">CP-State</div><div id="cpState" class="value">--</div><div class="unit">Ladestatus</div></div>
            <div class="data-card"><div class="label">Hardware-Max</div><div id="hwMax" class="value">--</div><div class="unit">A Grenze</div></div>
            <div class="data-card"><div class="label">RLC</div><div id="rlc" class="value">--</div><div class="unit">% Begrenzung</div></div>
            <div class="data-card"><div class="label">Hinweis</div><div id="reason" class="value">--</div><div id="timestamp" class="unit">Aktualisierung</div></div>
          </div>
        </div>
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

    const MODE_LABELS = {
      off: "Pausiert",
      pv: "PV-Überschuss",
      instant: "Sofort laden",
      hardware_override_free_charge: "FreeCharge"
    };

    const REASON_LABELS = {
      off: "Pausiert",
      instant: "Sofortladen",
      pv_surplus_available: "Solarstrom reicht",
      pv_waiting_start_delay: "Startverzögerung",
      pv_waiting_stop_delay: "Stopverzögerung",
      pv_waiting_for_surplus: "Wartet auf Sonne",
      stale_grid_power: "PV-Daten fehlen",
      vehicle_not_connected: "Kein Fahrzeug",
      hardware_override_free_charge: "FreeCharge aktiv",
      hardware_limit: "Hardware-Limit",
      rlc_limit: "RLC-Limit",
      hardware_or_rlc_limit: "Limit aktiv",
      not_started: "Dienst startet"
    };

    const nf = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
    const oneDecimalFmt = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

    function numberOrNull(value) {
      const numeric = Number(value);
      return Number.isFinite(numeric) ? numeric : null;
    }

    function fmt(value, digits = 0) {
      const numeric = numberOrNull(value);
      if (numeric === null) return "--";
      return digits > 0 ? oneDecimalFmt.format(numeric) : nf.format(numeric);
    }

    function fmtAmp(value) {
      const numeric = numberOrNull(value);
      if (numeric === null) return "--";
      const rounded = Math.round(numeric);
      if (Math.abs(numeric - rounded) < 0.05) return nf.format(rounded);
      return oneDecimalFmt.format(numeric);
    }

    function label(map, value) {
      return map[value] || value || "--";
    }

    function showError(message) {
      error.textContent = message || "";
      error.style.display = message ? "block" : "none";
    }

    function selectedModeTitle(state) {
      if (state.mode === "off") return "Laden pausiert";
      if (state.mode === "pv") return "PV-Überschuss gewählt";
      if (state.mode === "instant") return "Sofort laden gewählt";
      return "Bereit zum Laden";
    }

    function selectedModeCopy(state) {
      if (state.mode === "off") return "Der Softwaremodus ist pausiert. Hardware-FreeCharge wird separat angezeigt.";
      if (state.mode === "pv" && state.pv_input_stale) return "PV-Überschuss ist ausgewählt; Home Assistant liefert gerade keine aktuellen Netzdaten.";
      if (state.mode === "pv") return "PV-Überschuss ist ausgewählt. Solarwerte und Zielstrom bleiben sichtbar.";
      if (state.mode === "instant") return "Sofortladen ist ausgewählt. Der eingestellte Strom bleibt sichtbar.";
      return "Wählen Sie PV-Überschuss oder Sofortladen.";
    }

    function customerTitle(state) {
      if (state.hardware_override_free_charge) return selectedModeTitle(state);
      if (!state.vehicle_connected) return "Fahrzeug anschließen";
      if (state.is_charging && state.mode === "pv") return "Lädt mit Solarstrom";
      if (state.is_charging) return "Ihr Fahrzeug lädt";
      if (state.mode === "off") return "Laden pausiert";
      if (state.mode === "pv" && state.pv_input_stale) return "Warten auf PV-Daten";
      if (state.mode === "pv") return "Warten auf Überschuss";
      return "Bereit zum Laden";
    }

    function customerCopy(state) {
      if (state.hardware_override_free_charge) return selectedModeCopy(state);
      if (!state.vehicle_connected) return "Stecker einstecken. Danach übernimmt der gewählte Lademodus.";
      if (state.is_charging && state.mode === "pv") return "Solar-Überschuss wird in Ladestrom umgesetzt. Netzbezug bleibt begrenzt.";
      if (state.is_charging) return "Der Charger gibt aktuell Strom frei. Alle Hardware-Limits bleiben aktiv.";
      if (state.mode === "pv" && state.pv_input_stale) return "Home Assistant liefert gerade keine aktuellen Netzdaten.";
      if (state.mode === "pv") return "Der Charger startet automatisch, sobald genug Überschuss stabil vorhanden ist.";
      if (state.mode === "off") return "Der Ladepunkt bleibt gesperrt, bis ein anderer Modus gewählt wird.";
      return "Wählen Sie PV-Überschuss oder Sofortladen.";
    }

    function pvLabel(state) {
      const surplus = numberOrNull(state.pv_surplus_w);
      if (state.pv_input_stale) return "Daten fehlen";
      if (surplus !== null && surplus > 0) return "Überschuss aktiv";
      return "Wartet";
    }

    function gridUnit(value) {
      const numeric = numberOrNull(value);
      if (numeric === null) return "W Import / Export";
      if (numeric > 0) return "W Netzbezug";
      if (numeric < 0) return "W Einspeisung";
      return "W ausgeglichen";
    }

    function meterPercent(state) {
      const current = numberOrNull(state.effective_current_A);
      const max = numberOrNull(state.hw_max_current);
      if (current === null || max === null || max <= 0) return null;
      return Math.max(0, Math.min(100, Math.round((current / max) * 100)));
    }

    function updateFlow(state) {
      const charging = Boolean(state.is_charging);
      const surplus = numberOrNull(state.pv_surplus_w) || 0;
      const grid = numberOrNull(state.grid_power_w) || 0;
      $("flowPv").classList.toggle("active", charging && surplus > 0 && !state.pv_input_stale);
      $("flowGrid").classList.toggle("active", charging && grid > 0);
      $("flowGrid").classList.toggle("paused", !charging || grid <= 0);
      $("flowCable").classList.toggle("active", charging);
    }

    async function postJson(path, payload) {
      showError("");
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error("Befehl wurde nicht angenommen");
      return response.json();
    }

    async function setMode(mode) {
      buttons.forEach((button) => button.disabled = true);
      try {
        await postJson("/api/mode", { mode });
        await refresh();
      } catch (err) {
        showError(err.message);
      } finally {
        buttons.forEach((button) => button.disabled = false);
      }
    }

    async function setCurrent(value) {
      pendingCurrent = value;
      try {
        await postJson("/api/instant-current", { current: value });
        await refresh();
      } catch (err) {
        showError(err.message);
      } finally {
        pendingCurrent = null;
      }
    }

    function updateUi(state) {
      const charging = Boolean(state.is_charging);
      const stale = Boolean(state.pv_input_stale);
      const selectedMode = state.mode || state.effective_mode;
      const percent = meterPercent(state);
      const current = numberOrNull(state.effective_current_A);
      const surplus = numberOrNull(state.pv_surplus_w);
      const grid = numberOrNull(state.grid_power_w);
      const hardwareOverride = Boolean(state.hardware_override_free_charge);

      $("liveDot").className = "dot " + (charging ? "on" : stale ? "warn" : "");
      $("liveText").textContent = charging ? "Lädt" : stale ? "PV-Daten fehlen" : "Bereit";
      $("statusTitle").textContent = customerTitle(state);
      $("statusCopy").textContent = customerCopy(state);
      $("effectiveCurrent").textContent = fmtAmp(current);
      $("currentSubline").textContent = label(REASON_LABELS, state.limit_reason);
      $("modeBadge").textContent = label(MODE_LABELS, selectedMode);
      $("hardwareOverrideNotice").hidden = !hardwareOverride;
      $("vehicle").textContent = state.vehicle_connected ? "Verbunden" : "Nicht verbunden";
      $("targetCurrent").textContent = fmtAmp(state.target_current_A);
      $("pvStatus").textContent = pvLabel(state);
      $("meterFill").style.width = percent === null ? "0%" : percent + "%";
      $("meterPercent").textContent = percent === null ? "--" : percent + "%";

      $("surplus").textContent = fmt(surplus, 0);
      $("gridPower").textContent = fmt(grid, 0);
      $("gridUnit").textContent = gridUnit(grid);
      $("cpState").textContent = state.cp_state || "--";
      $("hwMax").textContent = fmt(state.hw_max_current, 0);
      $("rlc").textContent = fmt(state.rlc_percentage, 0);
      $("reason").textContent = label(REASON_LABELS, state.limit_reason);
      $("timestamp").textContent = state.timestamp || "--";
      $("instantCurrentLabel").textContent = fmtAmp(state.instant_current_A);

      $("surplus").className = "value " + (surplus !== null && surplus > 0 ? "good" : "");
      $("gridPower").className = "value " + (grid !== null && grid > 0 ? "warn" : "");
      $("reason").className = "value " + (stale ? "warn" : "");
      buttons.forEach((button) => button.classList.toggle("active", button.dataset.mode === state.mode));
      updateFlow(state);

      if (pendingCurrent === null) {
        const instant = Math.round(numberOrNull(state.instant_current_A) ?? 6);
        slider.value = instant;
        input.value = instant;
      }
    }

    async function refresh() {
      try {
        const response = await fetch("/api/state", { cache: "no-store" });
        if (!response.ok) throw new Error("Status nicht erreichbar");
        updateUi(await response.json());
        showError("");
      } catch (err) {
        $("liveDot").className = "dot warn";
        $("liveText").textContent = "Offline";
        $("statusTitle").textContent = "Keine Verbindung";
        $("statusCopy").textContent = "Die Webansicht erreicht den lokalen Charger-Dienst gerade nicht.";
        showError(err.message);
      }
    }

    buttons.forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
    slider.addEventListener("input", () => input.value = slider.value);
    slider.addEventListener("change", () => setCurrent(Number(slider.value)));
    input.addEventListener("change", () => {
      const value = Math.max(0, Math.min(32, Number(input.value || 0)));
      input.value = value;
      slider.value = value;
      setCurrent(value);
    });

    refresh();
    setInterval(refresh, 2000);
  </script>
</body>
</html>"""
