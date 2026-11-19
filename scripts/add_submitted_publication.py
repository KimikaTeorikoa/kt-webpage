#!/usr/bin/env python3
"""Add a submitted publication to the profiles of its listed authors."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import unicodedata
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import yaml

from group_metadata import group_aliases, load_groups, normalize_group_token


ROOT = Path(__file__).resolve().parents[1]
SUBMITTED_FILE = ROOT / "data" / "publications" / "submitted.yaml"
PEOPLE_DIR = ROOT / "content" / "people"
CROSSREF_API = "https://api.crossref.org/works/"
DATACITE_API = "https://api.datacite.org/dois/"
USER_AGENT = "kt-hugoblox-prototype/1.0 (submitted-publication helper)"


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", normalize_text(value))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", normalized.casefold())


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "publication"


def parse_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Date must use YYYY-MM-DD format.") from exc


def normalize_doi(raw: str) -> str:
    value = raw.strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^doi:\s*", "", value, flags=re.IGNORECASE)
    return value.strip()


def looks_like_doi(value: str) -> bool:
    return bool(re.fullmatch(r"10\.\d{4,9}/[^\s<>\"'?#]+", value, flags=re.IGNORECASE))


def fetch_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("The metadata service returned an unexpected response.")
    return payload


def first_text(value: object) -> str:
    if isinstance(value, list):
        return normalize_text(str(value[0])) if value else ""
    return normalize_text(str(value)) if value else ""


def extract_crossref_metadata(record: dict) -> dict[str, object]:
    authors = []
    for author in record.get("author") or []:
        given = normalize_text(str(author.get("given") or ""))
        family = normalize_text(str(author.get("family") or ""))
        name = " ".join(part for part in (given, family) if part)
        if name:
            authors.append(name)

    year = None
    for field in ("published-print", "published-online", "issued", "created"):
        date_parts = (record.get(field) or {}).get("date-parts") or []
        if date_parts and date_parts[0]:
            year = int(date_parts[0][0])
            break
    return {
        "title": first_text(record.get("title")),
        "authors": authors,
        "source": first_text(record.get("container-title") or record.get("publisher")),
        "year": year,
    }


def extract_datacite_metadata(payload: dict) -> dict[str, object]:
    record = (payload.get("data") or {}).get("attributes") or {}
    authors = []
    for creator in record.get("creators") or []:
        name = normalize_text(str(creator.get("name") or ""))
        if not name:
            name = " ".join(
                part
                for part in (
                    normalize_text(str(creator.get("givenName") or "")),
                    normalize_text(str(creator.get("familyName") or "")),
                )
                if part
            )
        if name:
            authors.append(name)

    source = record.get("publisher") or ""
    containers = record.get("container") or []
    if containers and isinstance(containers[0], dict):
        source = containers[0].get("title") or source
    return {
        "title": first_text([item.get("title", "") for item in record.get("titles") or []]),
        "authors": authors,
        "source": normalize_text(str(source)),
        "year": record.get("publicationYear"),
    }


def normalize_source(doi: str, source: str) -> str:
    if doi.lower().startswith("10.26434/"):
        return "ChemRxiv"
    if re.match(r"10\.48550/arxiv\.", doi, flags=re.IGNORECASE):
        return "arXiv"
    if doi.lower().startswith("10.1101/"):
        return "bioRxiv / medRxiv"
    known_sources = {
        "chemrxiv": "ChemRxiv",
        "arxiv": "arXiv",
        "biorxiv": "bioRxiv",
        "medrxiv": "medRxiv",
    }
    return known_sources.get(source.casefold(), source)


def fetch_doi_metadata(doi: str) -> tuple[dict[str, object] | None, list[str]]:
    services = (
        ("Crossref", CROSSREF_API + quote(doi, safe=""), lambda payload: extract_crossref_metadata(payload.get("message") or {})),
        ("DataCite", DATACITE_API + quote(doi, safe=""), extract_datacite_metadata),
    )
    errors = []
    for service, url, extract in services:
        try:
            metadata = extract(fetch_json(url))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{service}: {exc}")
            continue
        if metadata["title"] or metadata["authors"]:
            metadata["source"] = normalize_source(doi, str(metadata["source"] or ""))
            return metadata, errors
        errors.append(f"{service}: no title or author metadata found")
    return None, errors


def prompt_doi() -> str:
    while True:
        doi = normalize_doi(prompt_value("DOI (optional)"))
        if not doi or looks_like_doi(doi):
            return doi
        print("Enter a valid DOI (for example 10.26434/chemrxiv-12345678) or leave it blank.", file=sys.stderr)


def prompt_value(label: str, initial: str = "") -> str:
    suffix = f" [{initial}]" if initial else ""
    return input(f"{label}{suffix}: ").strip() or initial


def prompt_authors(initial: list[str] | None = None) -> list[str]:
    initial_value = "; ".join(initial or [])
    while True:
        raw = input(f"Authors (separate names with semicolons) [{initial_value}]: ").strip()
        if not raw and initial:
            return initial
        authors = [normalize_text(author) for author in raw.split(";")]
        authors = [author for author in authors if author]
        if authors:
            return authors
        print("Enter at least one author.", file=sys.stderr)


def parse_group_tags(raw: str) -> list[str]:
    groups = load_groups()
    aliases = group_aliases(groups)
    tags = []
    invalid = []
    for value in raw.split(","):
        tag = normalize_text(value)
        if not tag:
            continue
        group = aliases.get(normalize_group_token(tag))
        if group is None:
            invalid.append(tag)
        elif group.label not in tags:
            tags.append(group.label)
    if invalid:
        valid = ", ".join(group.label for group in groups.values())
        raise ValueError(f"Unknown group tag(s): {', '.join(invalid)}. Valid tags: {valid}")
    return tags


def prompt_group_tags() -> list[str]:
    valid_tags = ", ".join(group.label for group in load_groups().values())
    while True:
        raw = input(f"Research group tag(s), comma-separated (optional; {valid_tags}): ").strip()
        try:
            return parse_group_tags(raw)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)


def load_members() -> list[dict[str, object]]:
    members = []
    for path in sorted(PEOPLE_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            continue
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue
        metadata = yaml.safe_load(parts[1]) or {}
        if not isinstance(metadata, dict):
            continue
        member_id = str(metadata.get("id") or path.stem).strip()
        title = normalize_text(str(metadata.get("title") or path.stem))
        title = re.sub(r"^(Prof\.|Dr\.)\s+", "", title, flags=re.IGNORECASE)
        aliases = metadata.get("publication_names") or [title]
        if not isinstance(aliases, list):
            raise ValueError(f"Invalid publication_names in {path}")
        normalized_aliases = {
            normalize_name(str(alias))
            for alias in [*aliases, title]
            if normalize_name(str(alias))
        }
        members.append({
            "id": member_id,
            "name": title,
            "aliases": normalized_aliases,
        })
    return members


def author_name_variants(author: str) -> set[str]:
    variants = {normalize_name(author)}
    if "," in author:
        family, given = author.split(",", 1)
        variants.add(normalize_name(f"{given} {family}"))
    return {variant for variant in variants if variant}


def matching_members(author: str, members: list[dict[str, object]]) -> list[dict[str, object]]:
    variants = author_name_variants(author)
    return [
        member
        for member in members
        if variants.intersection(member["aliases"])
    ]


def choose_member(author: str, members: list[dict[str, object]]) -> str | None:
    print(f"\nSelect a profile to associate with author: {author}")
    for index, member in enumerate(members, start=1):
        print(f"  {index}. {member['name']}")
    print("  0. Do not associate this author with a profile")
    while True:
        raw = input("Profile number: ").strip()
        if raw.isdigit() and 0 <= int(raw) <= len(members):
            selected = int(raw)
            return str(members[selected - 1]["id"]) if selected else None
        print(f"Enter a number from 0 to {len(members)}.", file=sys.stderr)


def resolve_profile_ids(
    authors: list[str], members: list[dict[str, object]]
) -> list[str]:
    profile_ids = []
    for author in authors:
        matches = matching_members(author, members)
        selected_id: str | None = None
        if len(matches) == 1:
            member = matches[0]
            selected_id = str(member["id"])
            print(f"Matched author '{author}' to profile: {member['name']}")
        elif len(matches) > 1:
            print(f"Author '{author}' matches multiple profiles.")
            selected_id = choose_member(author, matches)
        else:
            print(f"No team profile matched author '{author}'.")
            associate = input("Associate this author with a team member? [y/N]: ").strip().lower()
            if associate in {"y", "yes"}:
                selected_id = choose_member(author, members)
        if selected_id and selected_id not in profile_ids:
            profile_ids.append(selected_id)
    return profile_ids


def load_submissions() -> dict:
    if not SUBMITTED_FILE.exists():
        return {"items": []}
    with SUBMITTED_FILE.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {"items": []}
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError(f"Invalid submitted-publications file: {SUBMITTED_FILE}")
    return data


def submission_exists(data: dict, title: str, authors: list[str]) -> bool:
    normalized_title = normalize_text(title).casefold()
    normalized_authors = {normalize_text(author).casefold() for author in authors}
    for item in data["items"]:
        if normalize_text(str(item.get("title", ""))).casefold() != normalized_title:
            continue
        existing_authors = {
            normalize_text(str(author)).casefold()
            for author in item.get("authors", [])
        }
        if existing_authors == normalized_authors:
            return True
    return False


def prompt_year(initial: object = "") -> int | None:
    default = str(initial or "")
    while True:
        raw = prompt_value("Publication year (optional)", default)
        if not raw:
            return None
        if raw.isdigit() and 1000 <= int(raw) <= 9999:
            return int(raw)
        print("Enter a four-digit year or leave it blank.", file=sys.stderr)


def write_submissions(data: dict) -> None:
    SUBMITTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=SUBMITTED_FILE.parent,
        prefix=f".{SUBMITTED_FILE.name}.",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        yaml.safe_dump(
            data,
            temporary,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=1000,
        )
    temporary_path.replace(SUBMITTED_FILE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Add a submitted publication to its authors' profile pages."
    )
    parser.add_argument("--date", type=parse_date, help="Submission date (YYYY-MM-DD).")
    parser.add_argument(
        "--tags",
        help="Comma-separated research-group tags, e.g. MatCat-KT.",
    )
    args = parser.parse_args(argv)

    print("Add submitted publication")
    doi = prompt_doi()
    metadata: dict[str, object] = {}
    if doi:
        print(f"Looking up DOI {doi} ...")
        metadata, errors = fetch_doi_metadata(doi)
        if metadata:
            print("Metadata found; review or edit the suggested title and authors below.")
        else:
            print("No title/author metadata could be retrieved; enter the details manually.", file=sys.stderr)
            for error in errors:
                print(f"  {error}", file=sys.stderr)

    title = prompt_value("Title", str(metadata.get("title") or ""))
    while not title:
        print("Title is required.", file=sys.stderr)
        title = prompt_value("Title", str(metadata.get("title") or ""))
    authors = prompt_authors(metadata.get("authors") or None)
    suggested_source = normalize_source(
        doi,
        str(metadata.get("source") or normalize_source(doi, "")),
    )
    source = normalize_source(doi, prompt_value("Archive/source (optional)", suggested_source))
    year = prompt_year(metadata.get("year"))
    members = load_members()
    profile_ids = resolve_profile_ids(authors, members)
    try:
        tags = parse_group_tags(args.tags) if args.tags is not None else prompt_group_tags()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    default_date = args.date or date.today()
    while True:
        raw_date = prompt_value("Date (YYYY-MM-DD)", default_date.isoformat())
        try:
            submitted_date = parse_date(raw_date)
            break
        except argparse.ArgumentTypeError as exc:
            print(str(exc), file=sys.stderr)

    data = load_submissions()
    if submission_exists(data, title, authors):
        print("This submitted publication is already in the data file.", file=sys.stderr)
        return 1
    if doi and any(str(item.get("doi", "")).casefold() == doi.casefold() for item in data["items"]):
        print("This DOI is already in the submitted-publications data file.", file=sys.stderr)
        return 1

    base_id = f"submitted-{submitted_date.isoformat()}-{slugify(title)}"
    existing_ids = {str(item.get("id", "")) for item in data["items"]}
    entry_id = base_id
    suffix = 2
    while entry_id in existing_ids:
        entry_id = f"{base_id}-{suffix}"
        suffix += 1

    entry = {
        "id": entry_id,
        "status": "submitted",
        "title": title,
        "authors": authors,
        "date": submitted_date.isoformat(),
        "profile_ids": profile_ids,
        "tags": tags,
    }
    if doi:
        entry["doi"] = doi
    if source:
        entry["source"] = source
    if year:
        entry["year"] = year

    print("\n=== Submitted publication ===")
    print(f"Title:   {title}")
    if doi:
        print(f"DOI:     {doi}")
    print(f"Authors: {'; '.join(authors)}")
    if source:
        print(f"Source:  {source}")
    if year:
        print(f"Year:    {year}")
    print(f"Date:    {submitted_date.isoformat()}")
    print(f"Tags:    {', '.join(tags) if tags else 'None'}")
    profile_names = [
        str(member["name"])
        for member in members
        if member["id"] in profile_ids
    ]
    print(f"Profiles: {'; '.join(profile_names) if profile_names else 'None'}")
    print("=============================\n")
    if input("Save this entry? [Y/n]: ").strip().lower() in {"n", "no"}:
        print("Cancelled; no changes written.")
        return 0

    data["items"].append(entry)
    write_submissions(data)
    print(f"Added submitted publication to {SUBMITTED_FILE}")
    print("The entry will appear on the profile pages of the listed authors.")
    print("Run 'make build && make deploy' to publish the changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
