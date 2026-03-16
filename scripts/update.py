#!/usr/bin/env python3
import json
import os
import re
import time
import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from pypdf import PdfReader
from io import BytesIO
from xml.sax.saxutils import escape

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
SITE_DIR = BASE_DIR / "site"
DOCS_JSON = DATA_DIR / "documents.json"
SEEN_JSON = DATA_DIR / "seen_ids.json"

FEEDS = [
    {
        "name": "Besvarede spørgsmål",
        "type": "Besvaret spørgsmål",
        "url": "https://www.ft.dk/da/abonnementservice/subscription/newsrss?feed=rss&catId=%7B38552A8D-2C86-4FA7-808A-C79AA82AE5EB%7D%7C20251,uru/spm/54",
    },
    {
        "name": "FOU alm. del",
        "type": "Alm. del",
        "url": "https://www.ft.dk/da/abonnementservice/subscription/newsrss?feed=rss&catId=%7BEB5EC0F4-5AEB-43E9-B413-A8AD3323C55C%7D%7CFOU",
    },
    {
        "name": "FOU paragraf 20",
        "type": "Paragraf 20",
        "url": "https://www.ft.dk/da/abonnementservice/subscription/newsrss?feed=rss&catId=%7B8661D858-A850-4F5A-9C07-9DDA264922CC%7D%7CFOU",
    },
]

PROMPT = """
Du er analytiker for en dansk public affairs-rådgiver med fokus på forsvar og forsvarsindustri.

Din opgave er at vurdere relevansen af et dokument fra Folketinget for en læser, der især følger:
- forsvarsanskaffelser
- materielindkøb
- kapacitetsopbygning
- leverandører og industri
- forsyningssikkerhed
- produktion, vedligehold og logistiske kapaciteter
- lovgivning og politiske beslutninger med betydning for forsvarsindustrien

Du skal være konservativ: Hvis dokumentet kan have meningsfuld betydning for anskaffelser, kapaciteter eller industrien, skal det hellere få en lidt højere score end en for lav.

Ignorér normalt emner som:
- soldaters løn- og ansættelsesvilkår
- personalesager
- krænkelser
- interne HR-forhold
- generelle trivsels- eller arbejdspladssager
medmindre de meget konkret påvirker anskaffelser, kontrakter, kapaciteter eller industrien.

Returnér kun gyldig JSON i dette format:
{
  "score": 1,
  "title_better": "...",
  "summary": "...",
  "document_type": "...",
  "asker": "...",
  "recipient": "...",
  "main_topic": "...",
  "procurement_relevance": true,
  "companies_mentioned": ["..."],
  "capabilities_mentioned": ["..."],
  "authorities_mentioned": ["..."],
  "programs_or_bills_mentioned": ["..."],
  "why_relevant": "..."
}

Scoringsregler:
5 = direkte og væsentlig relevans for anskaffelser, kapaciteter, leverandører eller industri
4 = tydelig indirekte relevans med sandsynlig betydning for anskaffelser eller industri
3 = mulig sekundær relevans, værd at kende
2 = begrænset relevans
1 = ikke relevant
""".strip()

CSS = """
:root {
  color-scheme: light;
  --bg: #f7f8fa;
  --card: #ffffff;
  --border: #d9dee7;
  --text: #16202a;
  --muted: #5b6878;
  --accent: #0b5cab;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  margin: 0;
}
.container {
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px;
}
header { margin-bottom: 20px; }
h1 { margin: 0 0 8px; font-size: 32px; }
.meta { color: var(--muted); }
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin: 20px 0 24px;
}
.stat, .card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px;
}
.controls {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
select, input {
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: white;
}
.card { margin-bottom: 14px; }
.card-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: start;
}
.badge {
  display: inline-block;
  min-width: 48px;
  text-align: center;
  padding: 6px 10px;
  border-radius: 999px;
  font-weight: 700;
  background: #ebf3ff;
  color: var(--accent);
}
.small { color: var(--muted); font-size: 14px; }
.facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
  margin-top: 12px;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
ul.tags { list-style: none; padding: 0; margin: 6px 0 0; display: flex; flex-wrap: wrap; gap: 6px; }
ul.tags li {
  padding: 5px 8px;
  border-radius: 999px;
  background: #eef2f7;
  font-size: 13px;
}
"""

JS = """
const docs = window.DOCS || [];
const listEl = document.getElementById('list');
const scoreEl = document.getElementById('minScore');
const typeEl = document.getElementById('docType');
const searchEl = document.getElementById('search');

function uniq(values) {
  return [...new Set(values.filter(Boolean))].sort();
}

function renderOptions() {
  const types = uniq(docs.map(d => d.feed_name));
  typeEl.innerHTML = '<option value="">Alle feedtyper</option>' +
    types.map(t => `<option value="${t}">${t}</option>`).join('');
}

function tags(items) {
  if (!items || !items.length) return '';
  return `<ul class="tags">${items.slice(0, 8).map(i => `<li>${i}</li>`).join('')}</ul>`;
}

function card(doc) {
  return `
    <article class="card">
      <div class="card-top">
        <div>
          <div class="small">${doc.feed_name} · ${doc.document_type || doc.source_type || ''}</div>
          <h3>${doc.title_better || doc.title}</h3>
        </div>
        <div class="badge">${doc.score}/5</div>
      </div>
      <p>${doc.summary || ''}</p>
      <div class="facts">
        <div><strong>Spørger</strong><br>${doc.asker || 'Ukendt'}</div>
        <div><strong>Adressat</strong><br>${doc.recipient || 'Ukendt'}</div>
        <div><strong>Emne</strong><br>${doc.main_topic || 'Ukendt'}</div>
        <div><strong>Anskaffelsesrelevans</strong><br>${doc.procurement_relevance ? 'Ja' : 'Nej'}</div>
      </div>
      <div class="small" style="margin-top:12px"><strong>Hvorfor relevant:</strong> ${doc.why_relevant || ''}</div>
      <div class="small" style="margin-top:10px"><strong>Virksomheder:</strong> ${doc.companies_mentioned?.join(', ') || 'Ingen nævnt'}</div>
      ${tags([...(doc.capabilities_mentioned || []), ...(doc.authorities_mentioned || []), ...(doc.programs_or_bills_mentioned || [])])}
      <div style="margin-top:12px"><a href="${doc.link}" target="_blank" rel="noopener noreferrer">Åbn original</a></div>
    </article>
  `;
}

function render() {
  const minScore = Number(scoreEl.value || 1);
  const type = typeEl.value;
  const term = (searchEl.value || '').toLowerCase().trim();

  const filtered = docs.filter(doc => {
    if ((doc.score || 0) < minScore) return false;
    if (type && doc.feed_name !== type) return false;
    if (!term) return true;
    const haystack = JSON.stringify(doc).toLowerCase();
    return haystack.includes(term);
  });

  listEl.innerHTML = filtered.map(card).join('') || '<p>Ingen dokumenter matcher filtrene.</p>';
}

renderOptions();
render();
scoreEl.addEventListener('change', render);
typeEl.addEventListener('change', render);
searchEl.addEventListener('input', render);
"""


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_feed_entries() -> List[Dict[str, Any]]:
    items = []
    for feed in FEEDS:
        parsed = feedparser.parse(feed["url"])
        for entry in parsed.entries:
            item_id = entry.get("id") or entry.get("guid") or entry.get("link")
            items.append(
                {
                    "uid": item_id,
                    "title": entry.get("title", ""),
                    "summary": BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ", strip=True),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "feed_name": feed["name"],
                    "source_type": feed["type"],
                }
            )
    return items


def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_pdf_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        absolute = urljoin(base_url, href)
        if ".pdf" in absolute.lower():
            links.append(absolute)
    seen = set()
    result = []
    for link in links:
        if link not in seen:
            result.append(link)
            seen.add(link)
    return result[:2]


def extract_pdf_text(url: str) -> str:
    try:
        response = requests.get(url, timeout=45)
        response.raise_for_status()
        reader = PdfReader(BytesIO(response.content))
        pages = []
        for page in reader.pages[:8]:
            pages.append(page.extract_text() or "")
        return clean_text("\n".join(pages))[:12000]
    except Exception as exc:
        return f"[Kunne ikke læse PDF: {exc}]"


def extract_document_text(url: str) -> Dict[str, Any]:
    response = requests.get(url, timeout=45, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    selectors = [
        "main",
        "article",
        ".content-area",
        ".article-content",
        ".main-content",
        "body",
    ]
    text = ""
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = node.get_text(" ", strip=True)
            if len(text) > 500:
                break
    text = clean_text(text)[:18000]
    pdf_links = extract_pdf_links(soup, url)
    pdf_texts = []
    for pdf_url in pdf_links:
        pdf_texts.append(extract_pdf_text(pdf_url))
        time.sleep(1)

    combined = text
    if pdf_texts:
        combined += "\n\nVEDHÆFTET PDF-TEKST:\n" + "\n\n".join(pdf_texts)

    return {
        "page_title": clean_text(soup.title.get_text()) if soup.title else "",
        "text": combined[:22000],
        "pdf_links": pdf_links,
    }


def extract_json(text: str) -> Dict[str, Any]:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("Kunne ikke finde JSON i modelsvar")
    return json.loads(match.group(0))


def analyze_with_openai(entry: Dict[str, Any], document: Dict[str, Any]) -> Dict[str, Any]:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")

    payload = f"""
METADATA
- Feed: {entry['feed_name']}
- Kildetype: {entry['source_type']}
- Titel i RSS: {entry['title']}
- Link: {entry['link']}
- Publiceret: {entry['published']}
- Sidetitel: {document.get('page_title', '')}

RSS-RESUMÉ
{entry['summary']}

DOKUMENTTEKST
{document['text']}
""".strip()

    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": payload},
        ],
    )
    output_text = getattr(response, "output_text", None)
    if not output_text:
        output_text = str(response)
    return extract_json(output_text)


def normalize_result(entry: Dict[str, Any], document: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    def as_list(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        return []

    score = int(analysis.get("score", 1))
    if score < 1:
        score = 1
    if score > 5:
        score = 5

    return {
        "uid": entry["uid"],
        "link": entry["link"],
        "title": entry["title"],
        "published": entry["published"],
        "feed_name": entry["feed_name"],
        "source_type": entry["source_type"],
        "page_title": document.get("page_title", ""),
        "pdf_links": document.get("pdf_links", []),
        "score": score,
        "title_better": analysis.get("title_better", entry["title"]),
        "summary": analysis.get("summary", ""),
        "document_type": analysis.get("document_type", entry["source_type"]),
        "asker": analysis.get("asker", ""),
        "recipient": analysis.get("recipient", ""),
        "main_topic": analysis.get("main_topic", ""),
        "procurement_relevance": bool(analysis.get("procurement_relevance", False)),
        "companies_mentioned": as_list(analysis.get("companies_mentioned", [])),
        "capabilities_mentioned": as_list(analysis.get("capabilities_mentioned", [])),
        "authorities_mentioned": as_list(analysis.get("authorities_mentioned", [])),
        "programs_or_bills_mentioned": as_list(analysis.get("programs_or_bills_mentioned", [])),
        "why_relevant": analysis.get("why_relevant", ""),
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }


def build_feed(documents: List[Dict[str, Any]]) -> str:
    items = []
    for doc in documents:
        if doc["score"] < 4:
            continue
        description = escape(
            f"Score: {doc['score']}/5\n{doc.get('summary', '')}\nHvorfor relevant: {doc.get('why_relevant', '')}"
        )
        title = escape(f"[{doc['score']}/5] {doc.get('title_better') or doc.get('title')}")
        link = escape(doc["link"])
        pub = escape(doc.get("published") or doc.get("processed_at"))
        guid = escape(doc["uid"])
        items.append(
            f"<item><title>{title}</title><link>{link}</link><guid>{guid}</guid><pubDate>{pub}</pubDate><description>{description}</description></item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        '<title>FOU Monitor - filtreret feed</title>'
        '<description>Kun dokumenter med score 4-5</description>'
        '<link>./index.html</link>'
        + "".join(items)
        + '</channel></rss>'
    )


def build_html(documents: List[Dict[str, Any]]) -> str:
    docs_json = json.dumps(documents, ensure_ascii=False)
    today = datetime.now().strftime("%d.%m.%Y %H:%M")
    stats = {
        "Samlet": len(documents),
        "Score 5": len([d for d in documents if d["score"] == 5]),
        "Score 4": len([d for d in documents if d["score"] == 4]),
        "Score 3": len([d for d in documents if d["score"] == 3]),
    }
    stat_html = "".join(
        f'<div class="stat"><div class="small">{k}</div><div style="font-size:28px;font-weight:700">{v}</div></div>'
        for k, v in stats.items()
    )
    return f"""<!doctype html>
<html lang="da">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FOU Monitor</title>
  <style>{CSS}</style>
</head>
<body>
  <div class="container">
    <header>
      <h1>FOU Monitor</h1>
      <div class="meta">Automatisk vurdering af Folketingets FOU-dokumenter med fokus på anskaffelser, kapaciteter og forsvarsindustri. Senest opdateret: {today}</div>
      <div class="meta"><a href="./feed.xml">Åbn filtreret RSS-feed</a></div>
    </header>
    <section class="stats">{stat_html}</section>
    <section class="controls">
      <select id="minScore">
        <option value="4" selected>Vis score 4-5</option>
        <option value="3">Vis score 3-5</option>
        <option value="1">Vis alle</option>
      </select>
      <select id="docType"></select>
      <input id="search" type="search" placeholder="Søg i emner, virksomheder, kapaciteter">
    </section>
    <section id="list"></section>
  </div>
  <script>window.DOCS = {docs_json};</script>
  <script>{JS}</script>
</body>
</html>"""


def main() -> None:
    ensure_dirs()
    existing_docs = load_json(DOCS_JSON, [])
    seen_ids = set(load_json(SEEN_JSON, []))
    entries = fetch_feed_entries()
    new_entries = [e for e in entries if e["uid"] not in seen_ids]

    processed = []
    for entry in new_entries:
        try:
            print(f"Behandler: {entry['title']}")
            document = extract_document_text(entry["link"])
            analysis = analyze_with_openai(entry, document)
            processed.append(normalize_result(entry, document, analysis))
            seen_ids.add(entry["uid"])
            time.sleep(1)
        except Exception as exc:
            print(f"FEJL ved {entry['link']}: {exc}")

    all_docs = processed + existing_docs
    all_docs.sort(key=lambda d: d.get("processed_at", ""), reverse=True)

    save_json(DOCS_JSON, all_docs)
    save_json(SEEN_JSON, sorted(seen_ids))
    save_json(SITE_DIR / "documents.json", all_docs)
    (SITE_DIR / "feed.xml").write_text(build_feed(all_docs), encoding="utf-8")
    (SITE_DIR / "index.html").write_text(build_html(all_docs), encoding="utf-8")
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")


if __name__ == "__main__":
    main()
