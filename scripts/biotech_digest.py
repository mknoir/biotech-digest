#!/usr/bin/env python3
import os, re, json, sys, datetime, hashlib
from pathlib import Path

import feedparser
from html import unescape

ROOT = Path(__file__).resolve().parents[1]
DIGEST_DIR = ROOT / "digest"
DATA_DIR = ROOT / "data"
SEEN_FILE = DATA_DIR / "seen.json"
SOURCES = ROOT / "scripts" / "sources.yaml"
README = ROOT / "README.md"

try:
    import yaml
except ImportError:
    print("Missing PyYAML; install from requirements.txt", file=sys.stderr); sys.exit(1)

def slug(s: str) -> str:
    s = re.sub(r"\s+", "-", s.strip().lower())
    return re.sub(r"[^a-z0-9\-]", "", s)

def load_seen():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SEEN_FILE.exists():
        with SEEN_FILE.open() as f: return json.load(f)
    return {"hashes": [], "max_len": 2000}

def save_seen(state):
    with SEEN_FILE.open("w") as f: json.dump(state, f, indent=2)

def hash_item(title, link):
    h = hashlib.sha256()
    h.update((title or "").encode())
    h.update((link or "").encode())
    return h.hexdigest()

def summarize(text: str, max_chars=280) -> str:
    if not text: return ""
    txt = unescape(re.sub("<[^<]+?>", "", text)).strip()
    if len(txt) <= max_chars: return txt
    return txt[: max_chars - 1].rstrip() + "…"

def load_config():
    with open(SOURCES) as f:
        cfg = yaml.safe_load(f)
    kw = [re.compile(k, re.I) for k in cfg.get("keywords", [])]
    feeds = cfg.get("feeds", [])
    return feeds, kw

def matches_keywords(title, summary, kw_regexes):
    hay = f"{title or ''}\n{summary or ''}"
    return any(k.search(hay) for k in kw_regexes)

def render_digest(date_str, items):
    if not items:
        return f"# Biotech Daily Digest — {date_str}\n\n_No matching items today._\n"
    
    lines = [f"# Biotech Daily Digest — {date_str}\n"]
    
    # Add summary section
    by_source = {}
    for it in items:
        by_source.setdefault(it["source"], []).append(it)
    
    lines.append(f"**{len(items)} items from {len(by_source)} sources**\n")
    
    # Add source breakdown
    source_counts = [(source, len(arr)) for source, arr in sorted(by_source.items())]
    lines.append("## Summary by Source\n")
    for source, count in source_counts:
        lines.append(f"- {source}: {count} item{'s' if count != 1 else ''}")
    lines.append("")
    
    # Add detailed sections
    for source, arr in sorted(by_source.items()):
        lines.append(f"\n## {source}\n")
        for it in arr:
            title = it["title"] or "(untitled)"
            link = it["link"] or ""
            summary = it["summary"] or ""
            pub = it.get("published", "")
            lines.append(f"- **[{title}]({link})**  \n  _{pub}_  \n  {summary}\n")
    return "\n".join(lines).strip() + "\n"

def update_readme(date_str):
    DIGEST_PATH = f"digest/{date_str}.md"
    link = f"[{date_str} Digest]({DIGEST_PATH})"
    header = "# Biotech Daily Digest\n"
    template = (
        f"{header}\n- Latest: {link}\n\n"
        "This repo auto-collects biotech news/preprints that match our interests "
        "(lab automation, qPCR/ELISA, robotics, organ-on-chip, etc.).\n"
    )
    README.write_text(template)

def main():
    today = datetime.date.today().isoformat()
    DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    feeds, kw = load_config()
    seen = load_seen()

    collected = []
    for f in feeds:
        d = feedparser.parse(f["url"])
        for e in d.entries:
            title = getattr(e, "title", "")
            link = getattr(e, "link", "")
            summary = getattr(e, "summary", "") or getattr(e, "description", "")
            pub = getattr(e, "published", "") or getattr(e, "updated", "")
            item_hash = hash_item(title, link)
            if item_hash in seen["hashes"]: 
                continue
            if kw and not matches_keywords(title, summary, kw):
                continue
            collected.append({
                "source": f["name"],
                "title": title,
                "link": link,
                "summary": summarize(summary, 320),
                "published": pub
            })
            seen["hashes"].append(item_hash)

    # Keep seen list capped
    if len(seen["hashes"]) > seen["max_len"]:
        seen["hashes"] = seen["hashes"][-seen["max_len"]:]

    digest_md = render_digest(today, collected)
    (DIGEST_DIR / f"{today}.md").write_text(digest_md, encoding="utf-8")
    save_seen(seen)
    update_readme(today)
    print(f"Wrote digest for {today} with {len(collected)} items.")

if __name__ == "__main__":
    main()
