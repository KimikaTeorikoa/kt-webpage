#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://www.ehu.eus/chemistry/theory/5_kt-seminars/past-group-seminars/"
HTML_PATH = Path("/tmp/kt-past-seminars.html")
DATA_PATH = ROOT / "data" / "seminars.yaml"
PDF_DIR = ROOT / "static" / "files" / "seminars"


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def yaml_quote(value: str) -> str:
    value = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{value}"'


def clean_text(value: str) -> str:
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = value.replace("\u00a0", " ")
    value = value.replace("“", '"').replace("”", '"').replace("’", "'")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def split_lines(value: str) -> list[str]:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = value.replace("\u00a0", " ")
    return [line.strip() for line in value.splitlines() if clean_text(line)]


def get_html() -> str:
    if HTML_PATH.exists():
        return HTML_PATH.read_text(encoding="utf-8", errors="replace")
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def make_absolute(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return "https://www.ehu.eus" + url
    return urllib.parse.urljoin(SOURCE_URL, url)


def download_pdf(url: str, label: str) -> str:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    parsed = urllib.parse.urlparse(url)
    source_name = Path(urllib.parse.unquote(parsed.path)).name
    stem = slugify(Path(source_name).stem or label)
    filename = f"{stem}.pdf"
    target = PDF_DIR / filename
    if target.exists() and target.stat().st_size > 1024:
        return f"/files/seminars/{filename}"

    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            content = response.read()
    except (urllib.error.URLError, TimeoutError):
        return url
    if not content.startswith(b"%PDF"):
        return url
    target.write_bytes(content)
    return f"/files/seminars/{filename}"


def extract_links(line: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for href, label in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', line, flags=re.I | re.S):
        url = make_absolute(html.unescape(href))
        clean_label = clean_text(label) or url
        if url.lower().split("?", 1)[0].endswith(".pdf"):
            url = download_pdf(url, clean_label)
        links.append({"label": clean_label, "url": url})
    return links


def parse_entry(item_html: str) -> dict[str, object] | None:
    lines = split_lines(item_html)
    entry: dict[str, object] = {"date": "", "place": "", "talks": []}
    talks: list[dict[str, object]] = []

    for line in lines:
        text = clean_text(line)
        label_match = re.match(r"^(Date|Place|Title|Speaker|Speakers)\s*:\s*(.*)$", text, flags=re.I)
        if not label_match:
            continue
        label = label_match.group(1).lower()
        value = label_match.group(2).strip()

        if label == "date":
            entry["date"] = value
        elif label == "place":
            entry["place"] = value
        elif label == "title":
            talk: dict[str, object] = {"title": value, "speaker": ""}
            links = extract_links(line)
            if links:
                talk["links"] = links
            talks.append(talk)
        elif label in {"speaker", "speakers"}:
            if not talks:
                talks.append({"title": "", "speaker": value})
            else:
                talks[-1]["speaker"] = value

    entry["talks"] = talks
    if not entry.get("date") or not talks:
        return None
    return entry


def content_body(page: str) -> str:
    match = re.search(
        r'<div class="entry-content[^"]*">(.*?)</div>\s*</article>',
        page,
        flags=re.S,
    )
    if match is None:
        raise RuntimeError("Could not find .entry-content in seminar page")
    return match.group(1)


def parse_seminars() -> list[dict[str, object]]:
    content = content_body(get_html())
    years: dict[int, list[dict[str, object]]] = {}

    first_year = re.search(r"<p>\s*<strong>\s*20\d{2}\s*</strong>\s*</p>", content, flags=re.I)
    if first_year:
        intro = content[: first_year.start()]
        for item_html in re.findall(r"<li\b[^>]*>(.*?)</li>", intro, flags=re.S | re.I):
            entry = parse_entry(item_html)
            if entry:
                years.setdefault(2026, []).append(entry)

    year_matches = list(re.finditer(r"<p>\s*<strong>\s*(20\d{2})\s*</strong>\s*</p>", content, flags=re.I))
    for index, year_match in enumerate(year_matches):
        year = int(year_match.group(1))
        start = year_match.end()
        end = year_matches[index + 1].start() if index + 1 < len(year_matches) else len(content)
        block = content[start:end]
        entries: list[dict[str, object]] = []
        for item_html in re.findall(r"<li\b[^>]*>(.*?)</li>", block, flags=re.S | re.I):
            entry = parse_entry(item_html)
            if entry:
                entries.append(entry)
        years.setdefault(year, []).extend(entries)

    return [
        {"year": year, "entries": years[year]}
        for year in sorted(years.keys(), reverse=True)
        if years[year]
    ]


def write_yaml(items: list[dict[str, object]]) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Generated from https://www.ehu.eus/chemistry/theory/5_kt-seminars/past-group-seminars/",
        "items:",
    ]
    for year_item in items:
        lines.append(f"  - year: {year_item['year']}")
        lines.append("    entries:")
        for entry in year_item["entries"]:  # type: ignore[index]
            lines.append(f"      - date: {yaml_quote(str(entry['date']))}")
            if entry.get("place"):
                lines.append(f"        place: {yaml_quote(str(entry['place']))}")
            lines.append("        talks:")
            for talk in entry["talks"]:  # type: ignore[index]
                lines.append(f"          - title: {yaml_quote(str(talk.get('title', '')))}")
                if talk.get("speaker"):
                    lines.append(f"            speaker: {yaml_quote(str(talk['speaker']))}")
                if talk.get("links"):
                    lines.append("            links:")
                    for link in talk["links"]:  # type: ignore[index]
                        lines.append(f"              - label: {yaml_quote(str(link['label']))}")
                        lines.append(f"                url: {yaml_quote(str(link['url']))}")
    DATA_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    print(
        "This was a one-time legacy importer and must not be run again: "
        "it overwrites data/seminars.yaml. Use scripts/add_seminar.py instead.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
