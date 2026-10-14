#!/usr/bin/env python3
"""Add an upcoming seminar and archive the ones whose date has already passed.

Upcoming seminars live under `next.entries` in data/seminars.yaml, each with an
ISO `iso` date. A seminar stays there until its day is over; then it moves to
the past-seminar archive (this script does it, and the Hugo templates also
classify by date at build time).
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "seminars.yaml"
YEAR_LINE = re.compile(r"(?m)^  - year:\s*(\d+)\s*$")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}


def prompt_required(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print(f"{label} cannot be empty.")


def prompt_date(label: str) -> dt.date:
    while True:
        value = input(f"{label} (DD.MM.YYYY): ").strip()
        try:
            return dt.datetime.strptime(value, "%d.%m.%Y").date()
        except ValueError:
            print("Enter a valid date in DD.MM.YYYY format.")


def ordinal(day: int) -> str:
    if 11 <= day % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def quote(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def missing(value: object) -> bool:
    text = str(value or "").strip().casefold()
    text = re.sub(r"^(date|place|title|speaker):\s*", "", text)
    return text in {"", "tba", "to be announced", "to be confirmed", "unknown"}


def entry_iso(entry: dict[str, object]) -> str | None:
    """ISO date of an entry, read from `iso` or derived from its text and year."""
    iso = str(entry.get("iso") or "").strip()[:10]
    if ISO_DATE.fullmatch(iso):
        return iso
    text = str(entry.get("date", ""))
    day_match = re.search(r"([A-Za-z]+)\s+(\d{1,2})", text)
    year_match = re.search(r"\b(?:19|20)\d{2}\b", text)
    year = entry.get("year") or (year_match.group() if year_match else None)
    if day_match and year and day_match.group(1).lower() in MONTHS:
        try:
            return dt.date(int(year), MONTHS[day_match.group(1).lower()], int(day_match.group(2))).isoformat()
        except ValueError:
            return None
    return None


def split_next_entries(
    data: dict[str, object], today: dt.date
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return (still upcoming, already past) entries from `next.entries`."""
    next_data = data.get("next", {})
    if not isinstance(next_data, dict):
        raise ValueError("Expected a mapping under 'next' in data/seminars.yaml.")
    entries = next_data.get("entries") or []
    if not isinstance(entries, list):
        raise ValueError("Expected a list at next.entries in data/seminars.yaml.")

    upcoming: list[dict[str, object]] = []
    past: list[dict[str, object]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Every entry under next.entries must be a mapping.")
        talks = entry.get("talks", [])
        if not isinstance(talks, list) or any(not isinstance(talk, dict) for talk in talks):
            raise ValueError("Expected a list of talk mappings under next.entries.")

        date_text = str(entry.get("date", "")).strip()
        place = str(entry.get("place", "")).strip()
        meaningful_talks = [
            talk
            for talk in talks
            if not missing(talk.get("title")) or not missing(talk.get("speaker"))
        ]
        if missing(date_text) and missing(place) and not meaningful_talks:
            continue
        if missing(date_text) or not meaningful_talks:
            raise ValueError(
                "A next seminar is only partly filled in. Complete or remove it first."
            )

        iso = entry_iso(entry)
        if iso is None:
            iso = prompt_date(f"Date of the seminar listed as '{date_text}'").isoformat()

        normalized: dict[str, object] = {"iso": iso, "date": date_text}
        if not missing(place):
            normalized["place"] = place
        normalized["talks"] = meaningful_talks
        (past if iso < today.isoformat() else upcoming).append(normalized)
    return upcoming, past


def format_entry(entry: dict[str, object], indent: int, iso: str | None = None) -> str:
    key_indent = indent + 2
    talk_indent = indent + 4
    talk_key_indent = indent + 6
    if iso:
        lines = [
            f'{" " * indent}- iso: {quote(iso)}',
            f'{" " * key_indent}date: {quote(entry["date"])}',
        ]
    else:
        lines = [f'{" " * indent}- date: {quote(entry["date"])}']
    if entry.get("place"):
        lines.append(f'{" " * key_indent}place: {quote(entry["place"])}')
    lines.append(f'{" " * key_indent}talks:')
    for talk in entry.get("talks", []):
        lines.append(f'{" " * talk_indent}- title: {quote(talk.get("title", ""))}')
        if talk.get("speaker"):
            lines.append(f'{" " * talk_key_indent}speaker: {quote(talk["speaker"])}')
        links = talk.get("links", [])
        if links:
            lines.append(f'{" " * talk_key_indent}links:')
            for link in links:
                lines.append(f'{" " * (talk_key_indent + 2)}- label: {quote(link.get("label", ""))}')
                lines.append(f'{" " * (talk_key_indent + 4)}url: {quote(link.get("url", ""))}')
    return "\n".join(lines) + "\n"


def replace_next_section(text: str, entries: list[dict[str, object]]) -> str:
    items_match = re.search(r"(?m)^items:\s*$", text)
    if not items_match:
        raise ValueError("Could not find the top-level 'items:' section in data/seminars.yaml.")
    next_match = re.search(r"(?m)^next:\s*$", text)
    if next_match and next_match.start() > items_match.start():
        raise ValueError("The 'next:' section must appear before 'items:'.")
    start = next_match.start() if next_match else items_match.start()

    if entries:
        body = "".join(format_entry(entry, 4, iso=str(entry["iso"])) for entry in entries)
        new_section = "next:\n  entries:\n" + body + "\n"
    else:
        new_section = "next:\n  entries: []\n\n"
    return text[:start] + new_section + text[items_match.start():]


def insert_archived_entry(text: str, year: int, entry: dict[str, object]) -> str:
    items_match = re.search(r"(?m)^items:\s*$", text)
    if not items_match:
        raise ValueError("Could not find the top-level 'items:' section in data/seminars.yaml.")
    years = [
        (match.start(), match.end(), int(match.group(1)))
        for match in YEAR_LINE.finditer(text, items_match.end())
    ]
    matching = next((year_line for year_line in years if year_line[2] == year), None)
    serialized = format_entry(entry, indent=6)

    if matching:
        year_index = years.index(matching)
        block_end = years[year_index + 1][0] if year_index + 1 < len(years) else len(text)
        entries_match = re.search(r"(?m)^    entries:\s*$", text[matching[0]:block_end])
        if not entries_match:
            raise ValueError(f"Could not find entries for seminar year {year}.")
        insert_at = matching[0] + entries_match.end()
        if text[insert_at:insert_at + 1] == "\n":
            insert_at += 1
        return text[:insert_at] + serialized + "\n" + text[insert_at:]

    year_block = f"  - year: {year}\n    entries:\n{serialized}\n"
    lower_year = next((line for line in years if line[2] < year), None)
    if lower_year:
        insert_at = lower_year[0]
        return text[:insert_at] + year_block + text[insert_at:]
    if years:
        insert_at = len(text.rstrip())
        return text[:insert_at] + "\n\n" + year_block + text[insert_at:] + "\n"

    insert_at = items_match.end()
    if text[insert_at:insert_at + 1] == "\n":
        insert_at += 1
    return text[:insert_at] + year_block + text[insert_at:]


def build_updated_text(
    text: str,
    upcoming: list[dict[str, object]],
    past: list[dict[str, object]],
) -> str:
    updated = replace_next_section(text, upcoming)
    # Oldest first: each one is inserted at the top of its year, so the newest ends up first.
    for entry in sorted(past, key=lambda item: str(item["iso"])):
        archived = {key: value for key, value in entry.items() if key != "iso"}
        updated = insert_archived_entry(updated, int(str(entry["iso"])[:4]), archived)
    parsed = yaml.safe_load(updated)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        raise ValueError("The updated seminar data did not retain a valid 'items' list.")
    if len(parsed["next"]["entries"] or []) != len(upcoming):
        raise ValueError("The updated seminar data did not retain the upcoming seminars.")
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="show the changes without writing the file")
    parser.add_argument(
        "--archive-only",
        action="store_true",
        help="only move seminars whose date has passed to the archive; do not add a new one",
    )
    parser.add_argument("--today", help="override today's date (YYYY-MM-DD), for testing")
    args = parser.parse_args(argv)

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    text = DATA_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError("Expected a YAML mapping in data/seminars.yaml.")
    if "Next" in data:
        raise ValueError("Use the lowercase 'next:' key in data/seminars.yaml.")

    upcoming, past = split_next_entries(data, today)
    new_label = None
    if not args.archive_only:
        seminar_date = prompt_date("Seminar date")
        time = prompt_required("Time (for example, 10:30 am)")
        place = input("Place (optional): ").strip()
        title = prompt_required("Talk title")
        speaker = prompt_required("Speaker")
        iso = seminar_date.isoformat()
        new_label = f"{seminar_date.strftime('%B')} {ordinal(seminar_date.day)}, {time}"
        if any(entry["iso"] == iso and entry["talks"][0].get("title") == title for entry in upcoming + past):
            raise ValueError("That seminar is already listed.")
        entry: dict[str, object] = {
            "iso": iso,
            "date": new_label,
            "talks": [{"title": title, "speaker": speaker}],
        }
        if place:
            entry["place"] = place
        (past if iso < today.isoformat() else upcoming).append(entry)
    upcoming.sort(key=lambda item: str(item["iso"]))

    updated_text = build_updated_text(text, upcoming, past)
    action = "Would" if args.dry_run else "Did"
    if new_label:
        print(f"{action}: add seminar {new_label}.")
    print(f"{action}: keep {len(upcoming)} upcoming seminar(s) under 'Next seminars'.")
    print(f"{action}: archive {len(past)} past seminar(s).")
    if args.dry_run:
        print("Dry run: data/seminars.yaml was not changed.")
    else:
        DATA_PATH.write_text(updated_text, encoding="utf-8")
        print(f"Updated {DATA_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (FileNotFoundError, ValueError, yaml.YAMLError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
