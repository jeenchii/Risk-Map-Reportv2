#!/usr/bin/env python3
"""
fetch_incidents.py
==================
Builds / refreshes data/incidents.json for the Bangkok Risk & Incident Map.

Pipeline each run:
  1. Load the existing incidents.json (the running 7-day history).
  2. Ingest new incidents from:
       a. data/manual_incidents.csv        <- reliable, curated path (default ON)
       b. source scrapers (JS100/FM91/...)  <- best-effort, OFF unless enabled
  3. Geocode anything without lat/lng (built-in gazetteer -> Nominatim).
  4. Merge + de-duplicate against history.
  5. Recompute active/cleared by age, prune anything older than HISTORY_DAYS.
  6. Write data/incidents.json with a fresh `updated` timestamp (Asia/Bangkok).

No paid APIs are required. GitHub Actions supplies Python, so nothing needs to
be installed on your PC. Run locally with:  python scripts/fetch_incidents.py

Config via environment variables (all optional):
  ACTIVE_WINDOW_HOURS   default 8    incidents newer than this are "active"
  HISTORY_DAYS          default 7    older incidents are dropped
  ENABLE_SCRAPERS       default 0    set to 1 to run the source scrapers
  ENABLE_NOMINATIM      default 1    set to 0 to skip online geocoding
"""

from __future__ import annotations
import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ------------------------------------------------------------------ config
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "incidents.json"
MANUAL_CSV = ROOT / "data" / "manual_incidents.csv"

ICT = timezone(timedelta(hours=7))  # Asia/Bangkok
ACTIVE_WINDOW_HOURS = int(os.getenv("ACTIVE_WINDOW_HOURS", "8"))
HISTORY_DAYS = int(os.getenv("HISTORY_DAYS", "7"))
ENABLE_SCRAPERS = os.getenv("ENABLE_SCRAPERS", "0") == "1"
ENABLE_NOMINATIM = os.getenv("ENABLE_NOMINATIM", "1") == "1"

VALID_CATEGORIES = {
    "accident", "construction", "weather", "flood", "closure", "fire", "other",
}
VALID_SOURCES = {"JS100", "FM91", "RAMA9", "MANUAL"}
VALID_SEVERITY = {"low", "medium", "high"}

# A tiny gazetteer of common Bangkok places so we rarely need the network.
# Add your own frequent locations here (key is a lowercase substring match).
GAZETTEER = {
    "อโศก": (13.7376, 100.5602), "asok": (13.7376, 100.5602),
    "อนุสาวรีย์ชัย": (13.7649, 100.5383), "victory monument": (13.7649, 100.5383),
    "ดินแดง": (13.7695, 100.5497), "din daeng": (13.7695, 100.5497),
    "พระราม 9": (13.7580, 100.5655), "rama 9": (13.7580, 100.5655),
    "พระราม 2": (13.6500, 100.4300), "rama 2": (13.6500, 100.4300),
    "พระราม 8": (13.7660, 100.4990), "rama 8": (13.7660, 100.4990),
    "บางนา": (13.6680, 100.6045), "bang na": (13.6680, 100.6045),
    "รัชดา": (13.7700, 100.5740), "ratchada": (13.7700, 100.5740),
    "เอกมัย": (13.7196, 100.5850), "ekkamai": (13.7196, 100.5850),
    "พญาไท": (13.7570, 100.5340), "phaya thai": (13.7570, 100.5340),
    "ลาดพร้าว": (13.8160, 100.5610), "lat phrao": (13.8160, 100.5610),
    "จตุจักร": (13.8020, 100.5530), "chatuchak": (13.8020, 100.5530),
    "สาทร": (13.7220, 100.5290), "sathorn": (13.7220, 100.5290),
    "ปิ่นเกล้า": (13.7770, 100.4760), "pinklao": (13.7770, 100.4760),
    "วิภาวดี": (13.8200, 100.5620), "vibhavadi": (13.8200, 100.5620),
    "สุขุมวิท": (13.7300, 100.5690), "sukhumvit": (13.7300, 100.5690),
    "พหลโยธิน": (13.8470, 100.5690), "phahonyothin": (13.8470, 100.5690),
    "แจ้งวัฒนะ": (13.8850, 100.5620), "chaeng watthana": (13.8850, 100.5620),
    "ราชดำเนิน": (13.7570, 100.5040), "ratchadamnoen": (13.7570, 100.5040),
    "ประตูน้ำ": (13.7510, 100.5400), "pratunam": (13.7510, 100.5400),
    "ห้วยขวาง": (13.7770, 100.5740), "huai khwang": (13.7770, 100.5740),
    "สีลม": (13.7248, 100.5340), "silom": (13.7248, 100.5340),
    "งามวงศ์วาน": (13.8620, 100.5300), "ngamwongwan": (13.8620, 100.5300),
    "บางกะปิ": (13.7650, 100.6470), "bang kapi": (13.7650, 100.6470),
    "กรุงเทพ": (13.7563, 100.5018), "bangkok": (13.7563, 100.5018),
    # --- Eastern corridor & seaboard (Bangkok -> Chonburi -> Rayong) ---
    "สุวรรณภูมิ": (13.6900, 100.7501), "suvarnabhumi": (13.6900, 100.7501),
    "บางนา-ตราด": (13.5900, 100.7600), "bang na-trat": (13.5900, 100.7600),
    "บางบ่อ": (13.5470, 100.8330), "bang bo": (13.5470, 100.8330),
    "บางปะกง": (13.5290, 100.9970), "bang pakong": (13.5290, 100.9970),
    "ฉะเชิงเทรา": (13.6904, 101.0779), "chachoengsao": (13.6904, 101.0779),
    "มอเตอร์เวย์": (13.5300, 100.9200), "motorway": (13.5300, 100.9200),
    "ชลบุรี": (13.3611, 100.9847), "chonburi": (13.3611, 100.9847),
    "บางแสน": (13.2830, 100.9200), "bang saen": (13.2830, 100.9200),
    "ศรีราชา": (13.1740, 100.9300), "si racha": (13.1740, 100.9300),
    "แหลมฉบัง": (13.0827, 100.8847), "laem chabang": (13.0827, 100.8847),
    "พัทยา": (12.9236, 100.8825), "pattaya": (12.9236, 100.8825),
    "สัตหีบ": (12.6600, 100.9010), "sattahip": (12.6600, 100.9010),
    "อู่ตะเภา": (12.6800, 101.0050), "u-tapao": (12.6800, 101.0050),
    "บ้านฉาง": (12.7200, 101.0700), "ban chang": (12.7200, 101.0700),
    "มาบตาพุด": (12.6800, 101.1500), "map ta phut": (12.6800, 101.1500),
    "ระยอง": (12.6833, 101.2372), "rayong": (12.6833, 101.2372),
}

# --------------------------------------------------------------- utilities
def now_ict() -> datetime:
    return datetime.now(ICT)


def iso(dt: datetime) -> str:
    return dt.astimezone(ICT).isoformat(timespec="seconds")


def parse_dt(value: str | None) -> datetime:
    """Parse an ISO-ish timestamp; default to now (ICT) when blank/invalid."""
    if not value:
        return now_ict()
    v = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(v)
        return dt if dt.tzinfo else dt.replace(tzinfo=ICT)
    except ValueError:
        return now_ict()


def short_hash(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:6]


def log(msg: str) -> None:
    print(f"[fetch] {msg}", flush=True)


# --------------------------------------------------------------- geocoding
def geocode(location_text: str) -> tuple[float, float] | None:
    if not location_text:
        return None
    low = location_text.lower()
    for key, coord in GAZETTEER.items():
        if key in low:
            return coord
    if ENABLE_NOMINATIM:
        return _nominatim(location_text)
    return None


def _nominatim(query: str) -> tuple[float, float] | None:
    """Free OpenStreetMap geocoder. Be polite: identify + rate-limit."""
    try:
        import requests  # imported lazily so CSV-only runs need no deps
    except ImportError:
        return None
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{query}, Bangkok, Thailand", "format": "json", "limit": 1},
            headers={"User-Agent": "bangkok-risk-map/1.0 (github pages static site)"},
            timeout=15,
        )
        time.sleep(1.1)  # respect Nominatim usage policy (<=1 req/sec)
        hits = r.json()
        if hits:
            return float(hits[0]["lat"]), float(hits[0]["lon"])
    except Exception as exc:  # never let geocoding break the run
        log(f"nominatim failed for {query!r}: {exc}")
    return None


# --------------------------------------------------------------- normalize
def normalize(raw: dict) -> dict | None:
    """Validate + fill defaults for one incident. Returns None if unusable."""
    source = (raw.get("source") or "MANUAL").upper()
    if source not in VALID_SOURCES:
        source = "MANUAL"
    category = (raw.get("category") or "other").lower()
    if category not in VALID_CATEGORIES:
        category = "other"
    severity = (raw.get("severity") or "medium").lower()
    if severity not in VALID_SEVERITY:
        severity = "medium"

    reported = parse_dt(str(raw.get("reported_at") or ""))
    location_text = (raw.get("location_text") or "").strip()

    lat, lng = raw.get("lat"), raw.get("lng")
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        coord = geocode(location_text)
        if not coord:
            log(f"skip (no coords): {location_text or raw.get('title_th')!r}")
            return None
        lat, lng = coord

    title_th = (raw.get("title_th") or raw.get("title_en") or location_text or "เหตุการณ์").strip()
    inc_id = raw.get("id") or (
        f"{source.lower()}-{reported.strftime('%Y%m%d-%H%M')}-"
        f"{short_hash(source, category, title_th, f'{lat:.4f}', f'{lng:.4f}')}"
    )

    pinned = bool(raw.get("status"))  # explicit status wins over age-based auto
    status = (raw.get("status") or "active").lower()
    if status not in {"active", "cleared"}:
        status = "active"

    return {
        "id": inc_id,
        "source": source,
        "category": category,
        "severity": severity,
        "title_th": title_th,
        "title_en": (raw.get("title_en") or "").strip(),
        "location_text": location_text,
        "lat": round(lat, 6),
        "lng": round(lng, 6),
        "reported_at": iso(reported),
        "status": status,
        "pinned_status": pinned,
        "url": (raw.get("url") or "").strip(),
    }


# ------------------------------------------------------------------ inputs
def read_manual_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if not any((v or "").strip() for v in row.values()):
                continue  # skip blank lines
            inc = normalize({k: (v or "").strip() for k, v in row.items()})
            if inc:
                out.append(inc)
    log(f"manual CSV: {len(out)} incident(s)")
    return out


# --------------------------------------------------------- source scrapers
# These three sources have NO public API. They publish via app/website + social
# (JS100: js100.com & X @js100radio; FM91: Facebook/TikTok/YouTube; Rama 9:
# rescue radio net). Implement per-source logic below and flip ENABLE_SCRAPERS=1.
# Each function MUST be defensive and return [] on any failure so the twice-daily
# job never turns red.
def fetch_js100() -> list[dict]:
    # TODO: parse js100.com traffic feed, or the X API with a bearer token
    #       (set as a GitHub Actions secret, read via os.getenv("X_BEARER")).
    return []


def fetch_fm91() -> list[dict]:
    # TODO: FM91 posts on Facebook/TikTok/YouTube — needs Graph API / manual entry.
    return []


def fetch_rama9() -> list[dict]:
    # TODO: ศูนย์วิทยุพระราม 9 rescue net — typically manual entry.
    return []


def run_scrapers() -> list[dict]:
    incidents: list[dict] = []
    for name, fn in (("JS100", fetch_js100), ("FM91", fetch_fm91), ("RAMA9", fetch_rama9)):
        try:
            got = fn() or []
            incidents.extend(normalize(x) for x in got)
        except Exception as exc:
            log(f"{name} scraper failed (ignored): {exc}")
    incidents = [i for i in incidents if i]
    log(f"scrapers: {len(incidents)} incident(s)")
    return incidents


# ----------------------------------------------------------- merge / prune
def merge(existing: list[dict], fresh: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {i["id"]: i for i in existing}
    for inc in fresh:
        by_id[inc["id"]] = {**by_id.get(inc["id"], {}), **inc}  # new data wins
    return list(by_id.values())


def recompute_status(incidents: list[dict], now: datetime) -> None:
    cutoff = now - timedelta(hours=ACTIVE_WINDOW_HOURS)
    for inc in incidents:
        if inc.get("pinned_status"):
            continue  # explicit status stays put
        inc["status"] = "active" if parse_dt(inc["reported_at"]) >= cutoff else "cleared"


def prune(incidents: list[dict], now: datetime) -> list[dict]:
    cutoff = now - timedelta(days=HISTORY_DAYS)
    kept = [i for i in incidents if parse_dt(i["reported_at"]) >= cutoff]
    kept.sort(key=lambda i: i["reported_at"], reverse=True)
    return kept


# ------------------------------------------------------------------- main
def main() -> int:
    now = now_ict()
    existing = []
    if DATA.exists():
        try:
            existing = json.loads(DATA.read_text(encoding="utf-8")).get("incidents", [])
        except json.JSONDecodeError as exc:
            log(f"warning: existing incidents.json unreadable ({exc}); starting fresh")

    fresh = read_manual_csv(MANUAL_CSV)
    if ENABLE_SCRAPERS:
        fresh += run_scrapers()
    else:
        log("scrapers disabled (set ENABLE_SCRAPERS=1 to enable)")

    incidents = merge(existing, fresh)
    recompute_status(incidents, now)
    incidents = prune(incidents, now)

    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(
        json.dumps(
            {
                "updated": iso(now),
                "note": "Auto-generated by scripts/fetch_incidents.py",
                "window_hours": ACTIVE_WINDOW_HOURS,
                "history_days": HISTORY_DAYS,
                "incidents": incidents,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    active = sum(1 for i in incidents if i["status"] == "active")
    log(f"wrote {DATA.relative_to(ROOT)} — {len(incidents)} total, {active} active")
    return 0


if __name__ == "__main__":
    sys.exit(main())
