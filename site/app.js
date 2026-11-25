"use strict";

const KINDS = ["nordic", "downhill", "backcountry"];
const KIND_LABEL = { nordic: "Nordic", downhill: "Downhill", backcountry: "Backcountry" };
const AVY = { 1: "Low", 2: "Moderate", 3: "Considerable", 4: "High", 5: "Extreme" };
const IMAGE = /\.(jpe?g|png)(\?|$)/i;
const PAGE_LOADED = Date.now();
const fresh = (url) => `${url}${url.includes("?") ? "&" : "?"}t=${PAGE_LOADED}`;
const PLAY = `<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><circle cx="12" cy="12" r="11" fill="rgba(32,35,38,.75)"/><path d="M10 8.2v7.6l6-3.8z" fill="#fff"/></svg>`;
const PLAYERS = [/^https:\/\/api\.wetmet\.net\/widgets\/stream\/frame\.php/, /^https:\/\/video\.nest\.com\/embedded\//,
  /^https:\/\/vauth\.command\.verkada\.com\/.*\/embed\//, /^https:\/\/camstreamer\.com\/embed\//];

// "image" for a still picture, a player URL for an embeddable stream, or null for a page that has to open in its own tab.
const panoramas = {};

// ALERTWest names each panorama by capture time, so the newest one is looked up once per page load.
function alertwestPanorama(id) {
  panoramas[id] ??= fetch(`https://api.cdn.prod.alertwest.com/api/panorama/list/byCamId?camId=${id}&timestamp=`)
    .then((r) => r.json())
    .then((d) => {
      const cur = d.data[id].cur;
      return `https://img.cdn.prod.alertwest.com/data/thumb/${id}/${cur.cmlg_date.replaceAll("-", "/")}/${cur.cmlg_img_name}`;
    });
  return panoramas[id];
}

function fillPanoramas(root) {
  root.querySelectorAll("img[data-alertwest]").forEach((img) => {
    alertwestPanorama(img.dataset.alertwest).then((src) => { img.src = src; }).catch(() => img.remove());
  });
}

// The best picture a map webcam popup can show: a still, the newest panorama, or a stream's live thumbnail;
// a live player behind a play button when none of those exist.
async function fillPopupThumb(box, cam) {
  if (!box || box.dataset.filled) return;
  box.dataset.filled = "1";
  const urls = cam.links.map((l) => l.url);
  const open = urls[0];
  let src = urls.find((u) => camKind(u) === "image");
  const aw = urls.find((u) => camKind(u) === "panorama");
  if (!src && aw) src = await alertwestPanorama(aw.match(/cam-console\/(\d+)/)[1]).catch(() => null);
  if (!src) {
    const stream = urls.find((u) => /youtube\.com|youtu\.be|camstreamer\.com/.test(u));
    const yt = stream && camKind(stream)?.match(/youtube-nocookie\.com\/embed\/([\w-]{11})/);
    const known = state.data?.zones.flatMap((z) => z.webcams).find((w) => w.preview && urls.includes(w.url));
    if (yt) src = fresh(`https://i.ytimg.com/vi/${yt[1]}/hqdefault_live.jpg`);
    else if (known) src = fresh(known.preview);
  }
  if (src) {
    box.innerHTML = `<a href="${esc(open)}" target="_blank" rel="noopener"><img src="${esc(src)}" alt=""></a>`;
    const img = box.querySelector("img");
    img.onerror = () => box.replaceChildren();
    img.onload = () => { if (img.naturalWidth <= 120) box.replaceChildren(); };
    return;
  }
  const player = urls.map(camKind).find((k) => k && k !== "image" && k !== "panorama");
  if (!player) return;
  box.innerHTML = `<button type="button" class="pop-play">${PLAY}<span>Live</span></button>`;
  box.querySelector("button").onclick = () => {
    box.innerHTML = `<iframe src="${esc(player)}" allow="autoplay; fullscreen" allowfullscreen title="${esc(cam.title)}"></iframe>`;
  };
}

function camKind(url) {
  if (IMAGE.test(url) || /^https:\/\/api\.mtbachelor\.com\/api\/v1\/cams\//.test(url)) return "image";
  if (/^https:\/\/alertwest\.live\/cam-console\/\d+/.test(url)) return "panorama";
  const yt = url.match(/youtube\.com\/watch\?v=([\w-]+)/) || url.match(/youtu\.be\/([\w-]+)/);
  if (yt) return `https://www.youtube-nocookie.com/embed/${yt[1]}?autoplay=1&mute=1`;
  return PLAYERS.some((re) => re.test(url)) ? url : null;
}
const CAMERA = `<svg viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 7h1a2 2 0 0 0 2-2a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1a2 2 0 0 0 2 2h1a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2"/><circle cx="12" cy="13" r="3"/></svg>`;

const state = { mode: "now", kind: "all", openOnly: false, selected: null, data: null,
  start: null, drive: null, startOpen: false, startError: "", startBusy: false };
const STORE = { start: "skireport.start", drive: "skireport.drive", skip: "skireport.skipStart", spread: "skireport.spread" };
const WARNING = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 9v4M10.36 3.6 1.9 17.7a1.9 1.9 0 0 0 1.64 2.85h16.9a1.9 1.9 0 0 0 1.64-2.85L13.64 3.6a1.9 1.9 0 0 0-3.28 0zM12 17h.01"/></svg>`;
const CHEVRON_LEFT = `<svg viewBox="0 0 6 9" preserveAspectRatio="none" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 .9 1.3 4.5 5 8.1"/></svg>`;
const MOBILE = window.matchMedia("(max-width: 767px)");
const LATLON =/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/;
const AVY_COLORS = { 1: "#50B848", 2: "#FFF200", 3: "#F7941E", 4: "#ED1C24", 5: "#231F20", 0: "#888888" };
const CENTER_NAMES = { COAA: "COAC" };
const markers = {};
let map, avyLayer, depthGroup, depthNow, depthAhead, camGroup;
const spreadOption = L.layerGroup();
const camMarkers = [];
const camIcon = (dx, dy) => L.divIcon({ className: "", html: `<div class="cam-pin">${CAMERA}</div>`, iconSize: [14, 14], iconAnchor: [7 - dx, 7 - dy],
  popupAnchor: [dx, dy - 7], tooltipAnchor: [dx + 7, dy] });

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const inches = (v) => (v == null ? "-" : v >= 300 ? "300+ in" : `${Math.round(v)} in`);
const signed = (v) => (v == null ? "-" : `${Math.round(v) >= 0 ? "+" : "-"}${Math.abs(Math.round(v))} in`);
const ft = (v) => (v == null ? "-" : `${(Math.round(v / 100) * 100).toLocaleString()}`);

function level(rng, elev) {
  const [lo, hi] = rng || [];
  if (lo == null) return "-";
  const text = hi == null || Math.abs(hi - lo) < 300 ? ft(lo) : `${ft(lo)}-${ft(hi)}`;
  return `${text} ft${hi > elev ? "^" : ""}`;
}

function temps(pair) {
  const [hi, lo] = pair || [];
  if (hi == null && lo == null) return "-";
  return `${hi == null ? "-" : hi + "°"} / ${lo == null ? "-" : lo + "°"}F`;
}

function dots(conf) {
  const n = conf >= 70 ? 3 : conf >= 40 ? 2 : 1;
  return `<span class="dots" title="${conf}% rating confidence"><span class="on">${"●".repeat(n)}</span><span class="off">${"●".repeat(3 - n)}</span></span>`;
}

const badge = (score, big) => `<span class="badge b${score || 0}${big ? " big" : ""}">${score || "?"}</span>`;
const status = (s) => (s.value === "Unknown" ? `<span class="st-Unknown">Unknown</span>` : `<span class="st-${esc(s.value)}">${esc(s.value)}</span> ${dots(s.confidence)}`);
const condition = (v) => (v.score ? `${badge(v.score)} <span class="${v.condition.confidence < 40 ? "dim" : ""}">${esc(v.condition.value)}</span> ${dots(v.condition.confidence)}` : `<span class="st-Unknown">Unknown</span>`);
const avyChip = (v) => `<span class="chip a${AVY[v.level] ? v.level : 0}">${esc(AVY[v.level] || "No rating yet")}</span>`;
const fmtTime = (iso, opts) => new Date(iso).toLocaleString("en-US", { timeZone: "America/Los_Angeles", ...opts });

function readStore(key) {
  try { return JSON.parse(localStorage.getItem(key)); } catch { return null; }
}

function writeStore(key, value) {
  try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, JSON.stringify(value)); } catch {}
}

function duration(sec) {
  if (sec == null) return null;
  const m = Math.round(sec / 300) * 5;
  return m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m` : `${m}m`;
}

const driveSec = (a) => state.drive?.secs?.[a.id];
const driveText = (a) => (driveSec(a) == null ? "" : `${duration(driveSec(a))} drive`);
const destination = (a) => (a.access ? [a.access.lat, a.access.lon] : [a.lat, a.lon]);

async function geocode(text) {
  const m = text.match(LATLON);
  if (m) return [parseFloat(m[1]), parseFloat(m[2])];
  const url = `https://nominatim.openstreetmap.org/search?${new URLSearchParams({ q: text, format: "json", limit: 1, countrycodes: "us" })}`;
  const hits = await (await fetch(url)).json();
  if (!hits.length) throw new Error("That place wasn't found. Try a town name or lat, lon.");
  return [parseFloat(hits[0].lat), parseFloat(hits[0].lon)];
}

async function routeAll(start) {
  const areas = state.data.areas;
  const coords = [[start.lat, start.lon], ...areas.map(destination)].map(([lat, lon]) => `${lon},${lat}`).join(";");
  const res = await (await fetch(`https://router.project-osrm.org/table/v1/driving/${coords}?sources=0&annotations=duration`)).json();
  if (res.code !== "Ok") throw new Error("Drive times aren't available right now. Try again later.");
  const secs = {};
  areas.forEach((a, i) => { if (res.durations[0][i + 1] != null) secs[a.id] = res.durations[0][i + 1]; });
  return secs;
}

async function loadDrive() {
  const start = state.start;
  if (!start) { state.drive = null; return; }
  const key = `${start.lat},${start.lon}`;
  const cached = readStore(STORE.drive);
  if (cached && cached.key === key && state.data.areas.every((a) => a.id in cached.secs)) {
    state.drive = cached;
    return;
  }
  state.drive = { key, secs: await routeAll(start) };
  writeStore(STORE.drive, state.drive);
}

async function saveStart(text) {
  state.startBusy = true;
  state.startError = "";
  state.startText = text;
  renderList();
  try {
    const [lat, lon] = await geocode(text);
    state.start = { label: text.trim(), lat, lon };
    await loadDrive();
    writeStore(STORE.start, state.start);
    state.startOpen = false;
    state.startText = null;
  } catch (e) {
    state.start = readStore(STORE.start);
    state.startError = e.message || "Something went wrong. Try again.";
  }
  state.startBusy = false;
  syncStartButton();
  render();
}

function clearStart() {
  state.start = state.drive = null;
  writeStore(STORE.start, null);
  writeStore(STORE.drive, null);
  writeStore(STORE.skip, true);
  state.startOpen = false;
  syncStartButton();
  render();
}

function syncStartButton() {
  document.getElementById("start-btn").textContent = state.start ? `From ${state.start.label}` : "Set start point";
}

function startCard() {
  const show = state.startOpen || (!state.start && !readStore(STORE.skip));
  if (!show) return "";
  return `<form class="start" id="start-form">
    <div class="name">Show drive times from</div>
    <input id="start-input" type="text" autocomplete="off" placeholder="Corvallis, OR" value="${esc(state.startText ?? state.start?.label ?? "")}" aria-label="Start point">
    ${state.startError ? `<div class="err">${esc(state.startError)}</div>` : ""}
    <div class="small">Saved on this device only.</div>
    <div class="actions">
      ${state.start ? `<button type="button" class="link" data-action="start-clear">Clear</button>` : ""}
      <button type="button" class="link" data-action="start-skip">${state.start ? "Cancel" : "Skip"}</button>
      <button type="submit" class="btn" ${state.startBusy ? "disabled" : ""}>${state.startBusy ? "Working…" : "Save"}</button>
    </div></form>`;
}

const view = (a) => (state.mode === "now" ? a.now : a.ahead);
const byId = (id) => state.data.areas.find((a) => a.id === id);
const zoneOf = (a) => state.data.zones.find((z) => z.id === a.zone);

function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  if (p.get("t") === "ahead") state.mode = "ahead";
  if (p.get("area")) state.selected = p.get("area");
}

function writeHash() {
  const p = new URLSearchParams();
  if (state.mode === "ahead") p.set("t", "ahead");
  if (state.selected) p.set("area", state.selected);
  history.replaceState(null, "", p.toString() ? `#${p}` : location.pathname);
}

function initMap() {
  map = L.map("map", { zoomControl: true, zoomSnap: 0.1, scrollWheelZoom: false }).setView([44.9, -121.9], 7);
  // One whole zoom level per scroll step; Leaflet's own wheel zoom lands on uneven fractions with zoomSnap 0.1.
  let wheelReady = 0;
  map.getContainer().addEventListener("wheel", (e) => {
    e.preventDefault();
    const now = performance.now();
    if (now < wheelReady || !e.deltaY) return;
    wheelReady = now + 200;
    const z = map.getZoom();
    const target = e.deltaY < 0 ? Math.floor(z + 1e-6) + 1 : Math.ceil(z - 1e-6) - 1;
    map.setZoomAround(map.mouseEventToContainerPoint(e), Math.max(map.getMinZoom(), Math.min(map.getMaxZoom(), target)));
  }, { passive: false });
  map.createPane("labels").style.zIndex = 450;
  map.getPane("labels").style.pointerEvents = "none";
  const esri = "https://server.arcgisonline.com/ArcGIS/rest/services/{service}/MapServer/tile/{z}/{y}/{x}";
  const relief = L.layerGroup([
    L.tileLayer(esri, { service: "Elevation/World_Hillshade", maxZoom: 17, maxNativeZoom: 16, opacity: 0.5,
      attribution: "Esri, USGS" }),
    L.tileLayer(esri, { service: "Canvas/World_Light_Gray_Reference", maxZoom: 17, maxNativeZoom: 16, pane: "labels" }),
  ]).addTo(map);
  const topo = L.tileLayer("https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 17, maxNativeZoom: 16, attribution: "USGS The National Map",
  });
  depthNow = L.tileLayer.wms("https://mapservices.weather.noaa.gov/raster/services/snow/NOHRSC_Snow_Analysis/MapServer/WMSServer", {
    layers: "5", format: "image/png", transparent: true, opacity: 0.55, attribution: "NOAA NOHRSC",
  });
  depthGroup = L.layerGroup([depthNow]).addTo(map);
  const depth = depthGroup;
  const cams = L.layerGroup().addTo(map);
  avyLayer = L.geoJSON(null, {
    style: (f) => ({ color: f.properties.color, weight: 1, opacity: 0.8, fillColor: f.properties.color, fillOpacity: 0.22 }),
    onEachFeature: (f, layer) => {
      const p = f.properties;
      layer.bindPopup(`<b>${esc(p.name)}</b> <span class="small">${esc(CENTER_NAMES[p.center_id] || p.center_id)}</span><br>
        ${avyChip({ level: p.danger_level })}<br><a href="${esc(p.link)}" target="_blank" rel="noopener">Read forecast</a>`);
    },
  });
  const layers = L.control.layers({ "Light relief": relief, "USGS topo": topo },
    { "Snow depth (NOHRSC)": depth, "Avalanche danger": avyLayer, Webcams: cams,
      "Spread overlapping markers": spreadOption }, { collapsed: true }).addTo(map);
  if (readStore(STORE.spread) !== false) spreadOption.addTo(map);
  map.on("overlayadd overlayremove", (e) => {
    if (e.layer !== spreadOption) return;
    writeStore(STORE.spread, e.type === "overlayadd");
    if (state.data) drawMarkers();
  });
  const box = layers.getContainer();
  // Leaflet opens the menu on hover; make it open on press and close on a press anywhere else.
  L.DomEvent.off(box, { mouseenter: layers._expandSafely, mouseleave: layers.collapse }, layers);
  document.addEventListener("click", (e) => { if (!box.contains(e.target)) layers.collapse(); });
  // Capture runs before Leaflet's own handler, which can only open the menu.
  box.querySelector(".leaflet-control-layers-toggle").addEventListener("click", (e) => {
    if (!box.classList.contains("leaflet-control-layers-expanded")) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    layers.collapse();
  }, true);

  const avyLegend = L.control({ position: "bottomleft" });
  avyLegend.onAdd = () => {
    const div = L.DomUtil.create("div", "legend");
    div.innerHTML = `<div class="lg-title">Avalanche danger</div><div class="lg-grid">${
      [1, 2, 3, 4, 5, 0].map((l) => `<span><i class="sw" style="background:${AVY_COLORS[l]}"></i>${l ? AVY[l] : "No rating"}</span>`).join("")}</div>`;
    return div;
  };
  map.on("overlayadd", (e) => e.layer === avyLayer && avyLegend.addTo(map));
  map.on("overlayremove", (e) => e.layer === avyLayer && avyLegend.remove());
  avyLayer.addTo(map);
  avyLegend.addTo(map);

  const legend = L.control({ position: "bottomleft" });
  legend.onAdd = () => {
    const div = L.DomUtil.create("div", "legend");
    div.innerHTML = `<div class="lg-title">Condition</div>
      <div class="lg-row">${[1, 2, 3, 4, 5].map((s) => `<span class="pin nordic p${s}"></span>`).join("")}<span>1 to 5</span></div>
      <div class="lg-row"><span class="pin nordic p0"></span>Nordic <span class="pin downhill p0"></span>Downhill <span class="pin backcountry p0"></span>Backcountry</div>
      <div class="lg-row"><span class="pin nordic p4 low"></span>Faded: low rating confidence</div>`;
    return div;
  };
  legend.addTo(map);

  const depthLegend = L.control({ position: "bottomleft" });
  depthLegend.onAdd = () => {
    const div = L.DomUtil.create("div", "legend");
    div.innerHTML = `<div class="lg-title">Snow depth (in)<span id="depth-when"></span></div><div class="lg-grid">${
      DEPTH_CLASSES.map(([color, label]) => `<span><i class="sw${color ? "" : " empty"}" style="background:${color ? `#${color}` : "none"}"></i>${label}</span>`).join("")}</div>`;
    return div;
  };
  const showDepthLegend = (on) => (on ? depthLegend.addTo(map) : depthLegend.remove());
  map.on("overlayadd", (e) => { if (e.layer === depth) { showDepthLegend(true); syncDepth(); } });
  map.on("overlayremove", (e) => e.layer === depth && showDepthLegend(false));
  showDepthLegend(true);

  camGroup = cams;
  map.on("overlayadd overlayremove", (e) => e.layer === cams && state.data && drawMarkers());
  fetch("data/webcams.json").then((r) => r.json()).then((list) => {
    list.forEach((c, i) => {
      const html = `<b>${esc(c.title)}</b><br><span class="small">${esc(c.note)}</span>
        <div class="pop-thumb"></div>
        ${c.links.map((l) => `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)}</a>`).join("<br>")}`;
      const marker = L.marker([c.lat, c.lon], { icon: camIcon(0, 0) }).bindPopup(html, { minWidth: 240, maxWidth: 240, className: "cam-popup" }).addTo(cams);
      marker.on("popupopen", (e) => fillPopupThumb(e.popup.getElement().querySelector(".pop-thumb"), c));
      camMarkers.push({ id: `cam-${i}`, lat: c.lat, lon: c.lon, marker });
    });
    if (state.data) drawMarkers();
  }).catch(() => {});
}

// NOHRSC's snow depth classes and colors; skireport/depthmap.py draws the +48h layer with the same ones.
const DEPTH_CLASSES = [
  [null, "0-0.4"], ["abc1bf", "0.4-2"], ["66c1c4", "2-4"], ["63a9cb", "4-10"], ["5079c8", "10-20"], ["3c3fc2", "20-39"],
  ["5720c3", "39-59"], ["7d01bb", "59-98"], ["b404b1", "98-197"], ["a91377", "197-295"], ["992b50", "295-394"], ["8b4545", "394+"],
];

function syncDepth() {
  const d = state.data;
  if (!d) return;
  const m = d.depth_map_ahead;
  const ahead = state.mode === "ahead" && m;
  if (ahead && !depthAhead) {
    depthAhead = L.imageOverlay(`data/${m.image}?v=${encodeURIComponent(d.generated)}`, m.bounds,
      { opacity: 0.55, className: "depth-img", attribution: "NOAA SNODAS, NBM" });
  }
  const want = ahead ? depthAhead : depthNow;
  if (!depthGroup.hasLayer(want)) {
    depthGroup.clearLayers();
    depthGroup.addLayer(want);
  }
  const el = document.getElementById("depth-when");
  if (el) {
    el.textContent = state.mode !== "ahead" ? ""
      : m ? " · +48h" : " · now";
  }
}

let fitPending = false;

function fitAreas() {
  // A hidden map (the List tab on a phone) has no size, so fitting now would zoom all the way in.
  fitPending = !document.getElementById("map").offsetWidth;
  if (!fitPending) map.fitBounds(L.latLngBounds(state.data.areas.map((a) => [a.lat, a.lon])), { padding: [12, 12] });
}

const PIN_GAP = 14;

function spread(items) {
  // Screen-space nudge: overlapping markers push each other apart until they're PIN_GAP px apart.
  const pts = items.map((a, i) => {
    const p = map.latLngToLayerPoint([a.lat, a.lon]);
    return { id: a.id, i, x0: p.x, y0: p.y, x: p.x, y: p.y };
  });
  for (let pass = 0; pass < 300; pass++) {
    let moved = false;
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const a = pts[i], b = pts[j];
        let dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy);
        if (d >= PIN_GAP) continue;
        if (d < 0.01) { dx = Math.cos(i + j); dy = Math.sin(i + j); d = 1; }
        const push = ((PIN_GAP - d) / 2) * 1.05;
        a.x -= (dx / d) * push; a.y -= (dy / d) * push;
        b.x += (dx / d) * push; b.y += (dy / d) * push;
        moved = true;
      }
    }
    if (!moved) break;
  }
  return Object.fromEntries(pts.map((p) => [p.id, [p.x - p.x0, p.y - p.y0]]));
}

function drawMarkers() {
  const cams = map.hasLayer(camGroup) ? camMarkers : [];
  const offsets = map.hasLayer(spreadOption) ? spread([...state.data.areas, ...cams]) : {};
  for (const c of camMarkers) c.marker.setIcon(camIcon(...(offsets[c.id] || [0, 0])));
  for (const a of state.data.areas) {
    const v = view(a);
    const score = v && v.score ? v.score : 0;
    const low = v && v.condition.confidence < 40;
    const cls = `pin ${a.kind} p${score}${low ? " low" : ""}${state.selected === a.id ? " sel" : ""}`;
    const [dx, dy] = offsets[a.id] || [0, 0];
    const icon = L.divIcon({ className: "", html: `<div class="${cls}"></div>`, iconSize: [12, 12], iconAnchor: [6 - dx, 6 - dy],
      popupAnchor: [dx, dy - 6], tooltipAnchor: [dx + 6, dy] });
    const tip = `${a.name}: ${v ? `${v.status.value}, ${v.score ? v.score + "/5 " + v.condition.value : "condition unknown"}` : "no projection"}`;
    if (markers[a.id]) {
      markers[a.id].setIcon(icon).setTooltipContent(esc(tip));
    } else {
      markers[a.id] = L.marker([a.lat, a.lon], { icon, keyboard: true, title: a.name })
        .bindTooltip(esc(tip)).on("click", () => {
          state.fromMap = document.querySelector(".layout").dataset.tab === "map" && MOBILE.matches;
          select(a.id, false);
        }).addTo(map);
    }
    markers[a.id].setZIndexOffset(state.selected === a.id ? 1000 : 0);
  }
}

function visible(a) {
  if (state.kind !== "all" && a.kind !== state.kind) return false;
  const v = view(a);
  return !state.openOnly || (v && tier(v.status) < 2);
}

const skiScore = (depth, fresh) => Math.min(depth || 0, 120) / 120 + Math.min(fresh || 0, 24) / 24;

const tier = (s) => ({ Open: 0, Sketchy: 1 }[s.value] ?? 2);

function promise(a) {
  const v = view(a);
  if (!v) return [3, 0, 0];
  return [tier(v.status), -(v.score || 0), -skiScore(v.depth_in, v.fresh_in)];
}

const byPromise = (x, y) => promise(x).reduce((d, k, i) => d || k - promise(y)[i], 0);

function renderList() {
  const d = state.data;
  const label = state.mode === "now" ? "" : ` ${fmtTime(d.ahead_until, { weekday: "long" })}`;
  const fresh = state.mode === "now" ? "new snow in the last 48 hours" : "forecast snow in the next 48 hours";
  let html = `${startCard()}<h2>Best snow${esc(label)}</h2>
    <p class="small" style="margin:0">Ranked by snow depth and fresh snow (${fresh}).</p>
    <p class="small" style="margin:2px 0 0">Rating confidence: ${dots(80)} high &nbsp;${dots(50)} medium &nbsp;${dots(20)} low</p><div class="best">`;
  for (const kind of KINDS) {
    const ids = d.best[state.mode][kind];
    html += `<div class="label kind">${kind}</div>`;
    if (!ids.length) html += `<div class="small">Nothing open.</div>`;
    for (const id of ids) {
      const a = byId(id), v = view(a);
      html += `<div class="bet" data-id="${esc(id)}">${badge(v.score, true)}
        <div><span class="name">${esc(a.name)}</span> <span class="small">${esc(v.condition.value)}</span><br>
        <span class="small">${esc(zoneOf(a).name)}${driveText(a) ? ` · ${driveText(a)}` : ""} · ${inches(v.depth_in)} deep · ${signed(v.fresh_in)} fresh · ${temps(v.temp)}</span></div>
        <div>${dots(v.condition.confidence)}</div></div>`;
    }
  }
  html += `</div>
    <h2>All areas</h2>
    <div class="filters">
      <span class="chipset">${["all", ...KINDS].map((k) => `<button type="button" data-kind="${k}" class="${state.kind === k ? "on" : ""}">${k === "all" ? "All" : KIND_LABEL[k]}</button>`).join("")}</span>
      <label><input type="checkbox" id="open-only" ${state.openOnly ? "checked" : ""}> Open or sketchy only</label>
    </div>`;

  let shown = 0;
  for (const z of d.zones) {
    const rows = d.areas.filter((a) => a.zone === z.id && visible(a)).sort(byPromise);
    if (!rows.length) continue;
    shown += rows.length;
    html += `<h3 class="zone">${esc(z.name)}</h3><div class="avy"><span class="label">Avalanche</span>&nbsp; ${
      z.avalanche.length ? z.avalanche.map((v) => `${esc(v.zone)} ${avyChip(v)}`).join(" &nbsp;") : `<span class="small">No forecast covers this zone.</span>`}</div>`;
    for (const a of rows) {
      const v = view(a);
      html += `<div class="row${state.selected === a.id ? " sel" : ""}" data-id="${esc(a.id)}">
        ${badge(v && v.score, true)}
        <div><span class="name">${esc(a.name)}</span> ${v && v.score ? `<span class="${v.condition.confidence < 40 ? "dim" : "cond"}">${esc(v.condition.value)}</span> ${dots(v.condition.confidence)}` : ""}
          <div class="meta">${KIND_LABEL[a.kind]} · ${a.elev_ft.toLocaleString()} ft${driveText(a) ? ` · ${duration(driveSec(a))}` : ""} · ${v ? status(v.status) : "-"}</div></div>
        <div class="right"><b>${v ? inches(v.depth_in) : "-"}</b><br><span class="small">${v ? temps(v.temp) : ""}</span></div></div>`;
    }
  }
  if (!shown) html += `<p class="small">No areas match these filters.</p>`;
  html += footer();
  document.getElementById("list").innerHTML = html;
}

function footer() {
  const d = state.data;
  return `<h2>Sources</h2>
    <p class="note">Resort and grooming reports, NRCS SNOTEL, NOAA NOHRSC and SNODAS, NOAA National Blend of Models, NWS, avalanche.org, ODOT TripCheck, WSDOT, NPS.</p>
    ${d.errors.length ? `<p class="note" style="color:#a00">Unavailable in this update: ${esc(d.errors.join(", "))}.</p>` : ""}`;
}

const LINK_ICONS = [
  [/(^|\.)weather\.gov$/, "noaa"], [/(^|\.)tripcheck\.com$/, "tripcheck"], [/(^|\.)caltopo\.com$/, "caltopo"],
  [/(^|\.)wsdot\.(com|wa\.gov)$/, "wsdot"], [/(^|\.)nps\.gov$/, "nps"], [/(^|\.)nordic-pulse\.com$/, "nordicpulse"],
  [/(^|\.)mtbachelor\.com$/, "bachelor"], [/(^|\.)timberlinelodge\.com$/, "timberline"], [/(^|\.)skihood\.com$/, "meadows"],
  [/(^|\.)skibowl\.com$/, "skibowl"], [/(^|\.)hoodoo\.com$/, "hoodoo"], [/(^|\.)willamettepass\.ski$/, "willamette"],
  [/(^|\.)cooperspur\.com$/, "cooperspur"],
];

function linkIcon(url) {
  const host = new URL(url).hostname;
  const hit = LINK_ICONS.find(([re]) => re.test(host));
  return hit ? `<img class="link-icon" src="icons/${hit[1]}.png" alt="">` : "";
}

const cardAttrs = (mode) => {
  const cls = `class="card${state.mode === mode ? " active" : ""}"`;
  return MOBILE.matches ? cls : `${cls} data-mode="${mode}" role="button" tabindex="0" aria-pressed="${state.mode === mode}"`;
};

function card(a, v, title, mode) {
  if (!v) return `<div ${cardAttrs(mode)}><div class="label">${title}</div><div class="line st-Unknown">No projection</div></div>`;
  const facts = mode === "ahead"
    ? [`${inches(v.depth_in)} deep (${signed(v.depth_change_in)})`,
       `${signed(v.fresh_in)} forecast snow${v.nws_snow_in != null ? ` (NWS ${signed(v.nws_snow_in)})` : ""}`,
       v.rain_in >= 0.1 ? `${v.rain_in.toFixed(1)} in rain` : null]
    : [`${inches(v.depth_in)} deep`, `${signed(v.fresh_in)} last 48h`];
  facts.push(`Snow level ${level(v.snow_level, a.elev_ft)}`, temps(v.temp));
  return `<div ${cardAttrs(mode)}><div class="label">${title}</div>
    <div class="line">${status(v.status)}</div><div class="line">${condition(v)}</div>
    <div class="facts">${facts.filter(Boolean).join("<br>")}</div></div>`;
}

function depthChart(a) {
  const d = state.data;
  const CAP = 300;
  const modeled = Object.entries(d.area_depth?.[a.id] || {}).filter(([, v]) => v != null)
    .sort(([p], [q]) => p.localeCompare(q)).map(([day, v]) => [day, Math.min(v, CAP)]);
  const comparable = a.station && Math.abs(a.station.elev_ft - a.elev_ft) <= 1500;
  const measured = (comparable && d.station_depth[a.station.triplet]) || [];
  if (!modeled.length && !measured.length) return "";
  const start = modeled[modeled.length - 1];
  const proj = start && a.ahead?.depth_change_in != null
    ? [d.ahead_until, Math.min(CAP, Math.max(0, start[1] + a.ahead.depth_change_in))] : null;
  const capped = modeled.some(([, v]) => v >= CAP);

  const W = 320, H = 120, L0 = 30, R = 8, T = 8, B = 18;
  const t0 = Date.parse(d.season_start), t1 = Math.max(Date.parse(d.ahead_until), t0 + 86400000 * 30);
  const peak = Math.max(12, ...modeled.map(([, v]) => v), ...measured.map(([, v]) => v), proj ? proj[1] : 0);
  const step = peak > 120 ? 48 : peak > 48 ? 24 : 12;
  const top = Math.ceil(peak / step) * step;
  const x = (day) => L0 + ((Date.parse(day) - t0) / (t1 - t0)) * (W - L0 - R);
  const y = (v) => T + (1 - v / top) * (H - T - B);

  let svg = "";
  for (let v = 0; v <= top; v += top / 2) {
    svg += `<line x1="${L0}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#E8E9EA"/>
      <text x="${L0 - 4}" y="${y(v) + 3}" text-anchor="end">${v}</text>`;
  }
  const m = new Date(t0);
  while (m.getTime() <= t1) {
    const day = m.toISOString().slice(0, 10);
    svg += `<text x="${x(day)}" y="${H - 4}">${m.toLocaleString("en-US", { month: "short", timeZone: "UTC" })}</text>`;
    m.setUTCMonth(m.getUTCMonth() + 1);
  }
  const path = (pts) => pts.map(([day, v]) => `${x(day).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  if (measured.length) svg += `<polyline fill="none" stroke="#A9ABAD" stroke-width="1.25" points="${path(measured)}"/>`;
  if (modeled.length) svg += `<polyline fill="none" stroke="#1A4F8B" stroke-width="1.75" points="${path(modeled)}"/>`;
  if (proj) {
    const when = fmtTime(proj[0], { weekday: "short", hour: "numeric" });
    svg += `<line x1="${x(start[0])}" y1="${y(start[1])}" x2="${x(proj[0])}" y2="${y(proj[1])}" stroke="#1A4F8B" stroke-width="1.5" stroke-dasharray="3 2"/>
      <circle cx="${x(proj[0])}" cy="${y(proj[1])}" r="4" fill="#fff" stroke="#1A4F8B" stroke-width="1.5"><title>${esc(when)}: ${inches(proj[1])} projected</title></circle>`;
  }

  return `<div class="chart"><div class="label">Snow depth this season (in)</div>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Snow depth since ${esc(d.season_start)}">${svg}</svg>
    <div class="keys small">${[
      modeled.length && `<span><i class="key model"></i>Modeled at ${esc(a.name)} (NOAA SNODAS)${capped ? `, ${CAP}+ in shown at ${CAP}` : ""}</span>`,
      measured.length && `<span><i class="key line"></i>Measured at ${esc(a.station.name)}, ${a.station.elev_ft.toLocaleString()} ft</span>`,
      proj && `<span><i class="key proj"></i>+48h projection: ${inches(proj[1])} (${signed(a.ahead.depth_change_in)})</span>`,
    ].filter(Boolean).join("")}</div></div>`;
}

function renderDetail() {
  const a = byId(state.selected), z = zoneOf(a), d = state.data;
  const avy = a.avalanche && z.avalanche.some((v) => v.zone === a.avalanche.zone) ? a.avalanche : null;
  const roads = z.roads.checkpoints.map((c) => `<div class="road">${esc(c.name)} <span class="small">${esc(c.route)}</span><br>${
    c.chain_level ? `<span class="warn w-${esc(c.chain_level)}">${WARNING}${esc(c.chains)}</span>` : `<span class="small">${esc(c.chains || "No restrictions")}</span>`}${c.surface ? `<span class="small"> · ${esc(c.surface)}</span>` : ""}</div>`);
  const cams = z.webcams.map((c) => {
    const kind = camKind(c.url);
    if (kind === "panorama") {
      const id = c.url.match(/cam-console\/(\d+)/)[1];
      return `<a href="${esc(c.url)}" target="_blank" rel="noopener" class="cam-pano"><img data-alertwest="${id}" alt="${esc(c.name)}">${esc(c.short)} · 360°</a>`;
    }
    if (kind === "image") {
      return `<a href="${esc(c.url)}" target="_blank" rel="noopener"><img src="${esc(c.url)}" alt="${esc(c.name)}" loading="lazy">${esc(c.short)}</a>`;
    }
    if (kind) {
      const still = c.preview
        ? `<img class="cam-still" src="${esc(fresh(c.preview))}" alt="" loading="lazy" onerror="this.remove()" onload="this.naturalWidth <= 120 && this.remove()">` : "";
      return `<button type="button" class="cam-play" data-src="${esc(kind)}" aria-label="Play ${esc(c.name)}"><span class="cam-screen">${still}${PLAY}<span>Live</span></span>${esc(c.short)}</button>`;
    }
    return `<a href="${esc(c.url)}" target="_blank" rel="noopener" class="cam-link">${esc(c.short)}</a>`;
  }).join("");
  const links = [
    a.resort_url && ["Resort report", a.resort_url],
    a.grooming_url && ["Grooming", a.grooming_url],
    ["Hourly forecast", `https://forecast.weather.gov/MapClick.php?lat=${a.lat}&lon=${a.lon}&FcstType=graphical`],
    ["Road conditions", z.road_link],
    ["Open in CalTopo", `https://caltopo.com/map.html#ll=${a.lat},${a.lon}&z=14`],
  ].filter(Boolean);
  const until = fmtTime(d.ahead_until, { weekday: "short", hour: "numeric" });

  document.getElementById("detail").innerHTML = `
    <button type="button" class="back" id="back">${CHEVRON_LEFT}${state.fromMap ? "Map" : "All areas"}</button>
    <p class="title">${esc(a.name)}</p>
    <div class="small">${KIND_LABEL[a.kind]} · ${a.elev_ft.toLocaleString()} ft · ${esc(z.name)}${
      driveText(a) ? ` · ${driveText(a)}${a.access ? ` to ${esc(a.access.name)}` : ""}` : a.access ? ` · access from ${esc(a.access.name)}` : ""}</div>
    <div class="cards">${card(a, a.now, "Now", "now")}${card(a, a.ahead, `+48h · ${esc(until)}`, "ahead")}</div>
    ${depthChart(a)}
    <div class="kv">
      <span class="label">Avalanche</span><span>${avy
        ? `${esc(avy.zone)} (${esc(avy.center_name)}) ${avyChip(avy)}<br><span class="small">Issued ${esc(fmtTime(avy.issued + "Z", { weekday: "short", hour: "numeric", minute: "2-digit" }))} · </span><a href="${esc(avy.link)}" target="_blank" rel="noopener">Read forecast</a>`
        : `<span class="small">No avalanche forecast covers this area.</span>`}</span>
      <span class="label">Roads</span><span>${roads.length ? roads.join("") : ""}${z.roads.notes.map((n) => `<div class="small">${esc(n)}</div>`).join("")}${
        !roads.length && !z.roads.notes.length ? `<span class="small">No road data</span>` : ""}</span>
      <span class="label">Permit</span><span>${esc(z.permit)}</span>
      ${cams ? `<span class="label">Webcams</span><div class="cams">${cams}</div>` : ""}
      <span class="label">Links</span><span class="links">${links.map(([t, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${linkIcon(u)}${t}</a>`).join("")}</span>
    </div>`;
  fillPanoramas(document.getElementById("detail"));
  document.getElementById("back").onclick = () => {
    const toMap = state.fromMap;
    select(null);
    if (toMap) setTab("map");
  };
}

function select(id, pan = true) {
  const panel = document.getElementById("panel");
  if (!state.selected && id) state.listScroll = panel.scrollTop;
  if (!id || pan) state.fromMap = false;
  state.selected = id;
  document.getElementById("list").hidden = !!id;
  document.getElementById("detail").hidden = !id;
  if (id) {
    renderDetail();
    // The panel is hidden behind the Map tab on phones, and a hidden element can't be scrolled.
    setTab("list");
    panel.scrollTop = 0;
    if (pan) map.setView([byId(id).lat, byId(id).lon], Math.max(map.getZoom(), 10));
  } else {
    renderList();
    panel.scrollTop = state.listScroll || 0;
  }
  drawMarkers();
  writeHash();
}

function setTab(tab) {
  document.querySelector(".layout").dataset.tab = tab;
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  if (tab !== "map") return;
  map.invalidateSize();
  if (fitPending) state.selected ? map.setView([byId(state.selected).lat, byId(state.selected).lon], 10) : fitAreas();
}

function syncToggle() {
  document.querySelectorAll(".seg button").forEach((b) => b.classList.toggle("on", b.dataset.mode === state.mode));
}

function render() {
  syncToggle();
  syncDepth();
  state.selected ? renderDetail() : renderList();
  drawMarkers();
  writeHash();
}

function bind() {
  document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => { state.mode = b.dataset.mode; render(); }));
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => {
    const from = document.querySelector(".layout").dataset.tab;
    if (b.dataset.tab === "list" && from === "map" && state.selected) select(null);
    setTab(b.dataset.tab);
  }));
  document.getElementById("list").addEventListener("click", (e) => {
    const action = e.target.closest("[data-action]")?.dataset.action;
    if (action === "start-clear") { clearStart(); return; }
    if (action === "start-skip") {
      if (!state.start) writeStore(STORE.skip, true);
      state.startOpen = false;
      state.startError = "";
      renderList();
      return;
    }
    if (e.target.closest("#start-form")) return;
    const kind = e.target.closest("[data-kind]");
    if (kind) { state.kind = kind.dataset.kind; renderList(); return; }
    const row = e.target.closest("[data-id]");
    if (row) select(row.dataset.id);
  });
  const pickCard = (e) => {
    const card = e.target.closest(".card[data-mode]");
    if (!card || e.target.closest("a") || card.dataset.mode === state.mode) return;
    state.mode = card.dataset.mode;
    render();
  };
  document.getElementById("detail").addEventListener("click", pickCard);
  document.getElementById("detail").addEventListener("click", (e) => {
    const tile = e.target.closest(".cam-play");
    if (!tile) return;
    const frame = document.createElement("iframe");
    frame.src = tile.dataset.src;
    frame.title = tile.getAttribute("aria-label").replace(/^Play /, "");
    frame.allow = "autoplay; fullscreen; picture-in-picture";
    frame.allowFullscreen = true;
    const live = Object.assign(document.createElement("div"), { className: "cam-live" });
    live.append(frame, Object.assign(document.createElement("span"), { textContent: frame.title }));
    tile.replaceWith(live);
  });
  document.getElementById("detail").addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pickCard(e); }
  });
  document.getElementById("list").addEventListener("submit", (e) => {
    e.preventDefault();
    const text = document.getElementById("start-input").value;
    if (!text.trim()) {
      state.startError = "Enter a place or lat, lon.";
      renderList();
      return;
    }
    saveStart(text);
  });
  document.getElementById("start-btn").addEventListener("click", () => {
    state.startOpen = true;
    state.startError = "";
    select(null);
    document.getElementById("start-input")?.focus();
  });
  document.getElementById("list").addEventListener("change", (e) => {
    if (e.target.id === "open-only") { state.openOnly = e.target.checked; renderList(); }
  });
}

async function main() {
  readHash();
  initMap();
  bind();
  try {
    state.data = await (await fetch("data/latest.json", { cache: "no-cache" })).json();
  } catch {
    document.getElementById("list").innerHTML = `<p class="small">The report data couldn't be loaded. Try again later.</p>`;
    return;
  }
  const d = state.data;
  syncUpdated();
  if (state.selected && !byId(state.selected)) state.selected = null;
  avyLayer.addData(d.avalanche_zones || []);
  map.on("zoomend", drawMarkers);
  syncDepth();
  state.start = readStore(STORE.start);
  syncStartButton();
  try { await loadDrive(); } catch { state.drive = null; }
  if (!state.selected) fitAreas();
  syncToggle();
  select(state.selected);
  setInterval(checkForUpdate, REFRESH_MS);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && Date.now() - lastCheck > REFRESH_MS / 6) checkForUpdate();
  });
}

const REFRESH_MS = 30 * 60 * 1000;
let lastCheck = Date.now();

function syncUpdated() {
  const d = state.data;
  document.getElementById("updated").textContent =
    `Updated ${fmtTime(d.generated, { weekday: "short", hour: "numeric", minute: "2-digit" })} · NBM ${d.nbm_run ? new Date(d.nbm_run).toISOString().slice(11, 13) + "Z" : "unavailable"}`;
}

async function checkForUpdate() {
  lastCheck = Date.now();
  let next;
  try {
    next = await (await fetch("data/latest.json", { cache: "no-cache" })).json();
  } catch {
    return;
  }
  if (next.generated === state.data.generated) return;
  state.data = next;
  for (const id of Object.keys(markers)) {
    if (!byId(id)) { map.removeLayer(markers[id]); delete markers[id]; }
  }
  const lost = state.selected && !byId(state.selected);
  avyLayer.clearLayers().addData(next.avalanche_zones || []);
  if (depthAhead) { depthGroup.removeLayer(depthAhead); depthAhead = null; }
  syncUpdated();
  try { await loadDrive(); } catch { state.drive = null; }
  if (lost) select(null);
  render();
}

main();
