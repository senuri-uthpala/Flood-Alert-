"use strict";

const COLORS = { Low: "#22c55e", Medium: "#f5c518", High: "#ff8a1f", Critical: "#ef3b3b" };
const LEVELS = ["Low", "Medium", "High", "Critical"];
const $ = (id) => document.getElementById(id);

// localStorage can throw (private mode, blocked site data) - never let that break the app
const ls = {
  get(k, d = null) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* ignore */ } },
};

const state = {
  lang: ls.get("lang", "si"),
  token: ls.get("token"),
  user: (() => { try { return JSON.parse(ls.get("user") || "null"); } catch { return null; } })(),
  areas: [], reports: [], forecast: {}, fcChart: null, selected: null, history: [], zones: [], nearest: null,
  alerts: [], lastAlertId: 0, seenAlertId: Number(ls.get("seenAlert", 0)) || 0,
  subs: [], geo: null, chart: null, authMode: "login", mapMode: ls.get("mapMode", "map"), tab: "areas",
};
if (!I18N[state.lang]) state.lang = "si";

const t = (k) => (I18N[state.lang] && I18N[state.lang][k]) || I18N.en[k] || k;
// Everything that comes from the server or from a user is escaped before it goes into innerHTML.
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const localeFor = () => ({ si: "si-LK", ta: "ta-LK", en: "en-GB" }[state.lang]);
const fmtTime = (iso) => {
  const d = new Date(iso + "Z"); // the API sends naive UTC timestamps
  return isNaN(d) ? "" : d.toLocaleString(localeFor(), { day: "2-digit", month: "short", hour: "numeric", minute: "2-digit" });
};

let toastTimer;
function toast(msg, isErr = false) {
  const el = $("toast");
  el.textContent = msg;
  el.className = "show" + (isErr ? " err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = ""), 3500);
}

// ---------------------------------------------------------------- icons & small illustrations
const svg = (inner) => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${inner}</svg>`;
const ICON = {
  waves: svg('<path d="M2 9c2-2 4-2 6 0s4 2 6 0 4-2 6 0M2 15c2-2 4-2 6 0s4 2 6 0 4-2 6 0"/>'),
  rain: svg('<path d="M7 15a4.5 4.5 0 1 1 1-8.9A5.5 5.5 0 0 1 19 8.5a3.5 3.5 0 0 1-.5 6.5H7"/><path d="M8 18l-1 2.5M12 18l-1 2.5M16 18l-1 2.5"/>'),
  drop: svg('<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/>'),
  bars: svg('<path d="M4 20h16"/><path d="M6 17v-4M11 17V9M16 17v-6M20 17V5"/>'),
  shield: svg('<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>'),
  warn: svg('<path d="M12 3 2 20h20z"/><path d="M12 10v5M12 17.5v.5"/>'),
  alert: svg('<circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16.5v.5"/>'),
  phone: svg('<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/>'),
  arrow: svg('<path d="M5 12h14M13 6l6 6-6 6"/>'),
};
const BUILDING = `<svg viewBox="0 0 104 78" aria-hidden="true"><defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2d77d6"/><stop offset="1" stop-color="#a9d3f7"/></linearGradient></defs>
<rect width="104" height="78" fill="url(#sky)"/><rect y="60" width="104" height="18" fill="#2f6b3a"/>
<path d="M14 36 52 18l38 18z" fill="#e9eef5"/><rect x="18" y="36" width="68" height="24" fill="#f4f1e8"/>
<g fill="#c9c3b1"><rect x="24" y="38" width="5" height="22"/><rect x="38" y="38" width="5" height="22"/><rect x="61" y="38" width="5" height="22"/><rect x="75" y="38" width="5" height="22"/></g>
<rect x="46" y="44" width="12" height="16" fill="#6b4a2f"/><rect x="10" y="60" width="84" height="4" fill="#d9d4c3"/>
<circle cx="8" cy="52" r="9" fill="#1f5a2c"/><circle cx="98" cy="54" r="8" fill="#1f5a2c"/></svg>`;

// ---------------------------------------------------------------- API
async function api(path, { method = "GET", json, form } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = "Bearer " + state.token;
  let body;
  if (json) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
  if (form) body = form;
  const r = await fetch("/api" + path, { method, headers, body });
  if (r.status === 204) return null;
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    if (r.status === 401 && state.token) logout(true);
    let msg = data && data.detail;
    if (Array.isArray(msg)) msg = msg.map((e) => e.msg).join("; ");
    throw new Error(msg || r.statusText);
  }
  return data;
}
const guard = (fn) => async (...a) => { try { return await fn(...a); } catch (e) { toast(e.message || t("error"), true); } };

// ---------------------------------------------------------------- map
let map, distLayer, maskLayer, selLayer, areaLayer, reportLayer, safeLayer, zoneLayer;
const districtShapes = {};   // name -> GeoJSON feature (real district boundaries)
const tileLayers = {};

function initMap() {
  if (typeof L === "undefined") { $("map").innerHTML = '<p class="hint" style="padding:20px">Map library unavailable offline.</p>'; return; }
  map = L.map("map", { minZoom: 6, zoomSnap: 0.5 });
  const esri = "https://server.arcgisonline.com/ArcGIS/rest/services/";
  const credit = "Tiles © Esri — Esri, HERE, Garmin, OpenStreetMap contributors, and the GIS User Community";
  tileLayers.map = L.tileLayer(esri + "Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", { maxZoom: 16, attribution: credit });
  tileLayers.mapLabels = L.tileLayer(esri + "Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}", { maxZoom: 16 });
  tileLayers.sat = L.tileLayer(esri + "World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 18, attribution: "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community" });
  tileLayers.labels = L.tileLayer(esri + "Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", { maxZoom: 18 });
  distLayer = L.layerGroup().addTo(map);   // thin outlines of every district (clickable)
  maskLayer = L.layerGroup().addTo(map);   // dims everything except the selected district
  selLayer = L.layerGroup().addTo(map);    // outline of the selected district
  areaLayer = L.layerGroup().addTo(map);
  reportLayer = L.layerGroup().addTo(map);
  safeLayer = L.layerGroup().addTo(map);
  zoneLayer = L.layerGroup();
  const SL = [[5.8, 79.4], [9.95, 82.0]];
  map.fitBounds(SL, { padding: [10, 10] });
  // the map's box is sized by CSS grid after load; re-measure and re-fit so Sri Lanka fills it
  let fitted = false;
  new ResizeObserver(() => {
    map.invalidateSize();
    if (!fitted && $("map").clientHeight > 100) { fitted = true; map.fitBounds(SL, { padding: [10, 10] }); }
  }).observe($("map"));
  const labelsByZoom = () => map.getContainer().classList.toggle("labels-off", map.getZoom() < 8);
  map.on("zoomend", () => { labelsByZoom(); renderMapAreas(); syncZoneLayer(); });
  labelsByZoom();
}

function setMapMode(mode) {
  state.mapMode = mode === "sat" ? "sat" : "map";
  ls.set("mapMode", state.mapMode);
  $("modeMap").classList.toggle("active", state.mapMode === "map");
  $("modeSat").classList.toggle("active", state.mapMode === "sat");
  $("modeMap").setAttribute("aria-pressed", String(state.mapMode === "map"));
  $("modeSat").setAttribute("aria-pressed", String(state.mapMode === "sat"));
  if (!map) return;
  Object.values(tileLayers).forEach((l) => map.hasLayer(l) && map.removeLayer(l));
  if (state.mapMode === "sat") { tileLayers.sat.addTo(map); tileLayers.labels.addTo(map); } else { tileLayers.map.addTo(map); tileLayers.mapLabels.addTo(map); }
}

function renderLegend() {
  $("legend").innerHTML = `<b>${esc(t("legend"))}:</b>` +
    LEVELS.map((l) => `<span><i style="background:${COLORS[l]};color:${COLORS[l]}"></i>${esc(t(l))}</span>`).join("");
}

async function loadDistricts() {
  try {
    const gj = await (await fetch("/data/districts.geojson")).json();
    gj.features.forEach((f) => { districtShapes[f.properties.name] = f; });
    L.geoJSON(gj, {
      style: { color: "#8fb8ff", weight: 1, opacity: 0.28, fillColor: "#000", fillOpacity: 0 },
      attribution: "District boundaries © geoBoundaries (CC BY 4.0)",
      onEachFeature: (f, layer) => {
        layer.on("click", () => { const a = state.areas.find((x) => x.name === f.properties.name); if (a) selectArea(a.id); });
        layer.bindTooltip(esc(f.properties.name), { sticky: true, className: "area-hover" });
      },
    }).addTo(distLayer);
    drawSelection();
  } catch { /* boundaries are optional - the circles still work */ }
}

// cut the selected district out of the map: everything else is dimmed, the district gets a bright outline
function drawSelection() {
  if (!map || !maskLayer) return null;
  maskLayer.clearLayers(); selLayer.clearLayers();
  const a = selArea(), f = a && districtShapes[a.name];
  if (!f) return null;
  const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
  const holes = polys.map((p) => p[0].map(([lng, lat]) => [lat, lng]));
  L.polygon([[[-85, -180], [-85, 180], [85, 180], [85, -180]], ...holes],
    { stroke: false, fillColor: "#020a1c", fillOpacity: 0.62, interactive: false, className: "district-mask" }).addTo(maskLayer);
  const outline = L.geoJSON(f, { style: { color: COLORS[a.risk_level], weight: 3, fillColor: COLORS[a.risk_level], fillOpacity: 0.08 }, interactive: false }).addTo(selLayer);
  return outline.getBounds();
}

const ZONE_COLORS = { shelter: "#22c55e", school: "#38bdf8", hospital: "#f43f5e", temple: "#f59e0b" };
const ZOOMED_IN = 9;   // from this zoom on the map focuses on the selected district

function renderMapAreas() {
  if (!areaLayer) return;
  areaLayer.clearLayers();
  const zoomedIn = map.getZoom() >= ZOOMED_IN;
  state.areas.forEach((a) => {
    const c = COLORS[a.risk_level], sel = a.id === state.selected;
    const quiet = zoomedIn && !sel;   // other districts fade into the background when you are looking at one
    const ring = L.circle([a.lat, a.lng], {
      radius: quiet ? 2500 : zoomedIn ? 7000 : 9000 + a.risk_score * 160,
      color: c, weight: sel ? 3 : quiet ? 1 : 1.5, opacity: quiet ? 0.45 : 0.9, fillColor: c,
      fillOpacity: sel ? 0.3 : quiet ? 0.05 : 0.22, className: "area-ring" + (sel ? " sel" : ""),
    }).addTo(areaLayer);
    const dot = L.circleMarker([a.lat, a.lng], { radius: quiet ? 3 : 5, color: "#fff", weight: quiet ? 1 : 1.5, fillColor: c, fillOpacity: 1 }).addTo(areaLayer);
    ring.bindTooltip(`${esc(a.name)} · ${esc(t("risk_" + a.risk_level))} (${a.risk_score})`, { sticky: true, className: "area-hover" });
    dot.bindTooltip(esc(a.name), { permanent: !quiet, direction: "bottom", offset: [0, quiet ? 4 : 6], className: `area-label lv-${a.risk_level}${sel ? " sel" : ""}` });
    [ring, dot].forEach((l) => l.on("click", () => selectArea(a.id)));
  });
}

// the selected district's real safe places (hospitals, schools, ...) - only when zoomed in
function drawZoneMarkers() {
  if (!zoneLayer) return;
  zoneLayer.clearLayers();
  state.zones.forEach((z) => {
    const col = ZONE_COLORS[z.kind] || "#22c55e";
    L.circleMarker([z.lat, z.lng], { radius: 7, color: "#fff", weight: 1.5, fillColor: col, fillOpacity: 1 }).addTo(zoneLayer)
      .bindTooltip(`${esc(z.name)} · ${esc(kindLabel(z.kind))}`, { direction: "top", offset: [0, -6], className: "area-hover" })
      .bindPopup(`<b>${esc(z.name)}</b><br>${esc(kindLabel(z.kind))}${z.is_sample ? " · " + esc(t("sample")) : ""}<br><a href="${esc(directionsUrl(z))}" target="_blank" rel="noopener">${esc(t("directions"))} ↗</a>`);
  });
  syncZoneLayer();
}
function syncZoneLayer() {
  if (!zoneLayer || !map) return;
  const show = map.getZoom() >= ZOOMED_IN;
  if (show && !map.hasLayer(zoneLayer)) zoneLayer.addTo(map);
  if (!show && map.hasLayer(zoneLayer)) map.removeLayer(zoneLayer);
}

// ---------------------------------------------------------------- language / auth chrome
function applyLang() {
  document.documentElement.lang = state.lang;
  $("langSel").value = state.lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => (el.textContent = t(el.dataset.i18n)));
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => (el.placeholder = t(el.dataset.i18nPh)));
  $("repType").options[0].textContent = t("flood");
  $("repType").options[1].textContent = t("landslide");
  [...$("bcLevel").options].forEach((o) => {   // keep the English value, translate only the label
    if (!o.hasAttribute("value")) o.setAttribute("value", o.textContent.trim());
    o.textContent = t(o.value);
  });
  $("tileCritLabel").textContent = t("Critical");
  $("bellBtn").setAttribute("aria-label", t("alerts"));
  $("subLang").value = state.lang;
  renderLegend();
  renderAuthBtn();
  renderAuthDialog();
  chanNote();
}

function renderAuthBtn() {
  const u = state.user;
  $("authLabel").textContent = u ? u.name.split(" ")[0] : t("login");
  $("authBtn").title = u ? t("account") : "";
  $("adminTabBtn").hidden = !(u && u.role === "admin");
  $("accountBody").innerHTML = u
    ? `<p class="hint">${esc(t("signed_in_as"))} <b>${esc(u.name)}</b><br>${esc(u.email)} · ${esc(u.role)}</p>
       <button class="ghost" type="button" data-act="logout">${esc(t("logout"))}</button>`
    : `<p class="hint">${esc(t("not_signed_in"))}</p><button class="primary" type="button" data-act="login">${esc(t("login"))}</button>`;
}

function setSession(token, user) {
  state.token = token; state.user = user;
  if (token) { ls.set("token", token); ls.set("user", JSON.stringify(user)); } else { ls.del("token"); ls.del("user"); }
  renderAuthBtn();
}

function logout(expired = false) {
  setSession(null, null);
  state.subs = [];
  renderSubs();
  if (expired) toast(t("login_required"), true);
  if (state.tab === "admin") showTab("areas");
}

function renderAuthDialog() {
  const reg = state.authMode === "register";
  $("authTitle").textContent = reg ? t("register") : t("login");
  $("authSubmit").textContent = reg ? t("register") : t("login");
  $("auName").hidden = !reg; $("auName").required = reg;
  $("auPhone").hidden = !reg;
  $("auPass").autocomplete = reg ? "new-password" : "current-password";
  $("authSwitchText").textContent = reg ? t("have_account") : t("no_account");
  $("authSwitch").textContent = reg ? t("login") : t("register");
}
function openAuth() { renderAuthDialog(); $("authDlg").showModal(); }

// ---------------------------------------------------------------- areas (dashboard)
const selArea = () => state.areas.find((a) => a.id === state.selected);

async function loadAreas() {
  try {
    state.areas = await api("/areas");
    ls.set("cache:areas", JSON.stringify(state.areas));
  } catch (e) {
    const cached = ls.get("cache:areas");
    if (!cached) return toast(e.message, true);
    state.areas = JSON.parse(cached);  // offline: show the last saved data
  }
  if (state.selected == null && state.areas.length) {
    const remembered = Number(ls.get("area"));
    state.selected = state.areas.some((a) => a.id === remembered) ? remembered : state.areas[0].id; // API sorts by risk, highest first
    $("areaPick").dataset.first = "1";
  }
  fillSelects();
  renderTiles();
  renderMapAreas();
  await selectArea(state.selected, false);
}

function fillSelects() {
  const sorted = [...state.areas].sort((a, b) => a.name.localeCompare(b.name));
  $("areaPick").innerHTML = sorted.map((a) => `<option value="${a.id}">${esc(a.name)} ${esc(t("district"))}</option>`).join("");
  if (state.selected != null) $("areaPick").value = state.selected;
  const plain = sorted.map((a) => `<option value="${a.id}">${esc(a.name)}</option>`).join("");
  for (const id of ["repArea", "subArea", "bcArea", "fcA"]) {
    const el = $(id), prev = el.value;
    el.innerHTML = plain;
    if (prev) el.value = prev;
  }
  const prevB = $("fcB").value, prevF = $("feedArea").value;
  $("fcB").innerHTML = `<option value="">${esc(t("fc_none"))}</option>` + plain;
  $("fcB").value = prevB;
  $("feedArea").innerHTML = `<option value="">${esc(t("feed_all"))}</option>` + plain;
  $("feedArea").value = prevF;
  if (!$("fcA").value && state.selected != null) $("fcA").value = state.selected;
}

function renderTiles() {
  const by = (lv) => state.areas.filter((a) => a.risk_level === lv).length;
  $("tileTotal").textContent = state.areas.length;
  $("tileSafe").textContent = by("Low");
  $("tileRisk").textContent = by("Medium") + by("High");
  $("tileCrit").textContent = by("Critical");
}

function renderAreaBadge() {
  const a = selArea(), b = $("areaBadge");
  b.className = "badge" + (a ? " " + a.risk_level : "");
  b.textContent = a ? t("risk_" + a.risk_level) : "";
}

const metric = (cls, icon, value, unit, label, extra = "") =>
  `<div class="metric ${cls}"><div class="mi">${ICON[icon]}</div><b>${value}${unit ? `<small> ${esc(unit)}</small>` : ""}</b><span>${esc(label)}${extra}</span></div>`;

function renderDetail() {
  const a = selArea();
  if (!a) { $("detail").innerHTML = ""; return; }
  const last = state.history[state.history.length - 1];
  const prev = state.history.length > 1 ? state.history[state.history.length - 2] : null;
  const v = (x) => (last ? x : "-");
  const up = !prev || a.risk_score >= prev.risk_score;
  const trend = `<svg class="i trend ${up ? "up" : "down"}" viewBox="0 0 24 24"><path d="${up ? "M3 17l6-6 4 4 8-8M15 7h6v6" : "M3 7l6 6 4-4 8 8M15 17h6v-6"}"/></svg>`;
  $("detail").innerHTML = `
    <div class="metrics">
      ${metric("m-blue", "waves", a.risk_score, "/ 100", t("score"), trend)}
      ${metric("m-sky", "rain", v(last && last.rainfall_24h), t("mm"), t("rain24"))}
      ${metric("m-green", "drop", v(last && last.rainfall_72h), t("mm"), t("rain72"))}
      ${metric("m-purple", "bars", v(last && last.forecast_24h), t("mm"), t("forecast"))}
    </div>
    ${a.ml_probability != null ? `<div class="ml"><span class="chip">AI</span>${esc(t("ml_prob"))}: <b>${Math.round(a.ml_probability * 100)}%</b></div>` : ""}`;
  const times = state.areas.map((x) => x.updated_at).filter(Boolean).sort();
  $("lastUpd").textContent = times.length ? fmtTime(times[times.length - 1]) : "-";
}

function drawChart(rows) {
  const box = $("chartBox"), canvas = $("chart");
  let empty = $("chartEmpty");
  if (state.chart) { state.chart.destroy(); state.chart = null; }
  if (!rows.length || typeof Chart === "undefined") {
    canvas.hidden = true;
    if (!empty) { empty = document.createElement("div"); empty.id = "chartEmpty"; box.appendChild(empty); }
    empty.hidden = false;
    empty.textContent = typeof Chart === "undefined" ? "Chart library unavailable offline." : t("no_history");
    return;
  }
  if (empty) empty.hidden = true;
  canvas.hidden = false;
  Chart.defaults.color = "#9dbbe6";
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  const grid = "rgba(120, 170, 255, .13)", dots = rows.length > 40 ? 0 : 3;
  state.chart = new Chart(canvas, {
    type: "line",
    data: {
      labels: rows.map((r) => fmtTime(r.recorded_at)),
      datasets: [
        { label: t("rain72"), data: rows.map((r) => r.rainfall_72h), borderColor: "#3da5ff", backgroundColor: "rgba(61,165,255,.14)", pointBackgroundColor: "#3da5ff", fill: true, tension: 0.3, pointRadius: dots, yAxisID: "y" },
        { label: t("forecast"), data: rows.map((r) => r.forecast_24h), borderColor: "#7dd3fc", borderDash: [6, 4], pointBackgroundColor: "#7dd3fc", tension: 0.3, pointRadius: dots, yAxisID: "y" },
        { label: t("score"), data: rows.map((r) => r.risk_score), borderColor: "#ff4d4d", pointBackgroundColor: "#ff4d4d", tension: 0.3, pointRadius: dots, yAxisID: "y2" },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { usePointStyle: true, boxWidth: 8, font: { size: 11 } } } },
      scales: {
        x: { ticks: { maxTicksLimit: 5, font: { size: 10 } }, grid: { color: grid } },
        y: { beginAtZero: true, title: { display: true, text: t("rain_axis") }, grid: { color: grid } },
        y2: { position: "right", min: 0, max: 100, title: { display: true, text: t("score") }, grid: { drawOnChartArea: false } },
      },
    },
  });
}

const selectArea = guard(async (id, fly = true) => {
  const a = state.areas.find((x) => x.id === id);
  if (!a) return;
  state.selected = id;
  ls.set("area", String(id));
  $("areaPick").value = id;
  if (fly && state.tab !== "areas") showTab("areas");
  renderAreaBadge();
  renderMapAreas();
  const bounds = drawSelection();
  if (fly && map) {
    if (bounds && bounds.isValid()) map.flyToBounds(bounds, { padding: [30, 30], maxZoom: 11, duration: 0.8 });
    else map.flyTo([a.lat, a.lng], 10, { duration: 0.8 });
  }
  const [history, zones] = await Promise.all([
    api(`/areas/${id}/history?hours=72`).catch(() => []),
    api(`/areas/${id}/safe-zones`).catch(() => []),
  ]);
  if (state.selected !== id) return;  // the user picked another district meanwhile
  state.history = history; state.zones = zones;
  renderDetail(); drawChart(history); renderZoneCard(); renderSafeList(); renderBanner(); renderEmerg(); drawZoneMarkers();
  $("fcA").value = id;
  if (state.tab === "forecast") renderForecast();
});

// ---------------------------------------------------------------- safe zones
function directionsUrl(z) {
  return state.geo
    ? `https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route=${state.geo.lat}%2C${state.geo.lng}%3B${z.lat}%2C${z.lng}`
    : `https://www.openstreetmap.org/?mlat=${z.lat}&mlon=${z.lng}#map=15/${z.lat}/${z.lng}`;
}
const kindLabel = (k) => (I18N.en[k] ? t(k) : k);

function renderZoneCard() {
  const body = $("zoneBody"), zs = state.zones;
  if (!zs.length) { body.innerHTML = `<p class="hint">${esc(t("no_zones"))}</p>`; return; }
  const z = zs[0];
  body.innerHTML = `<div class="zone"><div class="zthumb"><img src="/img/zone.jpg" alt="" onerror="this.replaceWith(Object.assign(document.createElement('span'),{innerHTML:BUILDING}))"></div><div>
      <div class="zname">${esc(z.name)}</div>
      <div class="tags"><span class="tag blue">${esc(kindLabel(z.kind))}</span>${z.is_sample ? `<span class="tag warn">${esc(t("sample"))}</span>` : ""}</div>
      ${z.is_sample ? "" : `<div class="osm-note">${esc(t("osm_note"))}</div>`}
      <a class="dir" href="${esc(directionsUrl(z))}" target="_blank" rel="noopener">${esc(t("directions"))} ${ICON.arrow}</a>
      ${zs.length > 1 ? `<button class="morezones" type="button" data-act="tab" data-tab="safe">${esc(t("more_zones").replace("{n}", zs.length - 1))}</button>` : ""}
    </div></div>`;
}

function zoneItemHtml(z) {
  return `<div class="item">
    <div class="name">${esc(z.name)} <span class="tag blue">${esc(kindLabel(z.kind))}</span>${z.is_sample ? `<span class="tag warn">${esc(t("sample"))}</span>` : ""}</div>
    <div class="sub">${z.distance_km != null ? z.distance_km + " " + esc(t("km")) + " · " : ""}${z.capacity ? esc(t("capacity")) + ": " + z.capacity + " · " : ""}${z.phone ? esc(z.phone) + " · " : ""}
      <a href="${esc(directionsUrl(z))}" target="_blank" rel="noopener">${esc(t("directions"))} ↗</a></div>
    ${z.is_sample ? `<div class="sub">${esc(t("sample_zone"))}</div>` : ""}</div>`;
}
function renderSafeList() {
  const zs = state.nearest || state.zones;
  $("safeList").innerHTML = zs.length ? zs.map(zoneItemHtml).join("") : `<p class="hint">${esc(t("no_zones"))}</p>`;
}

function getPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error("Geolocation not supported"));
    navigator.geolocation.getCurrentPosition(
      (p) => { state.geo = { lat: p.coords.latitude, lng: p.coords.longitude }; resolve(state.geo); },
      (e) => reject(new Error(e.message)), { enableHighAccuracy: true, timeout: 12000 });
  });
}

const findSafe = guard(async () => {
  const { lat, lng } = await getPosition();
  state.nearest = await api(`/safe-zones/nearest?lat=${lat}&lng=${lng}&limit=5`);
  renderSafeList(); renderZoneCard();
  if (!map) return;
  safeLayer.clearLayers();
  L.circleMarker([lat, lng], { radius: 8, color: "#fff", weight: 2, fillColor: "#2f8cff", fillOpacity: 1 }).addTo(safeLayer);
  // circle markers (not image icons) so they also render offline
  state.nearest.forEach((z) => L.circleMarker([z.lat, z.lng], { radius: 9, color: "#14532d", weight: 2, fillColor: "#22c55e", fillOpacity: 1 })
    .addTo(safeLayer).bindPopup(esc(z.name)));
  map.fitBounds(L.latLngBounds([[lat, lng], ...state.nearest.map((z) => [z.lat, z.lng])]).pad(0.3));
});

// ---------------------------------------------------------------- alerts, bell, banner
function alertHtml(a) {
  return `<div class="item"><div class="name">${esc(a.area_name)} <span class="badge ${a.level}">${esc(t("risk_" + a.level))}</span>
    ${a.manual ? `<span class="tag">${esc(t("manual_alert"))}</span>` : ""}</div>
    <div>${esc(a["message_" + state.lang])}</div><div class="sub">${esc(fmtTime(a.sent_at))}</div>
    <button class="ghost small" type="button" data-act="sharealert" data-id="${a.id}" style="margin-top:6px">${esc(t("share_alert"))}</button></div>`;
}
function renderAlerts() {
  $("alertList").innerHTML = state.alerts.length ? state.alerts.map(alertHtml).join("") : `<p class="hint">${esc(t("no_alerts"))}</p>`;
}

function renderBanner() {
  const a = state.alerts.find((x) => x.area_id === state.selected) || state.alerts[0];
  const el = $("alertBanner");
  el.className = "banner " + (a ? "lv-" + a.level : "calm");
  el.querySelector(".b-icon").innerHTML = a && a.level === "Critical" ? ICON.alert : ICON.warn;
  if (!a) {
    const ar = selArea();
    $("bannerTitle").textContent = t("flood_alert");
    $("bannerMsg").textContent = ar ? t("banner_default").replace("{level}", t("risk_" + ar.risk_level)).replace("{area}", ar.name) : t("no_alert_msg");
    $("bannerIssued").innerHTML = ar && ar.updated_at ? `${esc(t("issued_at"))}<b>${esc(fmtTime(ar.updated_at))}</b>` : "";
    return;
  }
  $("bannerTitle").textContent = a.manual ? t("manual_alert") : t("flood_alert");
  $("bannerMsg").textContent = a["message_" + state.lang];
  $("bannerIssued").innerHTML = `${esc(t("issued_at"))}<b>${esc(fmtTime(a.sent_at))}</b>`;
}

function renderBell() {
  const dayAgo = Date.now() - 24 * 3600 * 1000;
  const n = state.alerts.filter((a) => a.id > state.seenAlertId && new Date(a.sent_at + "Z").getTime() > dayAgo).length;
  const day = state.alerts.filter((a) => new Date(a.sent_at + "Z").getTime() > dayAgo).length;
  $("navAlertCount").hidden = day === 0;
  $("navAlertCount").textContent = day > 9 ? "9+" : String(day);
  $("bellBadge").hidden = n === 0;
  $("bellBadge").textContent = n > 9 ? "9+" : String(n);
}
function markSeen() {
  state.seenAlertId = Math.max(state.seenAlertId, state.lastAlertId);
  ls.set("seenAlert", String(state.seenAlertId));
  renderBell();
}

const loadAlerts = guard(async () => {
  state.alerts = await api("/alerts?limit=30");
  state.lastAlertId = state.alerts.reduce((m, a) => Math.max(m, a.id), 0);
  renderAlerts(); renderBanner(); renderBell();
});

async function pollAlerts() {
  try {
    const fresh = await api(`/alerts?since_id=${state.lastAlertId}&limit=10`);
    if (!fresh.length) return;
    state.lastAlertId = Math.max(state.lastAlertId, ...fresh.map((a) => a.id));
    state.alerts = [...fresh, ...state.alerts].slice(0, 50);
    renderAlerts(); renderBanner(); renderBell();
    if (state.tab === "alerts") markSeen();
    loadAreas();
    fresh.forEach((a) => {
      const mine = state.subs.some((s) => s.area_id === a.area_id);
      if (!mine && a.level !== "Critical") return;
      toast(`${t("new_alert")}: ${a["message_" + state.lang]}`, a.level === "Critical");
      if ("Notification" in window && Notification.permission === "granted") {
        new Notification("FloodAlert LK · " + a.area_name, { body: a["message_" + state.lang], icon: "/icon.svg" });
      }
    });
  } catch { /* offline - try again on the next tick */ }
}

// ---------------------------------------------------------------- reports & subscriptions
const loadReports = guard(async () => {
  if (!reportLayer) return;
  const rows = await api("/reports?limit=100");
  state.reports = rows;
  renderFeed();
  reportLayer.clearLayers();
  rows.filter((r) => r.lat != null).forEach((r) => {
    L.circleMarker([r.lat, r.lng], { radius: 6, color: "#e9d5ff", weight: 1.5, fillColor: "#a855d6", fillOpacity: 0.95 }).addTo(reportLayer)
      .bindPopup(`<b>${esc(r.type === "flood" ? t("flood") : t("landslide"))}</b> · ${esc(r.area_name)}<br>${esc(r.description || "")}` +
        (r.photo_url ? `<br><img src="${esc(r.photo_url)}" alt="" style="max-width:180px;margin-top:4px;border-radius:6px">` : ""));
  });
});

function renderFeed() {
  const sel = $("feedArea").value;
  const rows = state.reports.filter((r) => !sel || String(r.area_id) === sel);
  $("feedList").innerHTML = rows.length ? rows.map((r) => `
    <div class="item feed">
      ${r.photo_url ? `<img src="${esc(r.photo_url)}" alt="" loading="lazy">` : `<div class="ph">${ICON.warn}</div>`}
      <div><div class="name">${esc(r.type === "flood" ? t("flood") : t("landslide"))} · ${esc(r.area_name)} <span class="tag blue">${esc(t("feed_verified"))}</span></div>
        ${r.description ? `<div>${esc(r.description)}</div>` : ""}<div class="sub">${esc(fmtTime(r.created_at))}</div>
        ${r.lat != null ? `<button class="ghost small go" type="button" data-act="feedgo" data-id="${r.id}">${esc(t("feed_show"))}</button>` : ""}</div>
    </div>`).join("") : `<p class="hint">${esc(t("feed_empty"))}</p>`;
}

// ---------------------------------------------------------------- emergency contacts, "I'm safe", sharing
const EMERG = [["117", "emerg_dmc"], ["119", "emerg_police"], ["110", "emerg_fire"], ["1990", "emerg_amb"], ["1919", "emerg_gov"]];
function renderEmerg() {
  $("emergList").innerHTML = EMERG.map(([n, k]) =>
    `<a class="contact" href="tel:${n}"><span>${esc(t(k))}</span><b>${ICON.phone} ${n}</b></a>`).join("");
  const h = state.zones.find((z) => z.kind === "hospital");
  const tel = h && h.phone ? h.phone.replace(/[^+\d]/g, "") : "";
  $("emergHosp").innerHTML = h ? `<div class="hint">${esc(t("emerg_hosp"))}</div><div class="item"><div class="name">${esc(h.name)}</div>
    <div class="sub">${tel ? `<a href="tel:${esc(tel)}">${esc(h.phone)}</a> · ` : ""}<a href="${esc(directionsUrl(h))}" target="_blank" rel="noopener">${esc(t("directions"))} ↗</a></div></div>` : "";
}

function safeMessage(loc) {
  const a = selArea();
  const name = $("safeName").value.trim() || (state.user && state.user.name) || "";
  const time = new Date().toLocaleString(localeFor(), { day: "2-digit", month: "short", hour: "numeric", minute: "2-digit" });
  let m = t("safe_msg");
  if (!name) m = m.replace("{name}, ", "");
  return m.replace("{name}", name).replace("{area}", a ? a.name : "").replace("{time}", time)
    .replace("{loc}", loc ? loc + " " : "").replace(/\s+/g, " ").trim();
}
async function composeSafe() {
  let loc = "";
  if ($("safeLoc").checked) {
    try { const g = await getPosition(); loc = `https://www.openstreetmap.org/?mlat=${g.lat}&mlon=${g.lng}#map=16/${g.lat}/${g.lng}`; }
    catch (e) { toast(e.message, true); }
  }
  return safeMessage(loc);
}
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); toast(t("copied")); }
  catch { window.prompt("", text); }
}
async function shareText(text) {
  if (navigator.share) { try { await navigator.share({ text }); return; } catch (e) { if (e && e.name === "AbortError") return; } }
  window.open("https://wa.me/?text=" + encodeURIComponent(text), "_blank", "noopener");
}

// ---------------------------------------------------------------- 3-day forecast + compare
const loadForecast = guard(async () => { state.forecast = await api("/forecast"); renderForecast(); });
function dayLabel(iso, i) {
  if (i === 0) return t("fc_today");
  if (i === 1) return t("fc_tomorrow");
  return new Date(iso + "T00:00:00").toLocaleDateString(localeFor(), { weekday: "short", day: "numeric", month: "short" });
}
function renderForecast() {
  const ids = [$("fcA").value, $("fcB").value].filter(Boolean);
  const data = ids.map((id) => ({ a: state.areas.find((x) => String(x.id) === id), days: state.forecast[id] })).filter((d) => d.a && d.days && d.days.length);
  if (state.fcChart) { state.fcChart.destroy(); state.fcChart = null; }
  if (!data.length) {
    $("fcDays").innerHTML = `<p class="hint">${esc(t("fc_empty"))}</p>`;
  } else {
    $("fcDays").innerHTML = data.map((d) => `<div class="fchead">${esc(d.a.name)}</div>` + d.days.map((x, i) => `
      <div class="fcday"><span class="d">${esc(dayLabel(x.date, i))}</span><b>${x.rain_mm} ${esc(t("mm"))}</b>
        <span class="badge ${x.risk_level}">${esc(t("risk_" + x.risk_level))}</span></div>`).join("")).join("");
    if (typeof Chart !== "undefined") {
      Chart.defaults.color = "#9dbbe6";
      const colors = ["#3da5ff", "#f5c518"];
      state.fcChart = new Chart($("fcChart"), {
        type: "bar",
        data: { labels: data[0].days.map((x, i) => dayLabel(x.date, i)),
          datasets: data.map((d, i) => ({ label: d.a.name, data: d.days.map((x) => x.rain_mm), backgroundColor: colors[i], borderRadius: 6 })) },
        options: { responsive: true, maintainAspectRatio: false,
          plugins: { legend: { labels: { usePointStyle: true, boxWidth: 8, font: { size: 11 } } } },
          scales: { x: { grid: { display: false } }, y: { beginAtZero: true, title: { display: true, text: t("fc_rain") }, grid: { color: "rgba(120,170,255,.13)" } } } },
      });
    }
  }
  const ranked = Object.entries(state.forecast).map(([id, days]) => {
    const peakIdx = days.reduce((b, x, i) => (x.risk_score > days[b].risk_score ? i : b), 0);
    return { a: state.areas.find((x) => String(x.id) === id), peak: days[peakIdx], i: peakIdx };
  }).filter((r) => r.a && r.peak).sort((x, y) => y.peak.risk_score - x.peak.risk_score).slice(0, 5);
  $("fcTop").innerHTML = ranked.map((r) => `<div class="item row-between"><div><div class="name">${esc(r.a.name)}</div>
      <div class="sub">${esc(t("fc_peak"))}: ${esc(dayLabel(r.peak.date, r.i))} · ${r.peak.rain_mm} ${esc(t("mm"))} · ${r.peak.risk_score}/100</div></div>
      <button class="ghost small" type="button" data-act="fcpick" data-id="${r.a.id}"><span class="badge ${r.peak.risk_level}">${esc(t("risk_" + r.peak.risk_level))}</span></button></div>`).join("");
}

function nearestAreaId(lat, lng) {
  let best = null, bd = Infinity;
  for (const a of state.areas) {
    const d = (a.lat - lat) ** 2 + (a.lng - lng) ** 2;
    if (d < bd) { bd = d; best = a.id; }
  }
  return best;
}

async function requireLogin() {
  if (state.token) return true;
  toast(t("login_required"), true);
  openAuth();
  return false;
}

function renderSubs() {
  const name = (id) => (state.areas.find((a) => a.id === id) || {}).name || id;
  $("mySubs").innerHTML = state.subs.map((s) => `
    <div class="item row-between"><div><div class="name">${esc(name(s.area_id))}</div>
      <div class="sub">${esc(s.channel)} · ${esc(s.contact)} · ${esc(s.language)}</div></div>
      <button class="ghost small" type="button" data-act="unsub" data-id="${s.id}">${esc(t("remove"))}</button></div>`).join("");
}
const loadSubs = guard(async () => {
  if (!state.token) { state.subs = []; return renderSubs(); }
  state.subs = await api("/subscriptions");
  renderSubs();
});

// ---------------------------------------------------------------- admin
const loadAdmin = guard(async () => {
  const [pending, stats] = await Promise.all([api("/reports?status=pending"), api("/admin/stats")]);
  $("pending").innerHTML = pending.length ? pending.map((r) => `
    <div class="item"><div class="name">${esc(r.area_name)} · ${esc(r.type === "flood" ? t("flood") : t("landslide"))}</div>
      <div>${esc(r.description || "")}</div><div class="sub">${esc(fmtTime(r.created_at))}</div>
      ${r.photo_url ? `<img src="${esc(r.photo_url)}" alt="">` : ""}
      <div class="row" style="margin-top:8px">
        <button class="primary small" type="button" data-act="mod" data-do="verify" data-id="${r.id}">${esc(t("verify"))}</button>
        <button class="ghost small" type="button" data-act="mod" data-do="reject" data-id="${r.id}">${esc(t("reject"))}</button></div></div>`).join("")
    : `<p class="hint">${esc(t("no_pending"))}</p>`;
  $("stats").textContent = `users ${stats.users} · subscriptions ${stats.subscriptions} · alerts ${stats.alerts_sent} · ` +
    `reports: ${stats.reports.pending} pending / ${stats.reports.verified} verified / ${stats.reports.rejected} rejected`;
});

// ---------------------------------------------------------------- tabs & events
function showTab(name, scroll = false) {
  state.tab = name;
  document.querySelectorAll("#tabs button[data-tab]").forEach((b) => {
    const on = b.dataset.tab === name;
    b.classList.toggle("active", on);
    if (on) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  document.querySelectorAll("#panel .tab").forEach((s) => s.classList.toggle("active", s.id === "tab-" + name));
  if (name === "alerts") loadAlerts().then(markSeen);
  if (name === "settings") loadSubs();
  if (name === "forecast") loadForecast();
  if (name === "report") loadReports();
  if (name === "safe") renderEmerg();
  if (name === "admin") loadAdmin();
  $("panel").scrollTop = 0;
  if (scroll && window.matchMedia("(max-width: 860px)").matches) $("panel").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderAll() {
  fillSelects(); renderAreaBadge(); renderTiles(); renderMapAreas(); renderDetail(); drawChart(state.history);
  renderZoneCard(); renderSafeList(); renderBanner(); renderAlerts(); renderSubs(); renderBell();
  renderEmerg(); renderFeed(); if (state.tab === "forecast") renderForecast();
}

document.addEventListener("click", guard(async (e) => {
  const b = e.target.closest("[data-act]");
  if (!b) return;
  const act = b.dataset.act, id = +b.dataset.id;
  if (act === "unsub") { await api(`/subscriptions/${id}`, { method: "DELETE" }); await loadSubs(); }
  if (act === "mod") {
    await api(`/reports/${id}/${b.dataset.do}`, { method: "POST" });
    await Promise.all([loadAdmin(), loadReports(), loadAreas()]);
  }
  if (act === "logout") { logout(); toast("✔"); }
  if (act === "login") openAuth();
  if (act === "sharealert") {
    const al = state.alerts.find((x) => x.id === id);
    if (al) await shareText(t("alert_share_msg").replace("{area}", al.area_name).replace("{msg}", al["message_" + state.lang]));
  }
  if (act === "feedgo") {
    const r = state.reports.find((x) => x.id === id);
    if (r && map) { map.flyTo([r.lat, r.lng], 13, { duration: 0.8 }); $("mapWrap").scrollIntoView({ behavior: "smooth", block: "start" }); }
  }
  if (act === "fcpick") { $("fcA").value = id; renderForecast(); }
  if (act === "tab") showTab(b.dataset.tab, true);
}));

$("tabs").addEventListener("click", (e) => { const b = e.target.closest("button[data-tab]"); if (b) showTab(b.dataset.tab, true); });
$("areaPick").addEventListener("change", (e) => selectArea(+e.target.value));
$("modeMap").addEventListener("click", () => setMapMode("map"));
$("modeSat").addEventListener("click", () => setMapMode("sat"));
$("bellBtn").addEventListener("click", () => showTab("alerts", true));
$("bannerBtn").addEventListener("click", () => showTab("alerts", true));
$("langSel").addEventListener("change", (e) => {
  state.lang = e.target.value; ls.set("lang", state.lang);
  applyLang(); renderAll();
});

$("authBtn").addEventListener("click", () => (state.user ? showTab("settings", true) : openAuth()));
$("authCancel").addEventListener("click", () => $("authDlg").close());
$("authSwitch").addEventListener("click", (e) => { e.preventDefault(); state.authMode = state.authMode === "login" ? "register" : "login"; renderAuthDialog(); });
$("authForm").addEventListener("submit", guard(async (e) => {
  e.preventDefault();
  const reg = state.authMode === "register";
  const payload = { email: $("auEmail").value, password: $("auPass").value };
  if (reg) Object.assign(payload, { name: $("auName").value, phone: $("auPhone").value || null, language: state.lang });
  const data = await api(reg ? "/auth/register" : "/auth/login", { method: "POST", json: payload });
  setSession(data.access_token, data.user);
  state.authMode = "login";  // next time the dialog opens it starts on "log in"
  $("authDlg").close(); $("authForm").reset();
  toast("✔ " + data.user.name);
  loadSubs();
}));

$("locBtn").addEventListener("click", guard(async () => {
  const { lat, lng } = await getPosition();
  $("repArea").value = nearestAreaId(lat, lng);
  toast(t("location_set"));
}));

$("reportForm").addEventListener("submit", guard(async (e) => {
  e.preventDefault();
  if (!(await requireLogin())) return;
  const f = new FormData();
  f.append("area_id", $("repArea").value);
  f.append("type", $("repType").value);
  if ($("repDesc").value.trim()) f.append("description", $("repDesc").value.trim());
  if (state.geo) { f.append("lat", state.geo.lat); f.append("lng", state.geo.lng); }
  if ($("repPhoto").files[0]) f.append("photo", $("repPhoto").files[0]);
  await api("/reports", { method: "POST", form: f });
  $("reportForm").reset();
  toast(t("report_sent"));
  loadReports(); loadAreas();
}));

$("subForm").addEventListener("submit", guard(async (e) => {
  e.preventDefault();
  if (!(await requireLogin())) return;
  await api("/subscriptions", { method: "POST", json: {
    area_id: +$("subArea").value, channel: $("subChannel").value, contact: $("subContact").value.trim(), language: $("subLang").value } });
  toast(t("subscribed")); $("subContact").value = ""; loadSubs();
}));

$("notifBtn").addEventListener("click", guard(async () => {
  if (!("Notification" in window)) throw new Error(t("notifs_unsupported"));
  if (Notification.permission === "denied") throw new Error(t("notifs_denied"));
  const perm = await Notification.requestPermission();
  if (perm !== "granted") throw new Error(t("notifs_denied"));
  toast(t("notifs_on"));
  new Notification("FloodAlert LK", { body: t("notifs_test"), icon: "/icon.svg" });   // proves it works right now
}));
function chanNote() {
  const k = { sms: "sms_note", email: "email_note", push: "push_note" }[$("subChannel").value];
  $("chanNote").textContent = k ? t(k) : "";
}
$("subChannel").addEventListener("change", chanNote);
$("findSafeBtn").addEventListener("click", findSafe);
$("fcA").addEventListener("change", renderForecast);
$("fcB").addEventListener("change", renderForecast);
$("feedArea").addEventListener("change", renderFeed);
$("safeWa").addEventListener("click", guard(async () => window.open("https://wa.me/?text=" + encodeURIComponent(await composeSafe()), "_blank", "noopener")));
$("safeSms").addEventListener("click", guard(async () => {
  const msg = await composeSafe();
  if (/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)) location.href = "sms:?&body=" + encodeURIComponent(msg);
  else { await navigator.clipboard.writeText(msg).catch(() => {}); toast(t("sms_desktop")); }   // desktops have no SMS app
}));
$("safeShare").addEventListener("click", guard(async () => shareText(await composeSafe())));
$("safeCopy").addEventListener("click", guard(async () => copyText(await composeSafe())));

$("liveRefresh").addEventListener("click", guard(async () => {
  const b = $("liveRefresh"); b.classList.add("spin");
  try { await Promise.all([loadAreas(), loadAlerts()]); } finally { b.classList.remove("spin"); }
}));

$("refreshBtn").addEventListener("click", guard(async () => {
  $("refreshBtn").disabled = true;
  try { await api("/admin/refresh", { method: "POST" }); toast(t("refreshed")); await Promise.all([loadAreas(), loadAlerts()]); }
  finally { $("refreshBtn").disabled = false; }
}));

$("bcForm").addEventListener("submit", guard(async (e) => {
  e.preventDefault();
  await api("/admin/broadcast", { method: "POST", json: {
    area_id: +$("bcArea").value, level: $("bcLevel").value, message: $("bcMsg").value.trim() || null } });
  $("bcMsg").value = ""; toast("✔"); loadAlerts(); loadAreas();
}));

// ---------------------------------------------------------------- offline + PWA
function updateOnline() {
  const b = $("offlineBanner");
  b.hidden = navigator.onLine;
  b.textContent = t("offline");
}
window.addEventListener("online", () => { updateOnline(); loadAreas(); });
window.addEventListener("offline", updateOnline);
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});

// ---------------------------------------------------------------- start
(async function init() {
  initMap();
  setMapMode(state.mapMode);
  applyLang();
  updateOnline();
  await loadAreas();
  loadDistricts();
  loadReports();
  loadAlerts();
  loadSubs();
  setInterval(pollAlerts, 60_000);
  setInterval(loadAreas, 5 * 60_000);
  // brand-new database: the first weather refresh takes a few seconds, so poll until data appears
  let tries = 0;
  const warm = setInterval(async () => {
    if (state.areas.length && state.areas.every((a) => a.updated_at) || ++tries > 20) return clearInterval(warm);
    await loadAreas();
  }, 4000);
})();
