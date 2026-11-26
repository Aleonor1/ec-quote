// Panel stylesheet, kept as a string so it can be adopted by the shadow root
// without exposing any extension file to the page (no web_accessible_resources).
(() => {
  'use strict';
  const NS = (globalThis.EcQuote = globalThis.EcQuote || {});

  NS.PANEL_WIDTH = 368;
  NS.PANEL_RAIL_WIDTH = 40;

  NS.PANEL_CSS = `
:host { all: initial; }
.ecq {
  --bg: #ffffff; --bg-soft: #f5f6f6; --bg-field: #ffffff; --border: #e3e7ea; --border-strong: #c9d1d6;
  --text: #111b21; --muted: #5b6b75; --accent: #00745f; --accent-hover: #005f4e; --on-accent: #ffffff;
  --accent-soft: #e4f4f0; --note-bg: #fff6dc; --note-border: #e2b93b; --note-text: #4d3d08;
  --danger: #b3261e; --danger-soft: #fdecea; --warn: #8a5a00; --ok: #0b7a4b;
  --shadow: 0 0 0 1px rgba(17,27,33,.06), -6px 0 18px rgba(17,27,33,.06);
  box-sizing: border-box; height: 100%; width: 100%; display: flex; justify-content: flex-end;
  font: 400 13.5px/1.45 "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif;
  color: var(--text); -webkit-font-smoothing: antialiased; text-align: left;
}
.ecq[data-theme="dark"] {
  --bg: #111b21; --bg-soft: #1a262e; --bg-field: #0c1317; --border: #26343d; --border-strong: #3a4a54;
  --text: #e9edef; --muted: #9aa8b1; --accent: #00a884; --accent-hover: #06cf9c; --on-accent: #0b141a;
  --accent-soft: #12332d; --note-bg: #332b12; --note-border: #b08d1e; --note-text: #f3e2a9;
  --danger: #f2877f; --danger-soft: #3a1d1b; --warn: #e3b55a; --ok: #4fd39a;
  --shadow: 0 0 0 1px rgba(0,0,0,.4), -6px 0 18px rgba(0,0,0,.25);
}
*, *::before, *::after { box-sizing: border-box; }
[hidden] { display: none !important; }

.panel { width: 100%; height: 100%; display: flex; flex-direction: column; background: var(--bg);
  border-left: 1px solid var(--border); box-shadow: var(--shadow); min-height: 0; }
.ecq[data-floating="true"] .panel { border: 1px solid var(--border); border-radius: 10px 0 0 10px; }
.ecq[data-collapsed="true"] .panel { display: none; }
.rail { display: none; }
.ecq[data-collapsed="true"] .rail { display: flex; }
.rail { width: 100%; height: 100%; border: 0; border-left: 1px solid var(--border); background: var(--bg);
  color: var(--muted); cursor: pointer; flex-direction: column; align-items: center; gap: 10px;
  padding: 14px 0; font: inherit; }
.rail:hover { color: var(--text); background: var(--bg-soft); }
.rail-label { writing-mode: vertical-rl; transform: rotate(180deg); font-weight: 600; letter-spacing: .02em; font-size: 12.5px; }

.head { display: flex; align-items: center; gap: 10px; padding: 12px 12px 12px 14px; border-bottom: 1px solid var(--border); }
.mark { flex: none; width: 30px; height: 30px; border-radius: 8px; background: var(--accent); color: var(--on-accent);
  display: grid; place-items: center; font-weight: 700; font-size: 12px; letter-spacing: .03em; }
.rail .mark { width: 26px; height: 26px; font-size: 11px; }
.titles { min-width: 0; flex: 1; }
.title { font-weight: 600; font-size: 14px; line-height: 1.2; }
.chat { color: var(--muted); font-size: 12.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.icon-btn { flex: none; width: 30px; height: 30px; border-radius: 8px; border: 0; background: transparent; color: var(--muted);
  cursor: pointer; display: grid; place-items: center; }
.icon-btn:hover { background: var(--bg-soft); color: var(--text); }
svg { width: 18px; height: 18px; display: block; }

.body { flex: 1; min-height: 0; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 14px;
  scrollbar-width: thin; scrollbar-color: var(--border-strong) transparent; }
.view { display: flex; flex-direction: column; gap: 14px; }

.label { font-size: 11.5px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--muted); margin: 0 0 6px; }
.badge-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.badge { display: inline-flex; align-items: center; height: 22px; padding: 0 9px; border-radius: 999px; font-size: 12px; font-weight: 600;
  background: var(--accent-soft); color: var(--accent); }
.badge[data-kind="needs_human"] { background: var(--danger-soft); color: var(--danger); }
.badge[data-kind="none"] { background: var(--bg-soft); color: var(--muted); }

.note { background: var(--note-bg); border: 1px solid var(--note-border); border-left-width: 4px; border-radius: 8px; padding: 9px 11px; color: var(--note-text); }
.note .label { color: inherit; opacity: .85; margin-bottom: 3px; }
.note p { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.note .reason { margin-top: 6px; font-size: 12.5px; }

textarea { width: 100%; min-height: 96px; max-height: 300px; resize: vertical; padding: 10px 11px; border-radius: 8px;
  border: 1px solid var(--border-strong); background: var(--bg-field); color: var(--text); font: inherit; line-height: 1.5; display: block; }
textarea::placeholder { color: var(--muted); }
.hint { margin: 5px 0 0; color: var(--muted); font-size: 12px; }

.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { border: 1px solid var(--border-strong); background: var(--bg); color: var(--text); border-radius: 999px; padding: 4px 11px;
  font: inherit; font-size: 12.5px; cursor: pointer; max-width: 100%; overflow-wrap: anywhere; text-align: left; }
.chip:hover { border-color: var(--accent); color: var(--accent); }

table { width: 100%; border-collapse: collapse; font-size: 12.5px; font-variant-numeric: tabular-nums; }
.table-wrap { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
th, td { padding: 7px 8px; text-align: right; vertical-align: top; }
th:first-child, td:first-child { text-align: left; padding-left: 11px; }
th:last-child, td:last-child { padding-right: 11px; }
thead th { background: var(--bg-soft); color: var(--muted); font-weight: 600; font-size: 11.5px; white-space: nowrap; }
tbody tr + tr td { border-top: 1px solid var(--border); }
tbody tr[data-highlighted="true"] td { background: var(--accent-soft); font-weight: 600; }
tbody tr[data-highlighted="true"] td:first-child { box-shadow: inset 3px 0 0 var(--accent); }
.line-label { display: block; color: var(--muted); font-weight: 400; font-size: 11.5px; overflow-wrap: anywhere; }
.table-title { margin: 0 0 6px; font-weight: 600; overflow-wrap: anywhere; }
.caption { margin: 5px 0 0; color: var(--muted); font-size: 11.5px; }

.image-box { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; background: var(--bg-soft); }
.image-box img { display: block; width: 100%; height: auto; max-height: 260px; object-fit: contain; background: var(--bg-soft); }
.image-state { padding: 18px 12px; text-align: center; color: var(--muted); font-size: 12.5px; }
.row { display: flex; gap: 8px; flex-wrap: wrap; }
.image-box .row { padding: 8px; border-top: 1px solid var(--border); background: var(--bg); }

.pay { border: 1px solid var(--border); border-radius: 8px; padding: 9px 11px; background: var(--bg-soft); }
.pay-url { display: block; font-size: 12.5px; overflow-wrap: anywhere; user-select: all; margin-bottom: 8px; color: var(--text); }

.btn { appearance: none; border: 1px solid var(--border-strong); background: var(--bg); color: var(--text); border-radius: 8px;
  padding: 7px 12px; font: inherit; font-weight: 600; font-size: 13px; cursor: pointer; line-height: 1.3; text-align: center; }
.btn:hover { background: var(--bg-soft); }
.btn[disabled] { opacity: .55; cursor: default; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: var(--on-accent); }
.btn.primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
.btn.small { padding: 5px 10px; font-size: 12.5px; flex: 1; }
.btn.link { border: 0; background: transparent; padding: 2px 0; color: var(--accent); font-weight: 600; }
.btn.link:hover { text-decoration: underline; background: transparent; }

.state { text-align: center; padding: 34px 10px; color: var(--muted); display: flex; flex-direction: column; align-items: center; gap: 12px; }
.state strong { color: var(--text); font-size: 14px; font-weight: 600; }
.state p { margin: 0; max-width: 270px; }
.state[data-tone="error"] strong { color: var(--danger); }
.spinner { width: 26px; height: 26px; border-radius: 50%; border: 3px solid var(--border); border-top-color: var(--accent); animation: ecq-spin .9s linear infinite; }
@keyframes ecq-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spinner { animation-duration: 3s; } }

.banner { display: flex; align-items: center; justify-content: space-between; gap: 8px; border-radius: 8px; padding: 8px 11px;
  background: var(--accent-soft); color: var(--text); font-size: 12.5px; }
.notice { border-radius: 8px; padding: 8px 11px; font-size: 12.5px; background: var(--accent-soft); color: var(--text); overflow-wrap: anywhere; }
.notice[data-tone="error"] { background: var(--danger-soft); color: var(--danger); }

.attach { border-top: 1px solid var(--border); padding-top: 14px; }
.attach > .btn { width: 100%; }
.attach-info { margin: 0 0 8px; overflow-wrap: anywhere; }
.drop { margin-top: 8px; border: 1.5px dashed var(--border-strong); border-radius: 8px; padding: 11px; text-align: center; color: var(--muted); font-size: 12.5px; }
.drop[data-over="true"] { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
.attach-status { margin: 8px 0 0; font-size: 12.5px; overflow-wrap: anywhere; }
.attach-status[data-tone="error"] { color: var(--danger); }
.attach-status[data-tone="ok"] { color: var(--ok); }
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

.confirm { border-top: 1px solid var(--border); padding: 12px 14px; background: var(--bg-soft); }
.confirm p { margin: 0 0 9px; }
.actions { border-top: 1px solid var(--border); padding: 12px 14px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; background: var(--bg); }
.actions .wide { grid-column: 1 / -1; }

.foot { border-top: 1px solid var(--border); padding: 7px 14px; display: flex; align-items: center; justify-content: space-between; gap: 8px;
  font-size: 12px; color: var(--muted); background: var(--bg-soft); }
.compat { border: 0; background: transparent; font: inherit; color: inherit; padding: 2px 0; cursor: pointer; display: inline-flex; align-items: center; gap: 7px; text-align: left; }
.dot { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
.compat[data-status="ok"] .dot { background: var(--ok); }
.compat[data-status="check"] .dot { background: var(--warn); }
.compat[data-status="check"] { color: var(--warn); font-weight: 600; }
.checks { margin: 0; padding: 8px 14px 10px; list-style: none; border-top: 1px solid var(--border); background: var(--bg-soft); font-size: 12px; color: var(--muted); }
.checks li { display: flex; justify-content: space-between; gap: 10px; padding: 2px 0; }
.checks li[data-ok="false"] span:last-child { color: var(--warn); font-weight: 600; }

:is(button, textarea, a, [tabindex]):focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.btn.primary:focus-visible { outline-color: var(--text); }
`;
})();
