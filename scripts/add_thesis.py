#!/usr/bin/env python3
"""Interactively add a thesis and optional PDF to the site."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "theses.yaml"
PDF_DIR = ROOT / "static" / "files" / "theses"
SOURCE_URL = "https://www.ehu.eus/chemistry/theory/3_publications/thesis/"


def prompt_required(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print(f"{label} cannot be empty.")


def prompt_date() -> dt.date:
    while True:
        value = input("Defense date (DD.MM.YYYY): ").strip()
        try:
            return dt.datetime.strptime(value, "%d.%m.%Y").date()
        except ValueError:
            print("Enter a valid date in DD.MM.YYYY format.")


def parse_supervisors(value: str) -> list[str]:
    supervisors = [name.strip() for name in value.split(",") if name.strip()]
    if not supervisors:
        raise ValueError("Enter at least one supervisor.")
    return supervisors


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value)).strip("-")


def quote(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def load_theses() -> tuple[dict[str, object], list[dict[str, object]]]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Thesis data file does not exist: {DATA_PATH}")
    data = yaml.safe_load(DATA_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Expected a YAML mapping in data/theses.yaml.")
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("Expected a list under 'items' in data/theses.yaml.")
    if any(not isinstance(item, dict) for item in items):
        raise ValueError("Every thesis in data/theses.yaml must be a mapping.")
    return data, items


def next_number(items: list[dict[str, object]]) -> int:
    numbers = []
    for item in items:
        if item.get("number") is not None:
            try:
                numbers.append(int(item["number"]))
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid thesis number: {item['number']!r}") from error
    return max(numbers, default=0) + 1


def build_pdf_target(author: str, title: str, defense_date: dt.date) -> Path:
    name = f"{defense_date.isoformat()}-{slugify(author)}-{slugify(title)[:60]}.pdf"
    return PDF_DIR / name


def prompt_pdf() -> tuple[Path | None, str | None]:
    while True:
        choice = input("PDF: [l]ocal file, [e]xternal URL, [n]one (default n): ").strip().lower()
        if choice in {"", "n", "none"}:
            return None, None
        if choice in {"l", "local"}:
            return Path(prompt_required("PDF file path")).expanduser(), None
        if choice in {"e", "external"}:
            url = prompt_required("External PDF URL")
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("Enter a valid external PDF URL starting with http:// or https://.")
            return None, url
        print("Choose local, external, or none.")


def serialize_data(data: dict[str, object]) -> str:
    body = yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=1000,
    )
    serialized = f"# Generated from {SOURCE_URL}\n{body}"
    if not isinstance(yaml.safe_load(serialized), dict):
        raise ValueError("Could not serialize updated thesis data.")
    return serialized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="show changes without copying or writing")
    args = parser.parse_args(argv)

    data, items = load_theses()
    defense_date = prompt_date()
    title = prompt_required("Thesis title")
    author = prompt_required("Author")
    supervisors = parse_supervisors(prompt_required("Supervisor(s), separated by commas"))
    pdf_source, pdf_url = prompt_pdf()

    pdf_target: Path | None = None
    if pdf_source:
        if not pdf_source.is_file():
            raise FileNotFoundError(f"PDF file does not exist: {pdf_source}")
        if pdf_source.suffix.lower() != ".pdf":
            raise ValueError("The thesis file must have a .pdf extension.")
        with pdf_source.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                raise ValueError(f"The selected file is not a valid PDF: {pdf_source}")
        pdf_target = build_pdf_target(author, title, defense_date)
        if pdf_target.exists():
            raise FileExistsError(f"PDF destination already exists: {pdf_target}")

    normalized_title = title.casefold()
    normalized_author = author.casefold()
    if any(
        str(item.get("title", "")).casefold() == normalized_title
        and str(item.get("author", "")).casefold() == normalized_author
        for item in items
    ):
        raise ValueError("A thesis with this title and author is already listed.")

    entry: dict[str, object] = {
        "number": next_number(items),
        "status": "defended",
        "author": author,
        "title": title,
        "defense_date": defense_date.isoformat(),
        "year": defense_date.year,
        "supervisors": supervisors,
    }
    if pdf_target:
        entry["pdf"] = f"/files/theses/{pdf_target.name}"
    if pdf_url:
        entry["pdf_url"] = pdf_url

    updated_data = dict(data)
    updated_data["items"] = [*items, entry]
    updated_text = serialize_data(updated_data)

    action = "Would add" if args.dry_run else "Added"
    print(f"{action} thesis: {title} ({defense_date.isoformat()})")
    if pdf_target and pdf_source:
        print(f"{'Would copy' if args.dry_run else 'Copied'} PDF to {pdf_target.relative_to(ROOT)}")
    if pdf_url:
        print(f"PDF URL: {pdf_url}")
    if args.dry_run:
        print("Dry run: thesis data and files were not changed.")
        return 0

    if pdf_target and pdf_source:
        PDF_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf_source, pdf_target)
    try:
        DATA_PATH.write_text(updated_text, encoding="utf-8")
    except OSError:
        if pdf_target and pdf_target.exists():
            pdf_target.unlink()
        raise

    print(f"Updated {DATA_PATH.relative_to(ROOT)}")
    print("The thesis list will sort by defense date and number entries automatically at build time.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (FileNotFoundError, FileExistsError, ValueError, yaml.YAMLError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
