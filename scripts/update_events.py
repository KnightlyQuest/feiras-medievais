import json
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

JSON_PATH = Path("data/events-2026.json")

def load_existing():
    if JSON_PATH.exists() and JSON_PATH.stat().st_size > 0:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def normalize(s):
    return re.sub(r'\s+', ' ', s.strip().lower())

def is_duplicate(existing, new_event):
    new_norm = normalize(new_event.get("name", ""))
    for ev in existing:
        if normalize(ev.get("name", "")) == new_norm:
            return True
    return False

def scrape_source(source_name, url, parser_func):
    print(f"🔍 Scraping {source_name}...")
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        events = parser_func(r.text)
        print(f"   → Found {len(events)} potential events from {source_name}")
        return events
    except Exception as e:
        print(f"   ❌ Error scraping {source_name}: {e}")
        return []

# ====================== SCRAPERS ======================

def parse_wetravelportugal(html):
    soup = BeautifulSoup(html, "html.parser")
    events = []
    for item in soup.find_all(['h2', 'h3']):
        name = item.get_text(strip=True)
        if len(name) < 8 or not any(kw in name.lower() for kw in ["medieval", "feira", "festival", "viagem"]):
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
            "link": "https://wetravelportugal.com/medieval-fairs-portugal/",
            "maps_query": name + " Portugal"
        })
    return events

def parse_aondevamos(html):
    soup = BeautifulSoup(html, "html.parser")
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
            "link": "https://aondevamos.pt/feiras-medievais/",
            "maps_query": name + " Portugal"
        })
    return events

def parse_feirasmedievais(html):
    soup = BeautifulSoup(html, "html.parser")
    events = []
    for tag in soup.find_all(["h2", "h3", "strong", "a"]):
        text = tag.get_text(strip=True)
        if any(kw in text.lower() for kw in ["feira medieval", "viagem medieval", "encontro viking", "história viva", "dias medievais"]):
            events.append({
                "name": text,
                "dates": "2026",
                "location": "Portugal",
                "month": "2026",
                "region": "Portugal",
                "desc": "Evento do calendário feirasmedievais.pt",
                "link": "https://feirasmedievais.pt/",
                "maps_query": text + " Portugal"
            })
    return events

# ====================== MAIN ======================

def main():
    existing = load_existing()
    print(f"📊 Loaded {len(existing)} existing events from JSON.\n")

    all_new = []

    # Scrape each source
    all_new.extend(scrape_source("WeTravelPortugal", 
                                 "https://wetravelportugal.com/medieval-fairs-portugal/", 
                                 parse_wetravelportugal))

    all_new.extend(scrape_source("AondeVamos", 
                                 "https://aondevamos.pt/feiras-medievais/", 
                                 parse_aondevamos))

    all_new.extend(scrape_source("FeirasMedievais.pt", 
                                 "https://feirasmedievais.pt/", 
                                 parse_feirasmedievais))

    # Add only new events
    added = 0
    added_sources = {}
    
    for ev in all_new:
        if not is_duplicate(existing, ev):
            source = ev.get("link", "Unknown")
            if "wetravelportugal" in source:
                src_name = "WeTravelPortugal"
            elif "aondevamos" in source:
                src_name = "AondeVamos"
            elif "feirasmedievais" in source:
                src_name = "FeirasMedievais.pt"
            else:
                src_name = "Unknown"

            existing.append(ev)
            added += 1
            added_sources[src_name] = added_sources.get(src_name, 0) + 1

    # Save updated JSON
    existing.sort(key=lambda x: x.get("dates", ""))
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    # Final report
    print("\n" + "="*50)
    print("✅ SCRAPING SUMMARY")
    print("="*50)
    if added > 0:
        print(f"🎉 Added {added} new event(s):")
        for src, count in added_sources.items():
            print(f"   • {src}: {count} new event(s)")
    else:
        print("No new events found this run.")
    
    print(f"📁 Total events in JSON now: {len(existing)}")
    print("="*50)

if __name__ == "__main__":
    main()
