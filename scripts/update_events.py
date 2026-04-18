import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

JSON_PATH = Path("data/events-2026.json")
DEFAULT_YEAR = 2026
HEADERS = {"User-Agent": "Mozilla/5.0"}
FEIRAS_BASE_URL = "https://feirasmedievais.pt/"
FEIRAS_CALENDAR_URL = "https://feirasmedievais.pt/calendario-feiras-medievais-portugal-2024/"

MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
MONTH_RE = r"janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"
MONTHS_DISPLAY = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}

NAME_STOPWORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "de",
    "da",
    "das",
    "do",
    "dos",
    "e",
    "em",
    "festival",
    "feira",
    "medieval",
    "mercado",
    "dias",
    "evento",
    "historico",
    "historia",
    "viva",
    "encontro",
    "viagem",
}

DATE_CONFIDENCE_RANK = {
    "unknown": 0,
    "year_only": 1,
    "month_only": 2,
    "exact_day": 3,
    "exact_range": 4,
}

SOURCE_PRIORITY = {
    "FeirasMedievais.pt": 3,
    "AondeVamos": 2,
    "WeTravelPortugal": 1,
}


def strip_accents(text):
    text = text or ""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_spaces(text):
    return re.sub(r"\s+", " ", (text or "").strip())


def normalize_text(text):
    text = strip_accents(text).lower()
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    return normalize_spaces(text)


def build_loose_name(name):
    tokens = []
    for token in normalize_text(name).split():
        if token in NAME_STOPWORDS:
            continue
        if len(token) <= 1:
            continue
        tokens.append(token)
    return " ".join(tokens)


def month_name_from_iso(iso_date):
    if not iso_date or len(iso_date) < 7:
        return ""
    month_num = int(iso_date[5:7])
    for name, number in MONTHS.items():
        if number == month_num:
            return name
    return ""


def month_display_from_iso(iso_date):
    if not iso_date or len(iso_date) < 7:
        return ""
    try:
        month_num = int(iso_date[5:7])
    except ValueError:
        return ""
    return MONTHS_DISPLAY.get(month_num, "")


def month_display_from_any(month_str):
    m = normalize_text(month_str)
    if not m:
        return ""
    if m in MONTHS:
        return MONTHS_DISPLAY[MONTHS[m]]
    return normalize_spaces(month_str).capitalize()


def make_iso(year, month, day):
    try:
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    except Exception:
        return None


def parse_dates_pt(raw_text, default_year=DEFAULT_YEAR):
    raw = normalize_spaces(raw_text)

    # ISO range: 2026-05-08 -> 2026-05-10
    m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\s*->\s*(20\d{2}-\d{2}-\d{2})\b", raw)
    if m:
        return {
            "start_date": m.group(1),
            "end_date": m.group(2),
            "date_confidence": "exact_range",
        }

    # ISO single day: 2026-05-08
    m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", raw)
    if m:
        return {
            "start_date": m.group(1),
            "end_date": m.group(1),
            "date_confidence": "exact_day",
        }

    text = normalize_text(raw_text)

    # 10 de julho a 13 de julho de 2026
    m = re.search(
        rf"\b(\d{{1,2}})\s+de\s+({MONTH_RE})\s*(?:a|ate|-)\s*(\d{{1,2}})\s+de\s+({MONTH_RE})(?:\s+de\s+(\d{{4}}))?\b",
        text,
    )
    if m:
        d1, m1, d2, m2, year = m.groups()
        year = int(year) if year else default_year
        start_date = make_iso(year, MONTHS[m1], d1)
        end_date = make_iso(year, MONTHS[m2], d2)
        if start_date and end_date:
            return {
                "start_date": start_date,
                "end_date": end_date,
                "date_confidence": "exact_range",
            }

    # 10 a 13 de julho de 2026 OR 10 e 13 de julho de 2026
    m = re.search(
        rf"\b(\d{{1,2}})\s*(?:a|ate|e|-)\s*(\d{{1,2}})\s+de\s+({MONTH_RE})(?:\s+de\s+(\d{{4}}))?\b",
        text,
    )
    if m:
        d1, d2, month, year = m.groups()
        year = int(year) if year else default_year
        start_date = make_iso(year, MONTHS[month], d1)
        end_date = make_iso(year, MONTHS[month], d2)
        if start_date and end_date:
            return {
                "start_date": start_date,
                "end_date": end_date,
                "date_confidence": "exact_range",
            }

    # 10 de julho de 2026 OR 10 de julho
    m = re.search(rf"\b(\d{{1,2}})\s+de\s+({MONTH_RE})(?:\s+de\s+(\d{{4}}))?\b", text)
    if m:
        day, month, year = m.groups()
        year = int(year) if year else default_year
        start_date = make_iso(year, MONTHS[month], day)
        if start_date:
            return {
                "start_date": start_date,
                "end_date": start_date,
                "date_confidence": "exact_day",
            }

    # julho de 2026
    m = re.search(rf"\b({MONTH_RE})(?:\s+de\s+|\s+)(\d{{4}})\b", text)
    if m:
        month, year = m.groups()
        year = int(year)
        return {
            "start_date": f"{year:04d}-{MONTHS[month]:02d}-01",
            "end_date": None,
            "date_confidence": "month_only",
        }

    # 2026
    m = re.search(r"\b(20\d{2})\b", text)
    if m:
        return {
            "start_date": f"{int(m.group(1)):04d}-01-01",
            "end_date": None,
            "date_confidence": "year_only",
        }

    return {
        "start_date": None,
        "end_date": None,
        "date_confidence": "unknown",
    }


def find_location_from_name(name):
    name = normalize_spaces(name)

    if "," in name:
        tail = normalize_spaces(name.split(",")[-1])
        if 1 <= len(tail.split()) <= 5:
            return tail

    m = re.search(r"\b(?:de|do|da)\s+([A-ZÁÂÃÀÉÊÍÓÔÕÚÇ][A-Za-zÁÂÃÀÉÊÍÓÔÕÚÇáâãàéêíóôõúç\- ]{1,40})$", name)
    if m:
        loc = normalize_spaces(m.group(1))
        if 1 <= len(loc.split()) <= 5:
            return loc

    return "Portugal"


def canonical_source_name(url):
    u = (url or "").lower()
    if "feirasmedievais.pt" in u:
        return "FeirasMedievais.pt"
    if "aondevamos.pt" in u:
        return "AondeVamos"
    if "wetravelportugal.com" in u:
        return "WeTravelPortugal"
    return "Unknown"


def format_dates_for_ui(start_date, end_date, confidence):
    if not start_date:
        return ""
    try:
        y1, m1, d1 = [int(x) for x in start_date.split("-")]
        month1 = MONTHS_DISPLAY.get(m1, "")
    except Exception:
        return start_date

    if confidence == "exact_range" and end_date:
        try:
            y2, m2, d2 = [int(x) for x in end_date.split("-")]
            month2 = MONTHS_DISPLAY.get(m2, "")
        except Exception:
            return f"{d1} a ? de {month1} {y1}".strip()

        if y1 == y2 and m1 == m2:
            return f"{d1} a {d2} de {month1} {y1}"
        if y1 == y2:
            return f"{d1} de {month1} a {d2} de {month2} {y1}"
        return f"{d1} de {month1} {y1} a {d2} de {month2} {y2}"

    if confidence == "exact_day":
        return f"{d1} de {month1} {y1}"

    if confidence == "month_only":
        return f"{month1} {y1}"

    if confidence == "year_only":
        return str(y1)

    return f"{d1} de {month1} {y1}"


def is_noise_event_name(name):
    n = normalize_text(name)
    if not n:
        return True
    if "?" in (name or ""):
        return True

    bad_starts = [
        "what ",
        "which ",
        "when ",
        "where ",
        "why ",
        "how ",
        "quem ",
        "como ",
        "porque ",
    ]
    if any(n.startswith(prefix) for prefix in bad_starts):
        return True

    bad_contains = [
        "have we missed",
        "will you be visiting",
        "medieval fairs like in portugal",
        "calendar",
        "calendario",
        "subscribe",
    ]
    if any(token in n for token in bad_contains):
        return True

    return False


def clean_event(event):
    event = dict(event)
    event["name"] = normalize_spaces(event.get("name", ""))
    event["dates"] = normalize_spaces(event.get("dates", ""))
    event["location"] = normalize_spaces(event.get("location", "")) or "Portugal"
    event["month"] = normalize_spaces(event.get("month", ""))
    event["region"] = normalize_spaces(event.get("region", "")) or "Portugal"
    event["desc"] = normalize_spaces(event.get("desc", ""))
    event["link"] = normalize_spaces(event.get("link", ""))
    event["maps_query"] = normalize_spaces(event.get("maps_query", ""))

    if not event["name"] or is_noise_event_name(event["name"]):
        return None

    parsed = parse_dates_pt(event.get("dates", ""))
    if not event.get("start_date"):
        event["start_date"] = parsed["start_date"]
    if not event.get("end_date"):
        event["end_date"] = parsed["end_date"]
    if not event.get("date_confidence"):
        event["date_confidence"] = parsed["date_confidence"]

    if not event["location"] or event["location"].lower() == "portugal":
        event["location"] = find_location_from_name(event["name"])

    if event.get("start_date"):
        if not event["month"]:
            event["month"] = month_display_from_iso(event["start_date"])
        else:
            event["month"] = month_display_from_any(event["month"])
    elif event["month"]:
        event["month"] = month_display_from_any(event["month"])

    iso_only_dates = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:\s*->\s*\d{4}-\d{2}-\d{2})?", event["dates"]))
    if not event["dates"] or iso_only_dates:
        formatted = format_dates_for_ui(event.get("start_date"), event.get("end_date"), event.get("date_confidence"))
        event["dates"] = formatted or event["dates"]

    if not event["dates"]:
        event["dates"] = f"{DEFAULT_YEAR} (datas a confirmar)"

    source = event.get("source") or canonical_source_name(event.get("link", ""))
    event["source"] = source
    event["source_priority"] = int(event.get("source_priority") or SOURCE_PRIORITY.get(source, 0))

    if not event["maps_query"]:
        event["maps_query"] = f"{event['name']} {event['location']} Portugal".strip()

    event["_strict_name"] = normalize_text(event["name"])
    event["_loose_name"] = build_loose_name(event["name"])
    event["_loc_norm"] = normalize_text(event["location"])
    event["_score"] = quality_score(event)

    return event


def quality_score(event):
    score = 0
    score += 10 * int(event.get("source_priority", 0))
    score += 6 * DATE_CONFIDENCE_RANK.get(event.get("date_confidence", "unknown"), 0)

    location_norm = normalize_text(event.get("location", ""))
    if location_norm and location_norm != "portugal":
        score += 2

    if len(event.get("desc", "")) >= 60:
        score += 1

    return score


def location_similar(a, b):
    a = normalize_text(a)
    b = normalize_text(b)

    if not a or not b:
        return True
    if a == b:
        return True

    generic = {"portugal"}
    if a in generic or b in generic:
        return True

    return a in b or b in a


def event_year(event):
    sd = event.get("start_date")
    if sd and len(sd) >= 4:
        return sd[:4]

    m = re.search(r"\b(20\d{2})\b", event.get("dates", ""))
    if m:
        return m.group(1)

    return None


def is_same_event(a, b):
    if a["_strict_name"] == b["_strict_name"]:
        return True

    if a["_loose_name"] and a["_loose_name"] == b["_loose_name"]:
        year_a = event_year(a)
        year_b = event_year(b)
        if (not year_a or not year_b or year_a == year_b) and location_similar(a.get("location", ""), b.get("location", "")):
            return True

    return False


def merge_events(existing, candidate):
    winner = existing
    loser = candidate
    if candidate.get("_score", 0) > existing.get("_score", 0):
        winner = candidate
        loser = existing

    merged = dict(winner)

    for field in ["location", "desc", "month", "maps_query", "region", "link", "source"]:
        if not merged.get(field):
            merged[field] = loser.get(field, "")

    # Prefer better date confidence even if base score ties.
    conf_w = DATE_CONFIDENCE_RANK.get(merged.get("date_confidence", "unknown"), 0)
    conf_l = DATE_CONFIDENCE_RANK.get(loser.get("date_confidence", "unknown"), 0)
    if conf_l > conf_w:
        merged["start_date"] = loser.get("start_date")
        merged["end_date"] = loser.get("end_date")
        merged["date_confidence"] = loser.get("date_confidence")
        merged["dates"] = loser.get("dates")
        merged["month"] = loser.get("month") or merged.get("month", "")

    merged["source_priority"] = max(int(merged.get("source_priority", 0)), int(loser.get("source_priority", 0)))

    merged["_score"] = quality_score(merged)
    return merged


def fetch_html(url):
    response = requests.get(url, timeout=25, headers=HEADERS)
    response.raise_for_status()
    return response.text


def split_candidate_chunks(text):
    text = normalize_spaces(text)
    if not text:
        return []

    parts = [text]
    for sep in [" | ", " • ", " — ", " – ", "; "]:
        next_parts = []
        for part in parts:
            next_parts.extend(part.split(sep))
        parts = next_parts

    cleaned = []
    for part in parts:
        p = normalize_spaces(part)
        if p:
            cleaned.append(p)
    return cleaned


def looks_like_event_line(text):
    n = normalize_text(text)
    if len(n) < 8:
        return False

    junk_markers = [
        "facebook",
        "instagram",
        "youtube",
        "newsletter",
        "cookies",
        "politica de",
        "partilhar",
        "comentarios",
        "ultimos artigos",
        "publicado em",
    ]
    if any(marker in n for marker in junk_markers):
        return False

    event_markers = [
        "feira medieval",
        "dias medievais",
        "mercado medieval",
        "mercado quinhentista",
        "feira quinhentista",
        "festa medieval",
        "feira historica",
        "mercado historico",
        "recriacao historica",
        "jornadas medievais",
        "encontro viking",
        "historia viva",
        "viagem medieval",
        "templarios",
        "torneio medieval",
        "feira franca",
    ]

    if any(marker in n for marker in event_markers):
        return True

    # Fallback: some titles don't use the exact phrases above.
    if any(token in n for token in ["medieval", "quinhentista", "historic", "viking"]):
        return True

    return False


def split_name_and_dates(text):
    line = normalize_spaces(text)
    norm = normalize_text(line)

    # Capture common Portuguese day/month patterns and keep the rest as event name.
    date_pattern = rf"(\d{{1,2}}\s*(?:a|ate|e|-)\s*\d{{1,2}}\s+de\s+(?:{MONTH_RE})(?:\s+de\s+\d{{4}})?|\d{{1,2}}\s+de\s+(?:{MONTH_RE})(?:\s+de\s+\d{{4}})?|(?:{MONTH_RE})\s+de\s+\d{{4}}|\b20\d{{2}}\b)"
    m = re.search(date_pattern, norm)
    if not m:
        return line, line

    start, end = m.span()
    raw_lower = strip_accents(line).lower()
    before = normalize_spaces(line[:start].strip(" -:|,"))
    date_text = normalize_spaces(line[start:end])

    # Try to recover original substring with accents for date.
    date_source = normalize_spaces(raw_lower[start:end])
    if date_source:
        date_text = date_source

    if before and len(before) >= 6:
        return before, date_text

    # If date appears first, try name after separator.
    after = normalize_spaces(line[end:].strip(" -:|,"))
    if after and len(after) >= 6:
        return after, date_text

    return line, date_text


def parse_feirasmedievais():
    url = FEIRAS_CALENDAR_URL
    print("Scraping FeirasMedievais.pt...")
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    keywords = [
        "feira medieval",
        "dias medievais",
        "mercado medieval",
        "viagem medieval",
        "historia viva",
        "encontro viking",
        "templarios",
    ]

    content = soup.select_one("article .entry-content")
    if content is None:
        content = soup.find("article")
    if content is None:
        content = soup.body or soup

    events_by_name = {}

    def upsert_event(name, dates, location, desc, link, month=""):
        name = normalize_spaces(name)
        if len(name) < 8:
            return
        name_norm = normalize_text(name)
        if len(name_norm) < 8:
            return

        dates = normalize_spaces(dates)
        location = normalize_spaces(location) or find_location_from_name(name)
        desc = normalize_spaces(desc)
        month = normalize_spaces(month)
        link = normalize_spaces(link) or url

        if name_norm in events_by_name:
            existing = events_by_name[name_norm]
            if len(dates) > len(existing["dates"]):
                existing["dates"] = dates
            if len(desc) > len(existing["desc"]):
                existing["desc"] = desc[:260]
            if existing.get("location", "").lower() == "portugal" and location.lower() != "portugal":
                existing["location"] = location
            if not existing.get("month") and month:
                existing["month"] = month
            if existing.get("link") == url and link != url:
                existing["link"] = link
            return

        events_by_name[name_norm] = {
            "name": name,
            "dates": dates or f"{DEFAULT_YEAR} (datas a confirmar)",
            "location": location,
            "month": month,
            "region": "Portugal",
            "desc": (desc or name)[:260],
            "link": link,
            "maps_query": f"{name} Portugal",
            "source": "FeirasMedievais.pt",
            "source_priority": SOURCE_PRIORITY["FeirasMedievais.pt"],
        }

    # Pass 1: DOM-aware extraction based on the page structure shown in devtools.
    # Expected nodes: .gl-month (month group), .ev-nome (title), .cal-date, .cal-local.
    for month_block in content.select(".gl-month"):
        month_label = ""
        header_tag = month_block.find(["div", "span", "h2", "h3"], class_=re.compile(r"month", re.I))
        if header_tag:
            month_label = normalize_spaces(header_tag.get_text(" ", strip=True))
        if month_label:
            month_label = month_label.strip(" -:|,").lower()

        for name_tag in month_block.select(".ev-nome"):
            name = normalize_spaces(name_tag.get_text(" ", strip=True))
            if not name:
                continue

            container = name_tag.parent
            date_tag = container.find(class_=re.compile(r"\bcal-date\b", re.I))
            local_tag = container.find(class_=re.compile(r"\bcal-local\b", re.I))
            subtitle_tag = container.find(class_=re.compile(r"\bev-subtitle\b", re.I))

            dates = normalize_spaces(date_tag.get_text(" ", strip=True)) if date_tag else ""
            location = normalize_spaces(local_tag.get_text(" ", strip=True)) if local_tag else find_location_from_name(name)
            subtitle = normalize_spaces(subtitle_tag.get_text(" ", strip=True)) if subtitle_tag else ""

            link_tag = container.find("a", href=True) or name_tag.find("a", href=True)
            link = urljoin(FEIRAS_BASE_URL, link_tag["href"]) if link_tag else url

            desc_parts = [p for p in [dates, location, subtitle] if p]
            desc = " | ".join(desc_parts)

            upsert_event(name=name, dates=dates, location=location, desc=desc, link=link, month=month_label)

    # Pass 2: generic fallback for entries rendered in less structured markup.
    candidate_nodes = content.find_all(["li", "p", "h2", "h3", "h4", "h5", "strong", "a", "td"])
    for node in candidate_nodes:
        node_text = normalize_spaces(node.get_text(" ", strip=True))
        if not node_text:
            continue

        node_link_tag = node if node.name == "a" and node.get("href") else node.find("a", href=True)
        node_link = urljoin(FEIRAS_BASE_URL, node_link_tag["href"]) if node_link_tag else url

        for chunk in split_candidate_chunks(node_text):
            normalized_chunk = normalize_text(chunk)
            if len(normalized_chunk) < 8:
                continue
            if not any(k in normalized_chunk for k in keywords) and not looks_like_event_line(chunk):
                continue

            name, date_text = split_name_and_dates(chunk)
            upsert_event(
                name=name,
                dates=date_text if date_text else chunk,
                location=find_location_from_name(name),
                desc=chunk,
                link=node_link,
                month="",
            )

    return list(events_by_name.values())


def parse_wetravelportugal():
    url = "https://wetravelportugal.com/medieval-fairs-portugal/"
    print("Scraping WeTravelPortugal...")
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    events = []
    seen_names = set()

    for heading in soup.find_all(["h2", "h3"]):
        name = normalize_spaces(heading.get_text(" ", strip=True))
        norm = normalize_text(name)
        if len(name) < 8:
            continue
        if not any(k in norm for k in ["medieval", "feira", "festival", "mercado"]):
            continue
        if norm in seen_names:
            continue
        seen_names.add(norm)

        next_p = heading.find_next("p")
        desc = normalize_spaces(next_p.get_text(" ", strip=True)) if next_p else ""
        desc_norm = normalize_text(desc)
        # Filter FAQ/blog headings; event rows on this source usually include when/where hints.
        if desc and "when" not in desc_norm and "where" not in desc_norm:
            continue
        date_probe = f"{name} {desc}"

        events.append(
            {
                "name": name,
                "dates": date_probe if date_probe.strip() else f"{DEFAULT_YEAR} (datas a confirmar)",
                "location": find_location_from_name(name),
                "month": "",
                "region": "Portugal",
                "desc": desc[:260],
                "link": url,
                "maps_query": f"{name} Portugal",
                "source": "WeTravelPortugal",
                "source_priority": SOURCE_PRIORITY["WeTravelPortugal"],
            }
        )

    return events


def parse_aondevamos():
    url = "https://aondevamos.pt/feiras-medievais/"
    print("Scraping AondeVamos...")
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    events = []
    seen_names = set()

    for h3 in soup.find_all("h3"):
        name = normalize_spaces(h3.get_text(" ", strip=True))
        norm = normalize_text(name)

        if len(name) < 8:
            continue
        if norm in seen_names:
            continue
        seen_names.add(norm)

        nearby = h3.find_next(string=re.compile(r"\d{1,2}.*20\d{2}"))
        date_text = normalize_spaces(nearby) if nearby else f"{DEFAULT_YEAR} (datas a confirmar)"

        events.append(
            {
                "name": name,
                "dates": date_text,
                "location": find_location_from_name(name),
                "month": "",
                "region": "Portugal",
                "desc": "Feira medieval listada em aondevamos.pt",
                "link": url,
                "maps_query": f"{name} Portugal",
                "source": "AondeVamos",
                "source_priority": SOURCE_PRIORITY["AondeVamos"],
            }
        )

    return events


def load_existing():
    if JSON_PATH.exists() and JSON_PATH.stat().st_size > 0:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    return []


def strip_internal_fields(event):
    cleaned = dict(event)
    for key in list(cleaned.keys()):
        if key.startswith("_"):
            cleaned.pop(key, None)
    return cleaned


def to_public_event(event):
    # Keep output schema compatible with the existing frontend/GH JSON.
    public = {
        "name": event.get("name", ""),
        "dates": event.get("dates", ""),
        "location": event.get("location", "Portugal"),
        "month": event.get("month", ""),
        "region": event.get("region", "Portugal"),
        "desc": event.get("desc", ""),
        "link": event.get("link", ""),
    }
    maps_query = event.get("maps_query", "")
    if maps_query:
        public["maps_query"] = maps_query
    return public


def event_sort_key(event):
    start = event.get("start_date") or "9999-12-31"
    return (start, normalize_text(event.get("name", "")))


def scrape_all():
    all_events = []

    sources = [parse_feirasmedievais, parse_aondevamos, parse_wetravelportugal]
    for parser in sources:
        try:
            events = parser()
            print(f"  -> {parser.__name__}: {len(events)} candidate events")
            all_events.extend(events)
        except Exception as e:
            print(f"  -> {parser.__name__} failed: {e}")

    return all_events


def main():
    existing_raw = load_existing()
    print(f"Loaded {len(existing_raw)} existing events.")

    merged = []

    # Seed with existing data (cleaned + normalized)
    for event in existing_raw:
        cleaned = clean_event(event)
        if cleaned:
            merged.append(cleaned)

    # Scrape new data
    new_raw = scrape_all()

    added = 0
    replaced = 0

    for event in new_raw:
        cleaned = clean_event(event)
        if not cleaned:
            continue

        match_index = None
        for i, current in enumerate(merged):
            if is_same_event(current, cleaned):
                match_index = i
                break

        if match_index is None:
            merged.append(cleaned)
            added += 1
        else:
            before = merged[match_index]
            after = merge_events(before, cleaned)
            merged[match_index] = after
            if after.get("_score", 0) > before.get("_score", 0):
                replaced += 1

    merged.sort(key=event_sort_key)
    final_events = [to_public_event(strip_internal_fields(e)) for e in merged]

    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(final_events, f, ensure_ascii=False, indent=2)

    print("\nUpdate completed")
    print(f"- New events added: {added}")
    print(f"- Existing events improved/replaced: {replaced}")
    print(f"- Total events in DB: {len(final_events)}")


if __name__ == "__main__":
    main()
