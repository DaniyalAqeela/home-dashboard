// Dashboard settings site. Plain JS, no build step, no CDN: it must work on a LAN
// without internet. All user/feed text goes into the DOM via textContent.
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const snap = (v) => Math.round(v * 2) / 2;

function el(tag, props, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k in e && typeof v !== "string") e[k] = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) e.append(kid);
  return e;
}

async function api(method, path, body) {
  const opt = { method, headers: { "X-Dashboard": "1" }, cache: "no-store" };
  if (body instanceof FormData) opt.body = body;
  else if (body !== undefined) {
    opt.headers["Content-Type"] = "application/json";
    opt.body = JSON.stringify(body);
  }
  const r = await fetch(path, opt);
  if (r.status === 401 && !path.startsWith("/api/auth/")) {
    showAuth();
    throw new Error("Please log in again");
  }
  const data = (r.headers.get("Content-Type") || "").includes("json") ? await r.json() : null;
  if (!r.ok) throw new Error((data && data.error) || `${r.status} ${r.statusText}`);
  return data;
}

let toastTimer;
function toast(msg, bad = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "show" + (bad ? " bad" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = ""), bad ? 6000 : 2500);
}
const fail = (e) => toast(e.message || String(e), true);

function busy(msg) {
  $("#busyText").textContent = msg;
  $("#busy").hidden = !msg;
}

// Wait for the service to come back after an update/restart, then reload.
async function waitForRestart(msg) {
  busy(msg);
  await sleep(4000);
  for (let i = 0; i < 120; i++) {
    try {
      const r = await fetch("/api/health", { cache: "no-store" });
      if (r.ok) return location.reload();
    } catch (e) { /* still restarting */ }
    await sleep(2000);
    if (i === 60) busy(msg + " This is taking a while. If nothing happens in a few minutes, unplug the dashboard and plug it back in.");
  }
}

const S = { cfg: null, schema: null, info: null, sel: null, tab: "design", edits: 0, saveTimer: null, started: false };

// ---------------------------------------------------------------- auth
async function showAuth() {
  let set = true;
  try { set = (await api("GET", "/api/auth/status")).set; } catch (e) { /* offline: show login */ }
  $("#auth").hidden = false;
  $("#authTitle").textContent = set ? "Log in" : "Welcome! Create a password";
  $("#authHint").textContent = set ? "Enter the dashboard password." : "This password protects these settings. Use at least 6 characters.";
  $("#authPw2").hidden = set;
  $("#authBtn").textContent = set ? "Log in" : "Create password";
  $("#authForm").dataset.mode = set ? "login" : "setup";
  $("#authPw").focus();
}

$("#authForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const pw = $("#authPw").value;
  const setup = $("#authForm").dataset.mode === "setup";
  $("#authErr").textContent = "";
  if (setup && pw !== $("#authPw2").value) return ($("#authErr").textContent = "The passwords don't match.");
  try {
    await api("POST", setup ? "/api/auth/setup" : "/api/auth/login", { password: pw });
    $("#auth").hidden = true;
    $("#authPw").value = $("#authPw2").value = "";
    if (!S.started) await start();
  } catch (e) {
    $("#authErr").textContent = e.message;
  }
});

$("#logout").addEventListener("click", async () => {
  await api("POST", "/api/auth/logout").catch(() => {});
  location.reload();
});

// ---------------------------------------------------------------- config saving
function changed() {
  S.edits++;
  renderBoxes();
  save();
}

function save(delay = 300) {
  clearTimeout(S.saveTimer);
  return new Promise((resolve) => {
    S.saveTimer = setTimeout(async () => {
      const seq = S.edits;
      try {
        const cfg = await api("PUT", "/api/config", S.cfg);
        if (seq === S.edits) S.cfg = cfg; // don't drop edits made while this was in flight
        renderBoxes();
      } catch (e) { fail(e); }
      resolve();
    }, delay);
  });
}

// ---------------------------------------------------------------- generic form fields
// getObj() returns the live object holding the values (looked up on every change,
// because S.cfg is replaced by the server's normalized copy after each save).
function renderFields(container, fields, getObj, defaults = {}) {
  for (const f of fields) {
    const obj = getObj();
    if (!obj) continue;
    const value = obj[f.key] !== undefined ? obj[f.key] : (defaults[f.key] !== undefined ? defaults[f.key] : f.default);
    if (f.type === "object") {
      const fs = el("fieldset", {}, el("legend", { text: f.label }));
      renderFields(fs, f.fields, () => { const o = getObj(); return o && o[f.key]; });
      container.append(fs);
      continue;
    }
    const set = (v) => { const o = getObj(); if (o) { o[f.key] = v; changed(); } };
    container.append(el("label", { class: "field" }, el("span", { text: f.label }), input(f, value, set)));
  }
}

function input(f, value, set) {
  switch (f.type) {
    case "bool":
      return el("input", { type: "checkbox", checked: !!value, onchange: (e) => set(e.target.checked) });
    case "number":
    case "coord": {
      return el("input", {
        type: "number", value: value === null || value === undefined ? "" : String(value),
        min: f.min !== undefined ? String(f.min) : null, max: f.max !== undefined ? String(f.max) : null,
        step: f.type === "coord" ? "any" : String(f.step || 1),
        onchange: (e) => set(e.target.value === "" ? (f.type === "coord" ? null : f.default) : Number(e.target.value)),
      });
    }
    case "select":
    case "mode": {
      const choices = f.type === "mode" ? [["auto", "Automatic"], ...((S.info && S.info.modes) || []).map((m) => [m, m])] : f.choices;
      const sel = el("select", { onchange: (e) => set(JSON.parse(e.target.value)) },
        choices.map(([v, label]) => el("option", { value: JSON.stringify(v), text: label })));
      sel.value = JSON.stringify(value);
      if (sel.selectedIndex < 0) sel.append(el("option", { value: JSON.stringify(value), text: String(value), selected: true }));
      return sel;
    }
    case "color":
      return colorInput(f, value, set);
    case "list":
      return el("textarea", {
        rows: 3, value: (value || []).join("\n"), placeholder: "One per line",
        onchange: (e) => set(e.target.value.split("\n").map((s) => s.trim()).filter(Boolean)),
      });
    case "time":
      return el("input", { type: "time", value: value || "", onchange: (e) => set(e.target.value) });
    case "tz": {
      const id = "tzlist";
      if (!document.getElementById(id) && Intl.supportedValuesOf) {
        document.body.append(el("datalist", { id }, Intl.supportedValuesOf("timeZone").map((z) => el("option", { value: z }))));
      }
      return el("input", { type: "text", list: id, value: value || "", onchange: (e) => set(e.target.value.trim()) });
    }
    default: // text, country, repo
      return el("input", {
        type: "text", value: value || "", maxLength: f.maxLength || (f.type === "country" ? 2 : 200),
        onchange: (e) => set(e.target.value.trim()),
      });
  }
}

// colours are stored as #RRGGBB or #RRGGBBAA; "" means "use the theme's"
function colorInput(f, value, set) {
  const rgb = value ? value.slice(0, 7) : "#ffffff";
  const a = value && value.length === 9 ? parseInt(value.slice(7), 16) : 255;
  const useTheme = f.default === "" ? el("input", { type: "checkbox", checked: !value, title: "Use the theme colour" }) : null;
  const pick = el("input", { type: "color", value: rgb });
  const alpha = el("input", { type: "range", min: "0", max: "255", value: String(a), title: "Opacity" });
  const emit = () => {
    if (useTheme && useTheme.checked) return set("");
    const av = Number(alpha.value);
    set(pick.value.toUpperCase() + (av === 255 ? "" : av.toString(16).padStart(2, "0").toUpperCase()));
  };
  pick.addEventListener("input", () => { if (useTheme) useTheme.checked = false; emit(); });
  alpha.addEventListener("input", () => { if (useTheme) useTheme.checked = false; emit(); });
  if (useTheme) useTheme.addEventListener("change", emit);
  return el("span", { class: "color" }, useTheme && el("small", { class: "muted" }, useTheme, " theme"), pick, alpha);
}

// ---------------------------------------------------------------- design tab
const findW = (id) => S.cfg.widgets.find((w) => w.id === id);
const GEOMETRY = [
  { key: "x", label: "Left (%)", type: "number", min: 0, max: 99, step: 0.5 },
  { key: "y", label: "Top (%)", type: "number", min: 0, max: 99, step: 0.5 },
  { key: "w", label: "Width (%)", type: "number", min: 1, max: 100, step: 0.5 },
  { key: "h", label: "Height (%)", type: "number", min: 1, max: 100, step: 0.5 },
];

function placeBox(box, w) {
  Object.assign(box.style, { left: w.x + "%", top: w.y + "%", width: w.w + "%", height: w.h + "%", zIndex: 100 + w.z });
}

function renderBoxes() {
  if (!S.cfg) return;
  const pad = S.cfg.display.padding;
  const boxes = $("#boxes");
  Object.assign(boxes.style, { left: pad.left + "%", top: pad.top + "%", right: pad.right + "%", bottom: pad.bottom + "%" });
  const side = S.cfg.display.rotation === 90 || S.cfg.display.rotation === 270;
  if (!$("#shot").naturalWidth) $("#stage").style.setProperty("--ar", side ? "9 / 16" : "16 / 9");
  boxes.replaceChildren();
  for (const w of S.cfg.widgets) {
    const label = (S.schema.widgets[w.type] || {}).label || w.type;
    const box = el("div", { class: "box" + (w.id === S.sel ? " sel" : ""), "data-id": w.id },
      el("span", { class: "tag", text: label }), el("div", { class: "handle" }));
    placeBox(box, w);
    box.addEventListener("pointerdown", (ev) => drag(ev, w.id, ev.target.classList.contains("handle") ? "size" : "move"));
    boxes.append(box);
  }
}

function drag(ev, id, mode) {
  ev.preventDefault();
  if (S.sel !== id) {
    S.sel = id;
    renderBoxes();
    renderPanel();
  }
  S.edits++; // a save response arriving mid-drag must not replace S.cfg
  const rect = $("#boxes").getBoundingClientRect();
  const w0 = { ...findW(id) };
  const box = $(`#boxes [data-id="${CSS.escape(id)}"]`);
  let moved = false;
  const move = (e) => {
    const w = findW(id);
    if (!w) return;
    const dx = ((e.clientX - ev.clientX) / rect.width) * 100;
    const dy = ((e.clientY - ev.clientY) / rect.height) * 100;
    if (mode === "move") {
      w.x = snap(clamp(w0.x + dx, 0, 100 - w0.w));
      w.y = snap(clamp(w0.y + dy, 0, 100 - w0.h));
    } else {
      w.w = snap(clamp(w0.w + dx, 2, 100 - w0.x));
      w.h = snap(clamp(w0.h + dy, 2, 100 - w0.y));
    }
    moved = moved || w.x !== w0.x || w.y !== w0.y || w.w !== w0.w || w.h !== w0.h;
    if (box) placeBox(box, w);
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    window.removeEventListener("pointercancel", up);
    if (moved) {
      renderPanel();
      changed();
    }
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
  window.addEventListener("pointercancel", up);
}

function renderPanel() {
  const p = $("#panel");
  p.replaceChildren();
  const w = S.sel && findW(S.sel);
  if (w) {
    const t = S.schema.widgets[w.type];
    const maxZ = Math.max(...S.cfg.widgets.map((x) => x.z));
    const minZ = Math.min(...S.cfg.widgets.map((x) => x.z));
    p.append(
      el("h2", { text: t.label }),
      el("div", { class: "row" },
        el("button", { class: "ghost", text: "Duplicate", onclick: () => addWidget({ ...JSON.parse(JSON.stringify(w)), id: undefined, x: clamp(w.x + 2, 0, 99 - w.w), y: clamp(w.y + 2, 0, 99 - w.h), z: Math.min(100, maxZ + 1) }) }),
        el("button", { class: "ghost", text: "To front", onclick: () => { w.z = Math.min(100, maxZ + 1); changed(); } }),
        el("button", { class: "ghost", text: "To back", onclick: () => { w.z = Math.max(-100, minZ - 1); changed(); } }),
        el("button", { class: "danger", text: "Delete", onclick: () => {
          if (!confirm(`Delete this ${t.label} widget?`)) return;
          S.cfg.widgets = S.cfg.widgets.filter((x) => x.id !== w.id);
          S.sel = null;
          renderPanel();
          changed();
        } }),
        el("button", { class: "ghost", text: "Done", onclick: () => { S.sel = null; renderBoxes(); renderPanel(); } })),
      el("h3", { text: "Position and size" }));
    renderFields(p, GEOMETRY, () => findW(w.id));
    if (t.options.length) {
      p.append(el("h3", { text: "Options" }));
      renderFields(p, t.options, () => { const x = findW(w.id); return x && x.options; });
    }
    p.append(el("h3", { text: "Style" }));
    renderFields(p, S.schema.common, () => { const x = findW(w.id); return x && x.style; }, t.style);
    return;
  }
  p.append(el("h2", { text: "Layout" }), el("p", { class: "muted", text: "Click a widget in the preview to edit it." }));
  const type = el("select", {}, Object.entries(S.schema.widgets).map(([k, v]) => el("option", { value: k, text: v.label })));
  p.append(el("div", { class: "row" }, type, el("button", {
    text: "Add widget",
    onclick: () => addWidget({ type: type.value, x: 35, y: 30, w: 30, h: 30, z: Math.min(100, Math.max(0, ...S.cfg.widgets.map((x) => x.z)) + 1) }),
  })));
  p.append(el("h3", { text: "Theme" }));
  renderFields(p, S.schema.sections.theme, () => S.cfg.theme);
}

async function addWidget(w) {
  if (S.cfg.widgets.length >= 50) return toast("That's the maximum of 50 widgets.", true);
  delete w.id;
  S.cfg.widgets.push(w);
  S.edits++;
  await save(0);
  S.sel = S.cfg.widgets[S.cfg.widgets.length - 1].id;
  renderBoxes();
  renderPanel();
}

let shotBusy = false;
async function refreshShot() {
  if (shotBusy || S.tab !== "design" || document.hidden || !$("#auth").hidden) return;
  shotBusy = true;
  try {
    const r = await fetch("/api/screenshot?t=" + Date.now(), { cache: "no-store" });
    if (r.status === 200) {
      const img = $("#shot");
      const old = img.src;
      img.src = URL.createObjectURL(await r.blob());
      if (old.startsWith("blob:")) URL.revokeObjectURL(old);
      $("#shotNote").textContent = S.info && S.info.screenOff ? "The screen is off (night schedule); showing the last picture." : "Live view of the screen, refreshed every second.";
    } else if (r.status === 204) {
      $("#shotNote").textContent = "Waiting for the screen to send a picture…";
    } else if (r.status === 401) {
      showAuth();
    }
  } catch (e) { /* the dashboard may be restarting */ }
  shotBusy = false;
}
$("#shot").addEventListener("load", (e) => {
  const i = e.target;
  if (i.naturalWidth) $("#stage").style.setProperty("--ar", `${i.naturalWidth} / ${i.naturalHeight}`);
});

// ---------------------------------------------------------------- other tabs
function section(id, ...kids) {
  const s = $("#tab-" + id);
  s.replaceChildren(...kids);
  return s;
}
function card(title, ...kids) {
  return el("div", { class: "card" }, title && el("h2", { text: title }), ...kids);
}
function fieldsCard(title, sectionKey, note) {
  const c = card(title, note && el("p", { class: "muted small", text: note }));
  renderFields(c, S.schema.sections[sectionKey], () => S.cfg[sectionKey]);
  return c;
}
const fmtBytes = (n) => (n > 1e9 ? (n / 1e9).toFixed(1) + " GB" : (n / 1e6).toFixed(0) + " MB");
const fmtTime = (ts) => (ts ? new Date(ts * 1000).toLocaleString() : "never");

let photoTimer;
async function renderPhotos() {
  const status = el("p", { class: "muted", text: "Loading…" });
  const grid = el("div", { class: "grid" });
  const upErr = el("div", { class: "err" });
  const files = el("input", { type: "file", accept: "image/jpeg,image/png,image/webp", multiple: true, hidden: true });
  files.addEventListener("change", async () => {
    const list = [...files.files];
    upErr.replaceChildren();
    for (let i = 0; i < list.length; i++) {
      busy(`Uploading photo ${i + 1} of ${list.length}…`);
      const fd = new FormData();
      fd.append("files", list[i]);
      try {
        const r = await api("POST", "/api/photos/upload", fd);
        r.errors.forEach((x) => upErr.append(el("div", { text: `${x.name}: ${x.error}` })));
      } catch (e) {
        upErr.append(el("div", { text: `${list[i].name}: ${e.message}` }));
      }
    }
    busy("");
    files.value = "";
    refresh();
  });
  section("photos",
    fieldsCard("Google Drive", "photos",
      "Paste the link of a Google Drive folder. In Drive: Share → General access → Anyone with the link. Leave the API key empty: it's only a fallback in case Google ever changes its public folder page."),
    card("Sync status", status, el("div", { class: "row" }, el("button", {
      text: "Sync now", onclick: () => api("POST", "/api/photos/sync").then(() => toast("Sync started")).catch(fail),
    }))),
    card("Uploaded photos",
      el("p", { class: "muted small", text: "Photos you upload here are shown together with the Drive photos (see each Photos widget's \"Photos from\" option)." }),
      el("div", { class: "row" }, el("button", { text: "Upload photos…", onclick: () => files.click() }), files), upErr, grid));

  async function refresh() {
    try {
      const r = await api("GET", "/api/photos");
      const d = r.drive;
      status.className = d.error ? "err" : "muted";
      status.textContent = d.progress
        ? `Downloading ${d.progress[0]} of ${d.progress[1]} photos…`
        : `${d.count} photos from Drive. Last sync: ${fmtTime(d.lastSync)}.` + (d.error ? " " + d.error : "");
      const names = r.uploads.map((u) => u.name).join("|");
      if (grid.dataset.names !== names) {
        grid.dataset.names = names;
        grid.replaceChildren(...r.uploads.map((u) => el("div", { class: "thumb" },
          el("img", { src: "/photo/uploads/" + encodeURIComponent(u.name), loading: "lazy", alt: "" }),
          el("button", { class: "danger", text: "Delete", onclick: async () => {
            if (!confirm("Delete this photo?")) return;
            await api("DELETE", "/api/photos/uploads/" + encodeURIComponent(u.name)).catch(fail);
            refresh();
          } }))));
        if (!r.uploads.length) grid.append(el("p", { class: "muted", text: "No uploaded photos yet." }));
      }
    } catch (e) { status.textContent = e.message; }
  }
  refresh();
  clearInterval(photoTimer);
  photoTimer = setInterval(() => S.tab === "photos" && refresh(), 3000);
}

async function renderDisplay() {
  S.info = await api("GET", "/api/system/info").catch(() => S.info);
  section("display", fieldsCard("Screen", "display",
    "Rotation and scale apply immediately. Changing the resolution restarts the screen (a few seconds of black). Edge padding keeps widgets away from the screen edges, e.g. for a TV that crops the picture."));
}

function renderLocation() {
  const results = el("ul", { class: "list" });
  const q = el("input", { type: "search", placeholder: "City or town, e.g. Bandung" });
  const search = async () => {
    results.replaceChildren(el("li", { class: "muted", text: "Searching…" }));
    try {
      const r = await api("GET", "/api/location/search?q=" + encodeURIComponent(q.value));
      results.replaceChildren(...r.map((p) => el("li", {
        onclick: () => {
          S.cfg.location = { name: p.name, lat: p.lat, lon: p.lon, timezone: p.timezone, country: p.countryCode };
          changed();
          toast(`Location set to ${p.name}`);
          renderLocation();
        },
      }, el("span", { text: [p.name, p.admin1, p.country].filter(Boolean).join(", ") }), el("small", { class: "muted", text: p.timezone }))));
      if (!r.length) results.replaceChildren(el("li", { class: "muted", text: "No places found." }));
    } catch (e) { results.replaceChildren(el("li", { class: "err", text: e.message })); }
  };
  q.addEventListener("keydown", (e) => e.key === "Enter" && search());
  section("location",
    card("Find your place", el("p", { class: "muted small", text: "Used for weather, prayer times, the clock's time zone and the Wi-Fi country." }),
      el("div", { class: "row" }, q, el("button", { text: "Search", onclick: search })), results),
    fieldsCard("Details", "location", "You can also type the coordinates yourself."));
}

async function renderNetwork() {
  const status = el("p", { class: "muted", text: "Checking…" });
  const nets = el("ul", { class: "list" });
  const ssid = el("input", { type: "text", placeholder: "Network name", maxLength: 32 });
  const pw = el("input", { type: "password", placeholder: "Password (empty for open networks)" });
  const scan = async () => {
    nets.replaceChildren(el("li", { class: "muted", text: "Scanning (takes a few seconds)…" }));
    try {
      const r = await api("GET", "/api/wifi/scan");
      const s = r.status;
      status.textContent = (s.eth_ip ? `Ethernet: ${s.eth_ip}. ` : "Ethernet: not connected. ")
        + (s.ssid ? `Wi-Fi: connected to "${s.ssid}"${s.ip ? " (" + s.ip + ")" : ""}.` : "Wi-Fi: not connected.");
      nets.replaceChildren(...r.networks.map((n) => el("li", { onclick: () => { ssid.value = n.ssid; pw.focus(); } },
        el("span", { text: n.ssid + (n.secure ? " 🔒" : "") }),
        el("small", { class: "muted", text: n.signal > -55 ? "strong" : n.signal > -70 ? "good" : "weak" }))));
      if (!r.networks.length) nets.replaceChildren(el("li", { class: "muted", text: "No networks found." }));
    } catch (e) { nets.replaceChildren(el("li", { class: "err", text: e.message })); }
  };
  section("network",
    card("Status", status, el("p", { class: "muted small", text: "When an Ethernet cable is plugged in it is always used first." })),
    card("Wi-Fi", el("div", { class: "row" }, el("button", { class: "ghost", text: "Scan for networks", onclick: scan })), nets,
      el("div", { class: "row" }, ssid, pw,
        el("button", { text: "Connect", onclick: async () => {
          try {
            await api("POST", "/api/wifi/connect", { ssid: ssid.value, password: pw.value });
            toast("Saved. The dashboard is connecting to " + ssid.value);
            pw.value = "";
            setTimeout(scan, 8000);
          } catch (e) { fail(e); }
        } }),
        el("button", { class: "ghost", text: "Forget", onclick: async () => {
          if (!ssid.value || !confirm(`Forget the Wi-Fi network "${ssid.value}"?`)) return;
          await api("POST", "/api/wifi/forget", { ssid: ssid.value }).then(() => toast("Forgotten")).catch(fail);
        } })),
      el("p", { class: "muted small", text: "Tip: set your country in Location so the right Wi-Fi channels are used." })));
  scan();
}

async function renderUpdates() {
  const info = el("table", { class: "info" });
  const actions = el("div", { class: "row" });
  const notes = el("pre", { class: "logs", hidden: true });
  const file = el("input", { type: "file", accept: ".tar.gz,.tgz,application/gzip", hidden: true });
  file.addEventListener("change", async () => {
    if (!file.files[0]) return;
    const fd = new FormData();
    fd.append("bundle", file.files[0]);
    busy("Installing the update…");
    try {
      const r = await api("POST", "/api/update/upload", fd);
      waitForRestart(`Installed version ${r.version}. Restarting the dashboard…`);
    } catch (e) { busy(""); fail(e); }
    file.value = "";
  });
  const load = async (check) => {
    try {
      const s = await api("GET", "/api/update/status" + (check ? "?check=1" : ""));
      const row = (k, v) => el("tr", {}, el("td", { text: k }), el("td", { text: v }));
      info.replaceChildren(row("Running version", s.version), row("Previous version", s.previous || "none"),
        row("Latest on GitHub", s.latest ? s.latest.version : (s.error ? "couldn't check: " + s.error : "no releases yet")),
        row("Last checked", fmtTime(s.checked)));
      notes.hidden = !(s.newer && s.latest.notes);
      notes.textContent = s.latest ? s.latest.notes : "";
      actions.replaceChildren(...[
        el("button", { class: "ghost", text: "Check for updates", onclick: () => load(true) }),
        s.newer && el("button", { text: `Install version ${s.latest.version}`, onclick: async () => {
          busy(`Downloading version ${s.latest.version}…`);
          try {
            const r = await api("POST", "/api/update/github");
            waitForRestart(`Installed version ${r.version}. Restarting the dashboard…`);
          } catch (e) { busy(""); fail(e); }
        } }),
        el("button", { class: "ghost", text: "Upload update file…", onclick: () => file.click() }), file,
        s.previous && el("button", { class: "ghost", text: `Go back to ${s.previous}`, onclick: async () => {
          if (!confirm(`Go back to version ${s.previous}?`)) return;
          try {
            await api("POST", "/api/update/rollback");
            waitForRestart("Going back to the previous version…");
          } catch (e) { fail(e); }
        } }),
      ].filter(Boolean));
    } catch (e) { fail(e); }
  };
  section("updates",
    card("Software", info, actions, notes,
      el("p", { class: "muted small", text: "If an update fails to start three times in a row, the dashboard automatically goes back to the previous version." })),
    fieldsCard("Update source", "updates", "The public GitHub repository that releases come from (owner/name)."));
  load(false);
}

async function renderSystem() {
  const info = el("table", { class: "info" });
  const logs = el("pre", { class: "logs", hidden: true });
  const oldPw = el("input", { type: "password", placeholder: "Current password", autocomplete: "current-password" });
  const newPw = el("input", { type: "password", placeholder: "New password", autocomplete: "new-password" });
  const restore = el("input", { type: "file", accept: ".zip", hidden: true });
  restore.addEventListener("change", async () => {
    if (!restore.files[0] || !confirm("Replace all settings and uploaded photos with this backup?")) return (restore.value = "");
    const fd = new FormData();
    fd.append("backup", restore.files[0]);
    busy("Restoring…");
    try {
      await api("POST", "/api/restore", fd);
      location.reload();
    } catch (e) { busy(""); fail(e); }
    restore.value = "";
  });
  section("system",
    card("About", info),
    card("Password", el("div", { class: "row" }, oldPw, newPw, el("button", { text: "Change password", onclick: async () => {
      try {
        await api("POST", "/api/auth/password", { old: oldPw.value, new: newPw.value });
        oldPw.value = newPw.value = "";
        toast("Password changed. Other devices have been logged out.");
      } catch (e) { fail(e); }
    } })), el("p", { class: "muted small", text: "Forgot it? Put the SD card in a computer, create an empty file named reset-password on it, and put it back." })),
    card("Backup", el("p", { class: "muted small", text: "Saves the design, settings and uploaded photos (not the password, not Drive photos)." }),
      el("div", { class: "row" }, el("a", { class: "button", href: "/api/backup", text: "Download backup" }),
        el("button", { class: "ghost", text: "Restore from backup…", onclick: () => restore.click() }), restore)),
    card("Power", el("div", { class: "row" },
      el("button", { class: "ghost", text: "Restart dashboard", onclick: async () => {
        await api("POST", "/api/system/restart").then(() => waitForRestart("Restarting the dashboard…")).catch(fail);
      } }),
      el("button", { class: "danger", text: "Reboot", onclick: async () => {
        if (!confirm("Reboot the dashboard? It takes about a minute.")) return;
        await api("POST", "/api/system/reboot").then(() => waitForRestart("Rebooting… this takes about a minute.")).catch(fail);
      } }))),
    card("Logs", el("div", { class: "row" }, el("button", { class: "ghost", text: "Show recent logs", onclick: async () => {
      try {
        logs.textContent = (await api("GET", "/api/system/logs?lines=300")).text;
        logs.hidden = false;
        logs.scrollTop = logs.scrollHeight;
      } catch (e) { fail(e); }
    } })), logs));
  try {
    const s = (S.info = await api("GET", "/api/system/info"));
    const row = (k, v) => el("tr", {}, el("td", { text: k }), el("td", { text: v }));
    const up = Math.floor(s.uptime / 60);
    info.replaceChildren(row("Version", s.version), row("Address", s.urls.join("  ")),
      row("Free space", fmtBytes(s.freeSpace)), row("Clock", s.clockSynced ? "set from the internet" : "not set yet (waiting for internet)"),
      row("Screen", s.screenOff ? "off (night schedule)" : "on"), row("Running for", up < 60 ? `${up} min` : `${Math.floor(up / 60)} h ${up % 60} min`));
  } catch (e) { fail(e); }
}

// ---------------------------------------------------------------- tabs and start-up
const RENDER = { photos: renderPhotos, display: renderDisplay, location: renderLocation, network: renderNetwork,
  updates: renderUpdates, system: renderSystem };

function showTab(name) {
  if (!$("#tab-" + name)) name = "design";
  S.tab = name;
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + name));
  if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
  if (RENDER[name]) Promise.resolve(RENDER[name]()).catch(fail);
  if (name === "design") { renderBoxes(); renderPanel(); refreshShot(); }
}
document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

async function start() {
  [S.schema, S.cfg, S.info] = await Promise.all([api("GET", "/api/schema"), api("GET", "/api/config"), api("GET", "/api/system/info")]);
  S.started = true;
  showTab(location.hash.slice(1) || "design");
  setInterval(refreshShot, 1000);
}

(async () => {
  try {
    const st = await api("GET", "/api/auth/status");
    if (st.loggedIn) await start();
    else showAuth();
  } catch (e) {
    busy("Can't reach the dashboard. Is it switched on? Retrying…");
    await sleep(3000);
    location.reload();
  }
})();
