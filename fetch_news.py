"""মায়ামি নিউজ ফেচার: Google News RSS + Open-Meteo আবহাওয়া -> news.json
শুধু Python-এর বিল্ট-ইন লাইব্রেরি লাগে, কিছু ইনস্টল করতে হবে না।
ঐচ্ছিক: ANTHROPIC_API_KEY সেট থাকলে হেডলাইন থেকে AI ব্রিফ বানায়।
"""
import json, os, re, html, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

CATEGORIES = {
    "Top": "Miami",
    "Local": "Miami-Dade County",
    "Sports": "Miami Heat OR Miami Dolphins OR Inter Miami OR Miami Hurricanes",
    "Business": "Miami business OR Miami real estate",
    "Weather": "Miami weather OR hurricane Florida",
    "Culture": "Miami restaurants OR Miami art OR Miami events",
}
PER_CATEGORY = 30
UA = {"User-Agent": "Mozilla/5.0 (MiamiNewsBot)"}


def get(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def fetch_category(name, query):
    url = ("https://news.google.com/rss/search?q="
           + urllib.parse.quote(query + " when:2d")
           + "&hl=en-US&gl=US&ceid=US:en")
    items = []
    root = ET.fromstring(get(url))
    for it in root.iter("item"):
        title = html.unescape(it.findtext("title", "")).strip()
        source = (it.findtext("source") or "").strip()
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        try:
            ts = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc)
        except Exception:
            continue
        items.append({
            "title": title,
            "source": source or "News",
            "link": it.findtext("link", ""),
            "time": ts.isoformat(),
            "cat": name,
        })
    return items


def weather():
    url = ("https://api.open-meteo.com/v1/forecast?latitude=25.7617&longitude=-80.1918"
           "&current=temperature_2m,apparent_temperature,wind_speed_10m,weather_code"
           "&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=America%2FNew_York")
    c = json.loads(get(url))["current"]
    return {"temp": round(c["temperature_2m"]), "feels": round(c["apparent_temperature"]),
            "wind": round(c["wind_speed_10m"]), "code": c["weather_code"]}


def ai_brief(items):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or not items:
        return ""
    lang = os.environ.get("BRIEF_LANG", "Bengali")
    heads = "\n".join("- " + i["title"] for i in items[:30])
    prompt = (f"Below are today's Miami news headlines. Write a short daily brief in {lang}: "
              f"4 to 5 bullet points, one sentence each, in your own words. "
              f"Use only what the headlines say; do not invent details.\n\n{heads}")
    body = json.dumps({"model": os.environ.get("MODEL", "claude-haiku-5-5"), "max_tokens": 600,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    hdr = {"content-type": "application/json", "x-api-key": key,
           "anthropic-version": "2023-06-01"}
    res = json.loads(get("https://api.anthropic.com/v1/messages", body, hdr))
    return "".join(b.get("text", "") for b in res["content"]).strip()


def main():
    seen, all_items = set(), []
    for name, q in CATEGORIES.items():
        try:
            got = fetch_category(name, q)
        except Exception as e:
            print("skip", name, e)
            continue
        got.sort(key=lambda x: x["time"], reverse=True)
        for it in got[:PER_CATEGORY]:
            k = re.sub(r"\W+", "", it["title"].lower())[:60]
            if k in seen:
                continue
            seen.add(k)
            all_items.append(it)
    all_items.sort(key=lambda x: x["time"], reverse=True)

    out = {"updated": datetime.now(timezone.utc).isoformat(),
           "weather": None, "brief": "", "items": all_items}
    try:
        out["weather"] = weather()
    except Exception as e:
        print("weather failed", e)
    try:
        out["brief"] = ai_brief(all_items)
    except Exception as e:
        print("brief failed", e)

    if not all_items:  # কিছু না এলে পুরোনো ফাইল রেখে দাও
        print("no items; keeping old news.json")
        return
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("saved", len(all_items), "items")


if __name__ == "__main__":
    main()
