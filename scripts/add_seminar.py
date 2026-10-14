#!/usr/bin/env python3
"""Set the next seminar and archive the seminar that was previously next."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "seminars.yaml"
YEAR_LINE = re.compile(r"(?m)^  - year:\s*(\d+)\s*$")


def prompt_required(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print(f"{label} cannot be empty.")


def prompt_date() -> dt.date:
    while True:
        value = input("Seminar date (DD.MM.YYYY): ").strip()
        try:
            return dt.datetime.strptime(value, "%d.%m.%Y").date()
        except ValueError:
            print("Enter a valid date in DD.MM.YYYY format.")


def prompt_old_year(date_text: str) -> int:
    match = re.search(r"\b(19|20)\d{2}\b", date_text)
    if match:
        return int(match.group())

    while True:
        value = input(f"Year of the seminar currently listed as next ({date_text}): ").strip()
        try:
            year = int(value)
        except ValueError:
            year = 0
        if 1900 <= year <= 2200:
            return year
        print("Enter a four-digit year.")


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


def old_seminars_to_archive(data: dict[str, object]) -> list[tuple[int, dict[str, object]]]:
    next_data = data.get("next", {})
    if not isinstance(next_data, dict):
        raise ValueError("Expected a mapping under 'next' in data/seminars.yaml.")
    entries = next_data.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("Expected a list at next.entries in data/seminars.yaml.")

    archive: list[tuple[int, dict[str, object]]] = []
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
                "The current next seminar is only partly filled in. Complete or remove it "
                "before adding the replacement."
            )

        year_value = entry.get("year")
        if year_value is None:
            year = prompt_old_year(date_text)
        else:
            try:
                year = int(year_value)
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid year on the current next seminar: {year_value}") from error
            if not 1900 <= year <= 2200:
                raise ValueError(f"Invalid year on the current next seminar: {year_value}")

        old_entry: dict[str, object] = {"date": date_text}
        if not missing(place):
            old_entry["place"] = place
        old_entry["talks"] = meaningful_talks
        archive.append((year, old_entry))
    return archive


def format_entry(entry: dict[str, object], indent: int) -> str:
    key_indent = indent + 2
    talk_indent = indent + 4
    talk_key_indent = indent + 6
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


def replace_next_section(text: str, entry: dict[str, object], year: int) -> str:
    items_match = re.search(r"(?m)^items:\s*$", text)
    if not items_match:
        raise ValueError("Could not find the top-level 'items:' section in data/seminars.yaml.")
    next_match = re.search(r"(?m)^next:\s*$", text)
    if next_match and next_match.start() > items_match.start():
        raise ValueError("The 'next:' section must appear before 'items:'.")
    start = next_match.start() if next_match else items_match.start()

    lines = [
        "next:",
        "  entries:",
        f"    - year: {year}",
        f'      date: {quote(entry["date"])}',
    ]
    if entry.get("place"):
        lines.append(f'      place: {quote(entry["place"])}')
    lines.extend(
        [
            "      talks:",
            f'        - title: {quote(entry["talks"][0]["title"])}',
            f'          speaker: {quote(entry["talks"][0]["speaker"])}',
        ]
    )
    new_section = "\n".join(lines) + "\n\n"
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
        entries_match = re.search(
            r"(?m)^    entries:\s*$",
            text[matching[0]:block_end],
        )
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
    upcoming: dict[str, object],
    archive: list[tuple[int, dict[str, object]]],
) -> str:
    updated = replace_next_section(text, upcoming, int(upcoming["year"]))
    for year, entry in reversed(archive):
        updated = insert_archived_entry(updated, year, entry)
    parsed = yaml.safe_load(updated)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        raise ValueError("The updated seminar data did not retain a valid 'items' list.")
    if parsed.get("next", {}).get("entries", [{}])[0].get("date") != upcoming["date"]:
        raise ValueError("The updated seminar data did not retain the new next seminar.")
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="show the changes without writing the file")
    args = parser.parse_args(argv)

    text = DATA_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError("Expected a YAML mapping in data/seminars.yaml.")
    if "Next" in data:
        raise ValueError("Use the lowercase 'next:' key in data/seminars.yaml.")

    archive = old_seminars_to_archive(data)
    seminar_date = prompt_date()
    time = prompt_required("Time (for example, 10:30 am)")
    place = input("Place (optional): ").strip()
    title = prompt_required("Talk title")
    speaker = prompt_required("Speaker")
    date_label = f"{seminar_date.strftime('%B')} {ordinal(seminar_date.day)}, {time}"
    upcoming: dict[str, object] = {
        "year": seminar_date.year,
        "date": date_label,
        "talks": [{"title": title, "speaker": speaker}],
    }
    if place:
        upcoming["place"] = place

    updated_text = build_updated_text(text, upcoming, archive)
    action = "Would set" if args.dry_run else "Set"
    print(f"{action} next seminar: {date_label} — {title} ({speaker})")
    if archive:
        print(f"{action} {len(archive)} previous next seminar(s) in the past-seminar archive.")
    else:
        print("There was no complete previous next seminar to archive.")
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
