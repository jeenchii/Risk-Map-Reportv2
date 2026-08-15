/* ============================================================
   Bangkok Risk & Incident Map
   Reads data/incidents.json and renders a filterable Leaflet map.
   ============================================================ */

// ---- Category & source config (single source of truth) ----
const CATEGORIES = {
  accident:     { th: "อุบัติเหตุ",  en: "Accident",     icon: "🚗", color: "#dc2626" },
  construction: { th: "ก่อสร้าง",    en: "Construction", icon: "🚧", color: "#f59e0b" },
  weather:      { th: "สภาพอากาศ",   en: "Weather",      icon: "⛈️", color: "#7c3aed" },
  flood:        { th: "น้ำท่วม",     en: "Flood",        icon: "🌊", color: "#0891b2" },
  closure:      { th: "ปิดถนน",      en: "Closure",      icon: "⛔", color: "#be123c" },
  fire:         { th: "ไฟไหม้",      en: "Fire",         icon: "🔥", color: "#ea580c" },
  other:        { th: "อื่น ๆ",      en: "Other",        icon: "⚠️", color: "#64748b" },
};

const SOURCES = {
  JS100:  { label: "JS100",         color: "#2563eb" },
  FM91:   { label: "สวพ.91",        color: "#059669" },
  RAMA9:  { label: "พระราม 9",      color: "#db2777" },
  MANUAL: { label: "รายงานเพิ่มเติม", color: "#64748b" },
};

const REGION_CENTER = [13.25, 100.85];
// Coverage: Bangkok → Chonburi → Pattaya → Laem Chabang → Rayong/Map Ta Phut
const COVERAGE = [[12.50, 100.28], [13.98, 101.45]]; // [SW, NE]
const ACTIVE_WINDOW_H = 8;          // "active" = reported within this many hours
const REFRESH_MS = 5 * 60 * 1000;   // re-check the JSON every 5 min

// ---- State ----
const state = {
  incidents: [],
  time: "active",                        // active | 24h | 7d
  cats: new Set(Object.keys(CATEGORIES)),
  srcs: new Set(Object.keys(SOURCES)),
  updated: null,
};

let map, cluster;
const markerById = new Map();

// ---- Boot ----
init();

function init() {
  map = L.map("map", { zoomControl: true, attributionControl: true }).setView(REGION_CENTER, 9);
  map.fitBounds(COVERAGE, { padding: [20, 20] }); // frame the whole BKK–Eastern corridor
  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    subdomains: "abcd",
    maxZoom: 20,
    attribution:
      '&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
  }).addTo(map);

  cluster = L.markerClusterGroup({
    maxClusterRadius: 45,
    showCoverageOnHover: false,
    spiderfyOnMaxZoom: true,
  });
  map.addLayer(cluster);

  buildChips();
  buildLegend();
  wireUI();
  loadData();
  setInterval(loadData, REFRESH_MS);
}

// ---- Data ----
async function loadData() {
  try {
    const res = await fetch("data/incidents.json?t=" + Date.now(), { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    state.incidents = (data.incidents || []).filter((d) => isFinite(d.lat) && isFinite(d.lng));
    state.updated = data.updated ? new Date(data.updated) : null;
    render();
  } catch (err) {
    console.error("Failed to load incidents:", err);
    document.getElementById("updated").textContent = "โหลดข้อมูลไม่สำเร็จ · load failed";
    document.getElementById("list").innerHTML =
      '<div class="empty">ยังไม่มีข้อมูล หรือโหลดไม่สำเร็จ<br>Run the updater to populate data/incidents.json</div>';
  }
}

// ---- Filtering ----
function withinTime(inc) {
  const t = new Date(inc.reported_at).getTime();
  const now = Date.now();
  if (state.time === "active") {
    if (inc.status === "cleared") return false;
    return now - t <= ACTIVE_WINDOW_H * 3600e3 || inc.status === "active";
  }
  if (state.time === "24h") return now - t <= 24 * 3600e3;
  return now - t <= 7 * 24 * 3600e3; // 7d
}

function visible() {
  return state.incidents
    .filter((i) => state.cats.has(i.category) && state.srcs.has(i.source) && withinTime(i))
    .sort((a, b) => new Date(b.reported_at) - new Date(a.reported_at));
}

function isPast(inc) {
  return inc.status === "cleared" ||
    Date.now() - new Date(inc.reported_at).getTime() > ACTIVE_WINDOW_H * 3600e3;
}

// ---- Render ----
function render() {
  const items = visible();
  renderUpdated();
  renderMarkers(items);
  renderList(items);
  document.getElementById("count").textContent = items.length;
}

function renderMarkers(items) {
  cluster.clearLayers();
  markerById.clear();
  const layers = [];
  for (const inc of items) {
    const m = L.marker([inc.lat, inc.lng], { icon: pinIcon(inc) });
    m.bindPopup(popupHtml(inc), { maxWidth: 280 });
    markerById.set(inc.id, m);
    layers.push(m);
  }
  cluster.addLayers(layers);
}

function pinIcon(inc) {
  const c = CATEGORIES[inc.category] || CATEGORIES.other;
  const cls = ["risk-pin", isPast(inc) ? "past" : "", inc.severity === "high" ? "ring-high" : ""].join(" ");
  return L.divIcon({
    className: "",
    html: `<div class="${cls}" style="background:${c.color}"><span>${c.icon}</span></div>`,
    iconSize: [34, 34],
    iconAnchor: [17, 32],
    popupAnchor: [0, -30],
  });
}

function popupHtml(inc) {
  const c = CATEGORIES[inc.category] || CATEGORIES.other;
  const s = SOURCES[inc.source] || SOURCES.MANUAL;
  const title = inc.title_th || inc.title_en || c.th;
  const link = inc.url
    ? `<div class="pop-src">ที่มา: <a href="${esc(inc.url)}" target="_blank" rel="noopener">${s.label} ↗</a></div>`
    : `<div class="pop-src">ที่มา: <b>${s.label}</b></div>`;
  return `
    <div class="pop-t">${c.icon} ${esc(title)}</div>
    <div class="pop-m">
      ${inc.location_text ? `<b>${esc(inc.location_text)}</b><br>` : ""}
      ประเภท: ${c.th} · ${c.en}<br>
      ระดับ: ${sevTh(inc.severity)} · เวลา: ${fmtTime(inc.reported_at)}
      ${isPast(inc) ? "<br><i>ผ่านไปแล้ว · past</i>" : ""}
    </div>
    ${link}`;
}

function renderList(items) {
  const box = document.getElementById("list");
  if (!items.length) {
    box.innerHTML = '<div class="empty">ไม่พบเหตุการณ์ในตัวกรองนี้<br>No incidents match these filters</div>';
    return;
  }
  box.innerHTML = items
    .map((inc) => {
      const c = CATEGORIES[inc.category] || CATEGORIES.other;
      const s = SOURCES[inc.source] || SOURCES.MANUAL;
      const title = inc.title_th || inc.title_en || c.th;
      return `
      <div class="item ${isPast(inc) ? "past" : ""}" data-id="${esc(inc.id)}">
        <div class="pin" style="background:${c.color}">${c.icon}</div>
        <div class="body">
          <div class="t">${esc(title)}</div>
          <div class="m">
            <span class="src" style="color:${s.color}">${s.label}</span>
            <span class="badge sev-${inc.severity}">${sevTh(inc.severity)}</span>
            <span>${timeAgo(inc.reported_at)}</span>
          </div>
        </div>
      </div>`;
    })
    .join("");

  box.querySelectorAll(".item").forEach((el) => {
    el.addEventListener("click", () => flyTo(el.getAttribute("data-id")));
  });
}

function flyTo(id) {
  const inc = state.incidents.find((i) => i.id === id);
  const m = markerById.get(id);
  if (!inc) return;
  map.flyTo([inc.lat, inc.lng], 15, { duration: 0.6 });
  if (m) setTimeout(() => cluster.zoomToShowLayer(m, () => m.openPopup()), 650);
  if (window.innerWidth <= 820) document.getElementById("sidebar").classList.remove("open");
}

function renderUpdated() {
  const el = document.getElementById("updated");
  if (!state.updated) { el.textContent = "ยังไม่มีข้อมูลอัปเดต"; return; }
  el.textContent = "อัปเดตล่าสุด " + fmtTime(state.updated) + " · " + timeAgo(state.updated);
}

// ---- UI construction ----
function buildChips() {
  const catBox = document.getElementById("catChips");
  catBox.innerHTML = Object.entries(CATEGORIES)
    .map(([k, c]) =>
      `<button class="chip cat active" data-cat="${k}" style="--cat:${c.color}">
         <span class="ic">${c.icon}</span>${c.th}
       </button>`)
    .join("");

  const srcBox = document.getElementById("srcChips");
  srcBox.innerHTML = Object.entries(SOURCES)
    .map(([k, s]) =>
      `<button class="chip src active" data-src="${k}">
         <span class="swatch" style="background:${s.color}"></span>${s.label}
       </button>`)
    .join("");
}

function buildLegend() {
  const box = document.getElementById("legend");
  box.innerHTML =
    "<h3>สัญลักษณ์ · Legend</h3>" +
    Object.values(CATEGORIES)
      .map((c) => `<div class="row"><span class="sw" style="background:${c.color}">${c.icon}</span>${c.th} · ${c.en}</div>`)
      .join("");
}

function wireUI() {
  document.getElementById("timeChips").addEventListener("click", (e) => {
    const b = e.target.closest(".chip"); if (!b) return;
    state.time = b.dataset.time;
    setActiveOnly("#timeChips", b);
    render();
  });

  document.getElementById("catChips").addEventListener("click", (e) => {
    const b = e.target.closest(".chip"); if (!b) return;
    toggle(state.cats, b.dataset.cat, b);
    render();
  });

  document.getElementById("srcChips").addEventListener("click", (e) => {
    const b = e.target.closest(".chip"); if (!b) return;
    toggle(state.srcs, b.dataset.src, b);
    render();
  });

  document.getElementById("menuToggle").addEventListener("click", () => {
    document.getElementById("sidebar").classList.toggle("open");
  });
}

function toggle(set, key, btn) {
  if (set.has(key)) { set.delete(key); btn.classList.remove("active"); }
  else { set.add(key); btn.classList.add("active"); }
}
function setActiveOnly(sel, btn) {
  document.querySelectorAll(sel + " .chip").forEach((c) => c.classList.remove("active"));
  btn.classList.add("active");
}

// ---- Helpers ----
function sevTh(s) { return s === "high" ? "สูง" : s === "low" ? "ต่ำ" : "ปานกลาง"; }
function esc(s) {
  return String(s).replace(/[&<>"']/g, (m) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
}
function fmtTime(d) {
  const dt = new Date(d);
  return dt.toLocaleString("th-TH", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    timeZone: "Asia/Bangkok",
  });
}
function timeAgo(d) {
  const s = (Date.now() - new Date(d).getTime()) / 1000;
  if (s < 60) return "เมื่อสักครู่";
  if (s < 3600) return Math.floor(s / 60) + " นาทีที่แล้ว";
  if (s < 86400) return Math.floor(s / 3600) + " ชม.ที่แล้ว";
  return Math.floor(s / 86400) + " วันที่แล้ว";
}
