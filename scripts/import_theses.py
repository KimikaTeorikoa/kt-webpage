#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://www.ehu.eus/chemistry/theory/3_publications/thesis/"
HTML_PATH = Path("/tmp/kt-thesis.html")
DATA_PATH = ROOT / "data" / "theses.yaml"
PDF_DIR = ROOT / "static" / "files" / "theses"


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def clean_text(value: str) -> str:
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = value.replace("\u00a0", " ")
    value = value.replace("“", '"').replace("”", '"').replace("’", "'")
    value = value.replace("&#8220;", '"').replace("&#8221;", '"')
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t\n\r\".,")


def yaml_quote(value: str) -> str:
    value = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{value}"'


def get_html() -> str:
    if HTML_PATH.exists():
        return HTML_PATH.read_text(encoding="utf-8", errors="replace")
    with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def make_absolute(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return "https://www.ehu.eus" + url
    return "https://www.ehu.eus/chemistry/theory/" + url


def download_pdf(url: str, filename: str) -> bool:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    target = PDF_DIR / filename
    if target.exists() and target.stat().st_size > 1024:
        return True
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            content = response.read()
    except (urllib.error.URLError, TimeoutError):
        return False
    if not content.startswith(b"%PDF"):
        return False
    target.write_bytes(content)
    return True


def parse_theses() -> list[dict[str, object]]:
    page = get_html()
    content_match = re.search(
        r'<div class="entry-content[^"]*">(.*?)</div>\s*</article>',
        page,
        flags=re.S,
    )
    if content_match is None:
        raise RuntimeError("Could not find .entry-content in thesis page")
    content = content_match.group(1)

    theses: list[dict[str, object]] = []
    for paragraph in re.findall(r"<p\b[^>]*>(.*?)</p>", content, flags=re.S | re.I):
        text = clean_text(paragraph)
        if not re.match(r"^\d+\s*\.?", text):
            continue

        number_match = re.match(r"^(\d+)\s*\.?", text)
        number = int(number_match.group(1)) if number_match else 0

        author_match = re.search(r"<span\b[^>]*>(.*?)</span>", paragraph, flags=re.S | re.I)
        author = clean_text(author_match.group(1)) if author_match else ""

        title_match = re.search(r"<em\b[^>]*>(.*?)</em>", paragraph, flags=re.S | re.I)
        title = clean_text(title_match.group(1)) if title_match else ""

        year_match = re.search(r"\((\d{4})\)", text)
        year = int(year_match.group(1)) if year_match else None

        supervisor_match = re.search(r"\bSupervisors?\s*:\s*(.+)$", text)
        supervisors: list[str] = []
        notes = ""
        if supervisor_match:
            supervisor_blob = supervisor_match.group(1)
            note_match = re.search(r"\b(Doctorado Europeo|Premio|ISBN|Publisher)\b", supervisor_blob)
            if note_match:
                notes = clean_text(supervisor_blob[note_match.start() :])
                supervisor_blob = supervisor_blob[: note_match.start()]
            supervisor_blob = supervisor_blob.replace(" y ", ", ")
            supervisors = [clean_text(item) for item in supervisor_blob.split(",") if clean_text(item)]

        link_match = re.search(r'<a\b[^>]*href=["\']([^"\']+)["\']', paragraph, flags=re.S | re.I)
        original_url = make_absolute(link_match.group(1)) if link_match else ""
        pdf = ""
        pdf_status = ""
        if original_url.lower().endswith(".pdf"):
            filename = f"{number:02d}-{slugify(author or title)}.pdf"
            if download_pdf(original_url, filename):
                pdf = f"/files/theses/{filename}"
                pdf_status = "downloaded"
            else:
                pdf_status = "unavailable"

        thesis: dict[str, object] = {
            "number": number,
            "status": "defended",
            "author": author,
            "title": title,
            "year": year,
            "supervisors": supervisors,
        }
        if pdf:
            thesis["pdf"] = pdf
        if original_url:
            thesis["original_url"] = original_url
        if pdf_status:
            thesis["pdf_status"] = pdf_status
        if notes:
            thesis["notes"] = notes
        theses.append(thesis)

    return sorted(
        theses,
        key=lambda item: (int(item.get("year") or 0), int(item["number"])),
        reverse=True,
    )


def write_yaml(theses: list[dict[str, object]]) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Generated from https://www.ehu.eus/chemistry/theory/3_publications/thesis/",
        "items:",
    ]
    for thesis in theses:
        if thesis.get("number") is not None:
            lines.append(f"  - number: {thesis['number']}")
        else:
            lines.append("  -")
        lines.append(f"    status: {yaml_quote(str(thesis.get('status', 'defended')))}")
        lines.append(f"    author: {yaml_quote(str(thesis['author']))}")
        lines.append(f"    title: {yaml_quote(str(thesis['title']))}")
        for key in ("year", "start_year"):
            if thesis.get(key):
                lines.append(f"    {key}: {thesis[key]}")
        if thesis.get("defense_date"):
            lines.append(f"    defense_date: {yaml_quote(str(thesis['defense_date']))}")
        supervisors = thesis.get("supervisors") or []
        lines.append("    supervisors:")
        if supervisors:
            for supervisor in supervisors:
                lines.append(f"      - {yaml_quote(str(supervisor))}")
        else:
            lines.append("      []")
        for key in ("pdf", "pdf_url", "original_url", "pdf_status", "notes"):
            if thesis.get(key):
                lines.append(f"    {key}: {yaml_quote(str(thesis[key]))}")
    DATA_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    theses = parse_theses()
    write_yaml(theses)
    with_pdf = sum(1 for thesis in theses if thesis.get("pdf"))
    unavailable = sum(1 for thesis in theses if thesis.get("pdf_status") == "unavailable")
    print(f"Imported {len(theses)} theses")
    print(f"Downloaded PDFs: {with_pdf}")
    print(f"Unavailable PDFs: {unavailable}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
