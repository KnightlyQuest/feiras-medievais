import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

JSON_PATH = Path("data/events-2026.json")

def load_existing():
    if JSON_PATH.exists() and JSON_PATH.stat().st_size > 0:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def normalize_name(name):
    return re.sub(r'\s+', ' ', name.strip().lower())

def should_replace(existing_event, new_event):
    """Return True if we should replace the existing event with the new one"""
    # Always prefer feirasmedievais.pt as the authoritative source
    if "feirasmedievais.pt" in new_event.get("link", ""):
        return True
    return False

def is_duplicate(existing, new_event):
    new_norm = normalize_name(new_event.get("name", ""))
    for ev in existing:
        if normalize_name(ev.get("name", "")) == new_norm:
            # If new event is from official source, we will replace it later
            if should_replace(ev, new_event):
                return False  # allow replacement
            return True       # keep existing
    return False

# ====================== SCRAPERS ======================

def scrape_feirasmedievais():
    url = "https://feirasmedievais.pt/"
    print("🔍 Scraping official source: feirasmedievais.pt")
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, timeout=20, headers=headers)
        soup = BeautifulSoup(r.text, "html.parser")
        events = []

        for block in soup.find_all(["div", "section"], class_=re.compile("event|feira|card|green", re.I)):
            title = block.find(["h2", "h3", "strong"])
            if not title:
                continue
            name = title.get_text(strip=True)
            if len(name) < 10:
                continue

            date_tag = block.find(string=re.compile(r"\d{1,2}.*\d{4}"))
            location_tag = block.find(string=re.compile(r"Castelo|Algarve|Norte|Centro|Lisboa|Alentejo|Bragança|Guimarães|Tomar|Óbidos|Sintra|Vagos|Sesimbra", re.I))

            events.append({
                "name": name,
                "dates": date_tag.strip() if date_tag else "2026",
                "location": location_tag.strip() if location_tag else "Portugal",
                "month": "2026",
                "region": "Portugal",
                "desc": "Evento oficial listado em feirasmedievais.pt",
                "link": url,
                "maps_query": name + " Portugal"
            })
        print(f"   → Found {len(events)} events from feirasmedievais.pt")
        return events
    except Exception as e:
        print(f"   ❌ Error scraping feirasmedievais.pt: {e}")
        return []

def scrape_wetravelportugal():
    url = "https://wetravelportugal.com/medieval-fairs-portugal/"
    print("🔍 Scraping WeTravelPortugal...")
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        events = []
        for item in soup.find_all(['h2', 'h3']):
            name = item.get_text(strip=True)
            if len(name) < 10 or not any(k in name.lower() for k in ["medieval", "feira", "festival"]):
                continue
            next_p = item.find_next("p")
            desc = next_p.get_text(strip=True)[:400] if next_p else ""
            events.append({
                "name": name,
                "dates": "2026 (datas a confirmar)",
                "location": "Portugal",
                "month": "2026",
                "region": "Portugal",
                "desc": desc or "Evento medieval em Portugal",
                "link": url,
                "maps_query": name + " Portugal"
            })
        print(f"   → Found {len(events)} events from WeTravelPortugal")
        return events
    except Exception as e:
        print(f"   ❌ Error scraping WeTravelPortugal: {e}")
        return []

def scrape_aondevamos():
    url = "https://aondevamos.pt/feiras-medievais/"
    print("🔍 Scraping AondeVamos...")
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        events = []
        for h3 in soup.find_all("h3"):
            name = h3.get_text(strip=True)
            if len(name) < 10:
                continue
            dates_tag = h3.find_next(string=re.compile(r"\d+.*202[6-7]"))
            dates = dates_tag.strip() if dates_tag else "2026"
            events.append({
                "name": name,
                "dates": dates,
                "location": "Portugal",
                "month": "2026",
                "region": "Portugal",
                "desc": "Feira medieval listada em aondevamos.pt",
                "link": url,
                "maps_query": name + " Portugal"
            })
        print(f"   → Found {len(events)} events from AondeVamos")
        return events
    except Exception as e:
        print(f"   ❌ Error scraping AondeVamos: {e}")
        return []

# ====================== MAIN ======================

def main():
    existing = load_existing()
    print(f"📊 Loaded {len(existing)} existing events.\n")

    all_new = []
    all_new.extend(scrape_feirasmedievais())   # Official source first → highest priority
    all_new.extend(scrape_wetravelportugal())
    all_new.extend(scrape_aondevamos())

    added = 0
    replaced = 0

    for ev in all_new:
        if not is_duplicate(existing, ev):
            existing.append(ev)
            added += 1
        elif "feirasmedievais.pt" in ev.get("link", ""):
            # Replace existing with official version
            for i, old in enumerate(existing):
                if normalize_name(old.get("name", "")) == normalize_name(ev.get("name", "")):
                    existing[i] = ev
                    replaced += 1
                    break

    existing.sort(key=lambda x: x.get("dates", ""))

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Update completed!")
    print(f"   • New events added: {added}")
    print(f"   • Events replaced with official source: {replaced}")
    print(f"   • Total events in JSON: {len(existing)}")

if __name__ == "__main__":
    main()
