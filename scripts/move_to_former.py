#!/usr/bin/env python3
"""Move an active group member to the Former Members list.

Usage:
    python3 scripts/move_to_former.py                # interactive: pick from a list
    python3 scripts/move_to_former.py jon-uranga      # move a specific member by id
    python3 scripts/move_to_former.py jon-uranga --yes   # skip the confirmation prompt

What it does:
    1. Finds content/people/<id>.md and reads its current `member_type`.
    2. Rewrites `member_type` to the matching "former_*" value
       (researcher -> former_researcher, postdoc -> former_postdoc,
       phd -> former_phd, technician -> former_technician,
       visitor -> former_visitor).
    3. Moves the member's id from data/member_order/<type>.yaml to
       data/member_order/former_<type>.yaml (creating the file if needed),
       so the member disappears from the active listings and appears at
       the end of the matching Former Members section.

This only touches the front matter of the member's own page; their bio,
photo and publications stay untouched. Run `make build` afterwards to
regenerate the site.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

from group_metadata import CONTENT_DIR, ROOT


PEOPLE_DIR = CONTENT_DIR / "people"
MEMBER_ORDER_DIR = ROOT / "data" / "member_order"

ACTIVE_TYPES = ["researcher", "postdoc", "phd", "technician", "visitor"]
MEMBER_TYPE_RE = re.compile(r'^(member_type:\s*)(["\']?)([a-zA-Z_]+)\2\s*$', re.MULTILINE)


def list_active_members() -> list[tuple[str, str, str]]:
    """Return (id, title, member_type) for every active (non-former) member."""
    members: list[tuple[str, str, str]] = []
    for path in sorted(PEOPLE_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        match = MEMBER_TYPE_RE.search(text)
        if not match:
            continue
        member_type = match.group(3)
        if member_type not in ACTIVE_TYPES:
            continue
        title_match = re.search(r'^title:\s*"([^"]*)"', text, re.MULTILINE)
        title = title_match.group(1) if title_match else path.stem
        members.append((path.stem, title, member_type))
    return members


def prompt_member_id() -> str:
    members = list_active_members()
    if not members:
        print("No active members found in content/people/.")
        sys.exit(1)

    print("Active members:")
    for index, (member_id, title, member_type) in enumerate(members, start=1):
        print(f"  {index}. {title}  ({member_type}, id: {member_id})")

    choice = input("Pick a number (or paste an id): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(members):
        return members[int(choice) - 1][0]
    return choice


def load_order_ids(path: Path) -> list[str]:
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    ids = data.get("ids") or []
    return [str(value) for value in ids]


def write_order_ids(path: Path, ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ids": ids}
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def move_member(member_id: str, assume_yes: bool) -> None:
    path = PEOPLE_DIR / f"{member_id}.md"
    if not path.is_file():
        print(f"Error: {path} does not exist.", file=sys.stderr)
        sys.exit(1)

    text = path.read_text(encoding="utf-8")
    match = MEMBER_TYPE_RE.search(text)
    if not match:
        print(f"Error: could not find a member_type field in {path}.", file=sys.stderr)
        sys.exit(1)

    current_type = match.group(3)
    if current_type.startswith("former_"):
        print(f"{member_id} is already a former member ({current_type}).")
        return
    if current_type not in ACTIVE_TYPES:
        print(f"Error: unknown member_type '{current_type}' in {path}.", file=sys.stderr)
        sys.exit(1)

    former_type = f"former_{current_type}"

    title_match = re.search(r'^title:\s*"([^"]*)"', text, re.MULTILINE)
    title = title_match.group(1) if title_match else member_id

    if not assume_yes:
        reply = input(f"Move '{title}' from {current_type} to {former_type}? [y/N]: ").strip().lower()
        if reply not in {"y", "yes"}:
            print("Cancelled.")
            return

    prefix, quote, _ = match.group(1), match.group(2), match.group(3)
    new_line = f"{prefix}{quote}{former_type}{quote}"
    new_text = text[: match.start()] + new_line + text[match.end() :]
    path.write_text(new_text, encoding="utf-8")

    active_order_path = MEMBER_ORDER_DIR / f"{current_type}.yaml"
    former_order_path = MEMBER_ORDER_DIR / f"{former_type}.yaml"

    active_ids = load_order_ids(active_order_path)
    if member_id in active_ids:
        active_ids = [value for value in active_ids if value != member_id]
        write_order_ids(active_order_path, active_ids)

    former_ids = load_order_ids(former_order_path)
    if member_id not in former_ids:
        former_ids.append(member_id)
    write_order_ids(former_order_path, former_ids)

    print(f"Moved '{title}' ({member_id}) to Former Members as {former_type}.")
    print("Run 'make build' (or 'make validate') to regenerate the site.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Move an active member to Former Members.")
    parser.add_argument("id", nargs="?", help="Member id (filename without .md in content/people/)")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args()

    member_id = args.id or prompt_member_id()
    if not member_id:
        print("No member selected.", file=sys.stderr)
        sys.exit(1)

    move_member(member_id, args.yes)


if __name__ == "__main__":
    main()
