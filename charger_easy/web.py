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
      color-scheme: dark;
      --page: #071014;
      --screen: #0b1216;
      --screen-soft: #101b20;
      --surface: #132126;
      --surface-strong: #182a31;
      --ink: #f7fbfb;
      --ink-dark: #0f171b;
      --muted: #8ba0a7;
      --muted-dark: #9aaeb5;
      --line: rgba(255, 255, 255, 0.11);
      --line-dark: rgba(255, 255, 255, 0.16);
      --green: #20d49b;
      --green-dark: #0e8c67;
      --cyan: #65c7ef;
      --blue: #2c6ee8;
      --yellow: #f4bd50;
      --red: #e45b5b;
      --shadow: 0 24px 54px rgba(0, 0, 0, 0.34);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: linear-gradient(180deg, #10191e 0, var(--page) 100%);
      color: var(--ink);
      -webkit-tap-highlight-color: transparent;
    }
    button, input { font: inherit; }
    input {
      user-select: text;
      -webkit-user-select: text;
    }
    main {
      width: min(1320px, calc(100% - 24px));
      margin: 0 auto;
      padding: 12px 0 22px;
    }
    .kiosk {
      min-height: calc(100vh - 34px);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 8px;
      background: #080f13;
      box-shadow: var(--shadow);
      padding: 10px;
    }
    .screen {
      min-height: calc(100vh - 56px);
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
        linear-gradient(90deg, rgba(255,255,255,0.035), transparent 24%, transparent 76%, rgba(255,255,255,0.03)),
        linear-gradient(180deg, rgba(255,255,255,0.05), transparent 170px);
    }
    .screen-inner {
      position: relative;
      z-index: 1;
      display: grid;
      grid-template-rows: auto 1fr;
      min-height: calc(100vh - 56px);
      padding: 16px;
      gap: 12px;
    }
    .topbar {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 14px;
      align-items: center;
    }
    h1 {
      margin: 0;
      font-size: 29px;
      line-height: 1;
      letter-spacing: 0;
    }
    .subline {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 13px;
    }
    .status-chip {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 9px;
      min-height: 38px;
      min-width: 120px;
      padding: 8px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.07);
      color: var(--ink);
      font-size: 13px;
      font-weight: 900;
      white-space: nowrap;
    }
    .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--muted);
      box-shadow: 0 0 0 6px rgba(139, 160, 167, 0.18);
    }
    .dot.on { background: var(--green); box-shadow: 0 0 0 6px rgba(32, 212, 155, 0.18); }
    .dot.warn { background: var(--yellow); box-shadow: 0 0 0 6px rgba(244, 189, 80, 0.18); }
    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 318px;
      gap: 12px;
      align-items: start;
      min-height: 0;
    }
    .stage-panel, .control-panel, .metric-card, .limits-panel, .diagram-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.055);
      backdrop-filter: blur(10px);
    }
    .stage-panel {
      display: grid;
      grid-template-rows: auto auto auto;
      align-content: start;
      gap: 10px;
      min-width: 0;
      padding: 14px;
    }
    .dashboard-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: center;
    }
    .eyebrow, .label {
      color: #a8bac0;
      font-size: 12px;
      font-weight: 800;
      text-transform: none;
      letter-spacing: 0;
    }
    .status-title {
      margin: 3px 0 0;
      color: var(--ink);
      font-size: 32px;
      line-height: 1;
      letter-spacing: 0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .status-badges {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
    }
    .status-badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 32px;
      padding: 7px 10px;
      border-radius: 8px;
      border: 1px solid var(--line-dark);
      background: rgba(255, 255, 255, 0.07);
      color: var(--ink);
      font-size: 12px;
      font-weight: 950;
      white-space: nowrap;
    }
    .status-badge.accent {
      border-color: rgba(32, 212, 155, 0.32);
      background: rgba(32, 212, 155, 0.13);
      color: var(--green);
    }
    .status-badge.warning {
      border-color: rgba(244, 189, 80, 0.45);
      background: rgba(244, 189, 80, 0.14);
      color: var(--yellow);
    }
    .status-badge.warn {
      border-color: rgba(244, 189, 80, 0.45);
      color: var(--yellow);
    }
    .status-badge[hidden] {
      display: none;
    }
    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
    }
    .metric-card {
      min-height: 94px;
      min-width: 0;
      padding: 12px;
      background: linear-gradient(180deg, rgba(255,255,255,0.09), rgba(255,255,255,0.052));
    }
    .metric-card.primary {
      border-color: rgba(32, 212, 155, 0.22);
      background: linear-gradient(180deg, rgba(32, 212, 155, 0.13), rgba(255,255,255,0.045));
    }
    .metric-value {
      display: flex;
      align-items: baseline;
      gap: 5px;
      margin-top: 9px;
      min-width: 0;
      color: var(--ink);
      font-size: 27px;
      font-weight: 950;
      line-height: 1;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .metric-value.compact {
      font-size: 22px;
    }
    .metric-unit {
      color: var(--muted);
      font-size: 12px;
      font-weight: 900;
    }
    .unit {
      margin-top: 7px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.25;
    }
    .value.good, .metric-value.good { color: var(--green); }
    .value.warn, .metric-value.warn { color: var(--yellow); }
    .operations-grid {
      display: grid;
      grid-template-columns: minmax(360px, 1fr) minmax(280px, 0.58fr);
      gap: 10px;
      align-items: start;
      min-height: 0;
    }
    .diagram-card {
      position: relative;
      height: 302px;
      min-height: 0;
      background: #101a1f;
      color: var(--ink);
      overflow: hidden;
      user-select: none;
      -webkit-user-select: none;
    }
    .diagram-card::before {
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(145deg, rgba(255,255,255,0.075), transparent 52%, rgba(32, 212, 155, 0.055));
    }
    .diagram {
      position: relative;
      z-index: 1;
      width: 100%;
      height: 302px;
      min-height: 0;
      display: block;
      pointer-events: none;
    }
    .svg-label {
      font: 800 15px Inter, system-ui, sans-serif;
      fill: #ecf6f5;
    }
    .svg-small {
      font: 700 12px Inter, system-ui, sans-serif;
      fill: #9fb0b6;
    }
    .svg-pill {
      fill: rgba(255, 255, 255, 0.08);
      stroke: rgba(255, 255, 255, 0.16);
      stroke-width: 1;
    }
    .flow-line {
      fill: none;
      stroke: rgba(155, 174, 181, 0.55);
      stroke-width: 8;
      stroke-linecap: round;
      stroke-dasharray: 1 18;
    }
    .flow-line.active {
      stroke: var(--green);
      stroke-dasharray: 18 14;
      animation: flow 1.3s linear infinite;
    }
    .flow-line.grid-import.active { stroke: var(--yellow); }
    .flow-line.paused { stroke: rgba(155, 174, 181, 0.38); }
    .cable-base {
      fill: none;
      stroke: rgba(236, 246, 245, 0.64);
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
      fill: #17272e;
      stroke: rgba(255, 255, 255, 0.2);
      stroke-width: 2;
    }
    .node.dark { fill: #0a1115; stroke: rgba(255, 255, 255, 0.2); }
    .node.green { fill: var(--green); stroke: var(--green-dark); }
    .station-body {
      fill: #0c1519;
      stroke: rgba(236, 246, 245, 0.72);
      stroke-width: 3;
    }
    .station-side {
      fill: rgba(32, 212, 155, 0.16);
    }
    .station-screen {
      fill: #ecf6f5;
    }
    .station-screen-inner {
      fill: #1b2d34;
    }
    .station-slot {
      fill: rgba(236, 246, 245, 0.18);
    }
    .station-base {
      fill: rgba(236, 246, 245, 0.1);
    }
    .station-bolt {
      fill: var(--green);
      stroke: var(--green-dark);
      stroke-width: 2;
    }
    .ev-car * {
      vector-effect: non-scaling-stroke;
    }
    .car-shadow {
      fill: none;
      stroke: rgba(236, 246, 245, 0.11);
      stroke-width: 18;
      stroke-linecap: round;
      vector-effect: non-scaling-stroke;
    }
    .ev-body {
      fill: #17272e;
      stroke: #ecf6f5;
      stroke-width: 5;
      stroke-linecap: round;
      stroke-linejoin: round;
    }
    .ev-window {
      fill: rgba(101, 199, 239, 0.13);
      stroke: #ecf6f5;
      stroke-width: 4;
      stroke-linejoin: round;
    }
    .ev-detail {
      fill: none;
      stroke: rgba(236, 246, 245, 0.6);
      stroke-width: 3;
      stroke-linecap: round;
    }
    .ev-accent {
      fill: none;
      stroke: var(--green);
      stroke-width: 4;
      stroke-linecap: round;
    }
    .ev-wheel {
      fill: #0b1216;
      stroke: #ecf6f5;
      stroke-width: 5;
    }
    .ev-rim {
      fill: none;
      stroke: rgba(236, 246, 245, 0.48);
      stroke-width: 3;
    }
    .charge-port {
      fill: var(--green);
      stroke: var(--green-dark);
      stroke-width: 2;
    }
    @keyframes flow {
      to { stroke-dashoffset: -32; }
    }
    .limits-panel {
      display: grid;
      align-content: start;
      gap: 14px;
      min-width: 0;
      padding: 14px;
      background: rgba(255, 255, 255, 0.065);
    }
    .limit-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .limit-top strong {
      display: block;
      margin-top: 5px;
      color: var(--ink);
      font-size: 34px;
      line-height: 1;
      font-variant-numeric: tabular-nums;
    }
    .current-subline {
      color: var(--muted);
      font-size: 13px;
      font-weight: 900;
      text-align: right;
    }
    .charge-bar {
      display: grid;
      gap: 9px;
    }
    .bar-head {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 900;
    }
    .track {
      height: 12px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.11);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .fill {
      width: 0%;
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--green-dark), var(--green));
      transition: width 240ms ease;
    }
    .limit-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }
    .mini-stat {
      min-height: 66px;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.045);
    }
    .mini-stat strong {
      display: block;
      margin-top: 7px;
      color: var(--ink);
      font-size: 19px;
      line-height: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      font-variant-numeric: tabular-nums;
    }
    .control-panel {
      align-self: start;
      padding: 14px;
      background: rgba(255, 255, 255, 0.075);
      color: var(--ink);
    }
    .control-panel h2 {
      margin: 0 0 12px;
      font-size: 18px;
      line-height: 1.1;
      letter-spacing: 0;
    }
    .mode-buttons {
      display: grid;
      gap: 8px;
    }
    .mode-button {
      min-height: 54px;
      display: grid;
      grid-template-columns: 38px 1fr;
      gap: 10px;
      align-items: center;
      width: 100%;
      border: 1px solid var(--line-dark);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.06);
      color: var(--ink);
      cursor: pointer;
      text-align: left;
      padding: 8px 10px;
      user-select: none;
      -webkit-user-select: none;
      touch-action: manipulation;
      transition: transform 140ms ease, background 140ms ease, border-color 140ms ease, color 140ms ease;
    }
    .mode-button:hover {
      transform: translateY(-1px);
      border-color: rgba(255, 255, 255, 0.28);
      background: rgba(255, 255, 255, 0.09);
    }
    .mode-button .icon {
      display: grid;
      place-items: center;
      width: 38px;
      height: 38px;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.09);
      color: var(--muted);
      font-size: 13px;
      font-weight: 950;
    }
    .mode-button strong {
      display: block;
      font-size: 15px;
      line-height: 1.08;
    }
    .mode-button .text {
      display: block;
      min-width: 0;
    }
    .mode-button .desc {
      display: none;
    }
    .mode-button.active {
      background: rgba(32, 212, 155, 0.16);
      border-color: rgba(32, 212, 155, 0.38);
      color: #ffffff;
      box-shadow: 0 12px 24px rgba(0, 0, 0, 0.22);
    }
    .mode-button.active .icon {
      background: var(--green);
      color: #06261b;
    }
    .mode-button:disabled {
      cursor: not-allowed;
      opacity: 0.62;
      transform: none;
    }
    .current-control {
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
    }
    .current-control label {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 900;
      margin-bottom: 10px;
    }
    .current-control label strong {
      color: var(--ink);
      font-size: 20px;
      font-variant-numeric: tabular-nums;
    }
    .slider-row {
      display: grid;
      grid-template-columns: 1fr 76px;
      gap: 10px;
      align-items: center;
    }
    input[type="range"] {
      width: 100%;
      accent-color: var(--green);
    }
    input[type="number"] {
      width: 76px;
      height: 42px;
      border: 1px solid var(--line-dark);
      border-radius: 8px;
      padding: 7px;
      background: rgba(0, 0, 0, 0.2);
      color: var(--ink);
      font-weight: 900;
      text-align: right;
    }
    .hint {
      display: none;
    }
    .error {
      display: none;
      margin-top: 12px;
      padding: 10px 12px;
      border: 1px solid rgba(228, 91, 91, 0.36);
      border-radius: 8px;
      background: rgba(228, 91, 91, 0.12);
      color: #ffb4b4;
      font-weight: 900;
    }
    @media (max-width: 1050px) {
      .layout { grid-template-columns: 1fr; }
      .operations-grid { grid-template-columns: 1fr; }
      .diagram-card, .diagram { height: 280px; }
      .control-panel { align-self: auto; }
      .metrics-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .mode-buttons { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    }
    @media (max-width: 720px) {
      main { width: calc(100vw - 20px); padding: 6px 0 14px; }
      .kiosk { padding: 8px; }
      .layout, .stage-panel, .metric-card, .control-panel, .limits-panel, .diagram-card { max-width: 100%; }
      .screen-inner { min-height: calc(100vh - 34px); padding: 12px; }
      .topbar, .dashboard-head { grid-template-columns: 1fr; }
      h1 { font-size: 24px; }
      .status-title { font-size: 28px; }
      .status-chip, .status-badges { justify-self: start; justify-content: flex-start; }
      .metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .operations-grid { grid-template-columns: 1fr; }
      .diagram-card, .diagram { height: 240px; }
      .limit-grid { grid-template-columns: 1fr; }
      .stage-panel { padding: 12px; }
      .control-panel { padding: 14px; }
      .mode-buttons { grid-template-columns: 1fr; }
      .slider-row { grid-template-columns: 1fr; }
      input[type="number"] { width: 100%; text-align: left; }
      .mode-button { min-height: 52px; }
    }
    @media (max-width: 560px) {
      .metrics-grid { grid-template-columns: 1fr; }
      .metric-value { font-size: 25px; }
      .metric-value.compact { font-size: 21px; }
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
              <p class="subline">Solar laden · Live</p>
            </div>
            <div class="status-chip"><span id="liveDot" class="dot"></span><span id="liveText">Verbinde...</span></div>
          </header>

          <div class="layout">
            <section id="hero" class="stage-panel">
              <div class="dashboard-head">
                <div>
                  <div class="eyebrow">Lademodus</div>
                  <h2 id="statusTitle" class="status-title">--</h2>
                </div>
                <div class="status-badges">
                  <span id="modeBadge" class="status-badge accent">--</span>
                  <span id="reasonBadge" class="status-badge">--</span>
                  <span id="hardwareOverrideNotice" class="status-badge warning" hidden>HW-FreeCharge</span>
                </div>
              </div>

              <div class="metrics-grid">
                <div class="metric-card">
                  <div class="label">Netzleistung</div>
                  <div id="gridPowerMetric" class="metric-value"><span id="gridPower">--</span><span class="metric-unit">W</span></div>
                  <div id="gridUnit" class="unit">Import / Export</div>
                </div>
                <div class="metric-card primary">
                  <div class="label">PV-Überschuss</div>
                  <div id="surplusMetric" class="metric-value"><span id="surplus">--</span><span class="metric-unit">W</span></div>
                  <div id="surplusUnit" class="unit">verfügbar</div>
                </div>
                <div class="metric-card">
                  <div class="label">Zielstrom</div>
                  <div class="metric-value"><span id="targetCurrent">--</span><span class="metric-unit">A</span></div>
                  <div class="unit">Sollwert</div>
                </div>
                <div class="metric-card primary">
                  <div class="label">Ladestrom</div>
                  <div class="metric-value"><span id="effectiveCurrent">--</span><span class="metric-unit">A</span></div>
                  <div id="currentSubline" class="unit">--</div>
                </div>
                <div class="metric-card">
                  <div class="label">Fahrzeug</div>
                  <div id="vehicle" class="metric-value compact">--</div>
                  <div class="unit">Status</div>
                </div>
                <div class="metric-card">
                  <div class="label">CP-State</div>
                  <div id="cpState" class="metric-value compact">--</div>
                  <div class="unit">Kontakt</div>
                </div>
              </div>

              <div class="operations-grid">
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

                    <g class="charger-station">
                      <ellipse class="station-base" cx="298" cy="302" rx="58" ry="10"></ellipse>
                      <rect class="station-body" x="248" y="88" width="100" height="204" rx="10"></rect>
                      <path class="station-side" d="M330 98 H338 V282 H330 Z"></path>
                      <rect class="station-screen" x="270" y="112" width="56" height="44" rx="5"></rect>
                      <rect class="station-screen-inner" x="278" y="121" width="40" height="26" rx="3"></rect>
                      <rect class="station-slot" x="271" y="170" width="54" height="7" rx="3.5"></rect>
                      <rect class="station-slot" x="271" y="184" width="42" height="6" rx="3"></rect>
                      <circle class="station-bolt" cx="298" cy="218" r="22"></circle>
                      <path d="M299 203 L286 223 H299 L292 238 L314 212 H301 Z" fill="#ffffff"></path>
                    </g>
                    <text class="svg-label" x="298" y="330" text-anchor="middle">Wallbox</text>

                    <path class="car-shadow" d="M422 336 H676"></path>
                    <g class="ev-car">
                      <path class="ev-body" d="M394 286 L414 238 C421 222 436 212 454 212 H520 C545 212 563 225 582 252 L626 258 C652 262 670 280 670 306 V322 C670 331 663 338 654 338 H400 C391 338 384 331 384 322 V306 C384 296 388 290 394 286 Z"></path>
                      <path class="ev-window" d="M434 252 L448 226 H495 V252 Z"></path>
                      <path class="ev-window" d="M502 226 H520 C539 226 552 237 565 252 H502 Z"></path>
                      <path class="ev-detail" d="M586 268 H626"></path>
                      <path class="ev-accent" d="M410 284 C446 275 529 276 624 284"></path>
                      <circle class="ev-wheel" cx="448" cy="334" r="22"></circle>
                      <circle class="ev-rim" cx="448" cy="334" r="10"></circle>
                      <circle class="ev-wheel" cx="604" cy="334" r="22"></circle>
                      <circle class="ev-rim" cx="604" cy="334" r="10"></circle>
                    </g>
                    <circle class="charge-port" cx="402" cy="286" r="14"></circle>
                    <path class="cable-base" d="M348 218 C370 218 380 270 402 286"></path>
                    <path id="flowCable" class="cable-flow" d="M348 218 C370 218 380 270 402 286"></path>

                    <rect class="svg-pill" x="440" y="108" width="148" height="24" rx="12"></rect>
                    <text class="svg-small" x="514" y="125" text-anchor="middle">AC 230 V · 1 Phase</text>
                  </svg>
                </div>

                <div class="limits-panel">
                  <div class="limit-top">
                    <div>
                      <div class="label">Freigabe</div>
                      <strong id="meterPercent">--</strong>
                    </div>
                    <div id="pvStatus" class="status-badge">--</div>
                  </div>

                  <div class="charge-bar">
                    <div class="bar-head"><span>Hardware-Limit</span><strong id="meterPercentInline">--</strong></div>
                    <div class="track"><div id="meterFill" class="fill"></div></div>
                  </div>

                  <div class="limit-grid">
                    <div class="mini-stat"><div class="label">Hardware-Max</div><strong><span id="hwMax">--</span> A</strong></div>
                    <div class="mini-stat"><div class="label">RLC</div><strong><span id="rlc">--</span>%</strong></div>
                    <div class="mini-stat"><div class="label">Status</div><strong id="reason">--</strong></div>
                    <div class="mini-stat"><div class="label">Update</div><strong id="timestamp">--</strong></div>
                  </div>
                </div>
              </div>
            </section>

            <aside class="control-panel">
              <h2>Laden</h2>
              <div class="mode-buttons">
                <button class="mode-button" data-mode="off">
                  <span class="icon">II</span>
                  <span class="text"><strong>Pause</strong><span class="desc"></span></span>
                </button>
                <button class="mode-button" data-mode="pv">
                  <span class="icon">PV</span>
                  <span class="text"><strong>PV</strong><span class="desc"></span></span>
                </button>
                <button class="mode-button" data-mode="instant">
                  <span class="icon">A</span>
                  <span class="text"><strong>Sofort</strong><span class="desc"></span></span>
                </button>
              </div>

              <div class="current-control">
                <label for="currentSlider">
                  <span>Sofortstrom</span>
                  <strong><span id="instantCurrentLabel">--</span> A</strong>
                </label>
                <div class="slider-row">
                  <input id="currentSlider" type="range" min="0" max="32" step="1" value="6">
                  <input id="currentInput" type="number" min="0" max="32" step="1" value="6">
                </div>
                <div class="hint"></div>
              </div>

              <div id="error" class="error"></div>
            </aside>
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
      off: "Pause",
      pv: "PV-Überschuss",
      instant: "Sofortladen",
      hardware_override_free_charge: "FreeCharge"
    };

    const REASON_LABELS = {
      off: "Pause",
      instant: "Instant",
      pv_surplus_available: "PV aktiv",
      pv_waiting_start_delay: "Startdelay",
      pv_waiting_stop_delay: "Stopdelay",
      pv_waiting_for_surplus: "Warten",
      stale_grid_power: "PV-Daten fehlen",
      vehicle_not_connected: "Kein Fahrzeug",
      hardware_override_free_charge: "FreeCharge",
      hardware_limit: "Hardware-Limit",
      rlc_limit: "RLC-Limit",
      hardware_or_rlc_limit: "Limit aktiv",
      not_started: "Start"
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

    function pvLabel(state) {
      const surplus = numberOrNull(state.pv_surplus_w);
      if (state.pv_input_stale) return "PV-Daten";
      if (surplus !== null && surplus > 0) return "Überschuss";
      return "Warten";
    }

    function gridUnit(value) {
      const numeric = numberOrNull(value);
      if (numeric === null) return "Import / Export";
      if (numeric > 0) return "Netzbezug";
      if (numeric < 0) return "Einspeisung";
      return "Ausgeglichen";
    }

    function meterPercent(state) {
      const current = numberOrNull(state.effective_current_A);
      const max = numberOrNull(state.hw_max_current);
      if (current === null || max === null || max <= 0) return null;
      return Math.max(0, Math.min(100, Math.round((current / max) * 100)));
    }

    function fmtTimestamp(value) {
      if (!value) return "--";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return value;
      return date.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    }

    function isWarningReason(reason, stale) {
      return stale || [
        "stale_grid_power",
        "vehicle_not_connected",
        "hardware_override_free_charge",
        "hardware_limit",
        "rlc_limit",
        "hardware_or_rlc_limit"
      ].includes(reason);
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
      const reasonText = label(REASON_LABELS, state.limit_reason);
      const percentText = percent === null ? "--" : percent + "%";

      $("liveDot").className = "dot " + (charging ? "on" : stale ? "warn" : "");
      $("liveText").textContent = charging ? "Lädt" : stale ? "PV-Daten fehlen" : "Bereit";
      $("statusTitle").textContent = label(MODE_LABELS, selectedMode);
      $("effectiveCurrent").textContent = fmtAmp(current);
      $("currentSubline").textContent = reasonText;
      $("modeBadge").textContent = label(MODE_LABELS, selectedMode);
      $("reasonBadge").textContent = reasonText;
      $("hardwareOverrideNotice").hidden = !hardwareOverride;
      $("vehicle").textContent = state.vehicle_connected ? "Verbunden" : "Kein Auto";
      $("targetCurrent").textContent = fmtAmp(state.target_current_A);
      $("pvStatus").textContent = pvLabel(state);
      $("meterFill").style.width = percent === null ? "0%" : percent + "%";
      $("meterPercent").textContent = percentText;
      $("meterPercentInline").textContent = percentText;

      $("surplus").textContent = fmt(surplus, 0);
      $("gridPower").textContent = fmt(grid, 0);
      $("gridUnit").textContent = gridUnit(grid);
      $("cpState").textContent = state.cp_state || "--";
      $("hwMax").textContent = fmt(state.hw_max_current, 0);
      $("rlc").textContent = fmt(state.rlc_percentage, 0);
      $("reason").textContent = reasonText;
      $("timestamp").textContent = fmtTimestamp(state.timestamp);
      $("instantCurrentLabel").textContent = fmtAmp(state.instant_current_A);

      $("surplusMetric").className = "metric-value " + (surplus !== null && surplus > 0 ? "good" : "");
      $("gridPowerMetric").className = "metric-value " + (grid !== null && grid > 0 ? "warn" : grid !== null && grid < 0 ? "good" : "");
      $("reasonBadge").className = "status-badge " + (isWarningReason(state.limit_reason, stale) ? "warn" : "");
      $("pvStatus").className = "status-badge " + (stale ? "warn" : surplus !== null && surplus > 0 ? "accent" : "");
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
        $("statusTitle").textContent = "Offline";
        $("modeBadge").textContent = "--";
        $("reasonBadge").textContent = "Offline";
        $("reasonBadge").className = "status-badge warn";
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
