#!/usr/bin/env python3
"""Create a standard internal research-group section.

Usage:
    python3 scripts/add_group.py
    python3 scripts/add_group.py --slug new-kt --label New-KT --title "New-KT Group"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

from group_metadata import CONTENT_DIR, ROOT, load_groups


NAVIGATION_DIR = ROOT / "data" / "navigation"
GROUP_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def prompt(label: str, initial: str = "") -> str:
    suffix = f" [{initial}]" if initial else ""
    return input(f"{label}{suffix}: ").strip() or initial


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def group_index(slug: str, label: str, title: str, logo: str, summary: str) -> str:
    metadata = {
        "title": title,
        "layout": "subgroup",
        "hide_hero": True,
        "home_title": f"Welcome to the {title}",
        "weight": 99,
        "cascade": {
            "header": {
                "variant": "subgroup",
                "menu": slug,
                "accent": "primary",
                "brand_name": title,
                "brand_note": "EHU & DIPC",
                "brand_url": f"/{slug}/",
            }
        },
        "research_group_card": {
            "key": slug,
            "label": label,
            "logo": logo,
            "logo_class": "group-logo--wide",
            "summary": summary,
        },
        "research_intro": False,
        "research_lines": [],
        "contact": {"people": []},
    }
    return f"---\n{yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)}---\n\nAdd the group introduction here.\n"


def group_navigation(slug: str) -> str:
    payload = {
        "items": [
            {"name": "Home", "url": f"/{slug}/"},
            {"name": "Members", "url": f"/{slug}/members/"},
            {"name": "Research", "url": f"/{slug}/research/"},
            {"name": "Publications", "url": f"/{slug}/publications/"},
            {"name": "Contact", "url": f"/{slug}/contact/"},
            {"name": "KT-Home", "url": "/"},
        ]
    }
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", help="Lowercase group key, for example new-kt")
    parser.add_argument("--label", help="Public label, for example New-KT")
    parser.add_argument("--title", help="Full title, for example New-KT Group")
    parser.add_argument("--logo", help="Logo path below static/, for example /images/groups/new-kt.png")
    parser.add_argument("--summary", help="Short group summary for the Research Groups directory")
    parser.add_argument("--dry-run", action="store_true", help="Show files that would be created")
    args = parser.parse_args(argv)

    slug = (args.slug or prompt("Group key")).strip().lower()
    if not GROUP_SLUG.fullmatch(slug):
        print("Group key must use lowercase letters, numbers and hyphens only.", file=sys.stderr)
        return 1
    if slug in load_groups() or (CONTENT_DIR / slug).exists():
        print(f"Group '{slug}' already exists.", file=sys.stderr)
        return 1

    label_default = slug.upper()
    label = (args.label or (label_default if args.dry_run else prompt("Public label", label_default))).strip()
    title_default = f"{label} Group"
    title = (args.title or (title_default if args.dry_run else prompt("Full title", title_default))).strip()
    logo_default = f"/images/groups/{slug}.png"
    logo = (args.logo or (logo_default if args.dry_run else prompt("Logo path", logo_default))).strip()
    summary_default = "Research group description."
    summary = (
        args.summary
        or (summary_default if args.dry_run else prompt("Short summary", summary_default))
    ).strip()
    if not all((label, title, logo, summary)):
        print("Label, title, logo path and summary are required.", file=sys.stderr)
        return 1

    files = {
        CONTENT_DIR / slug / "_index.md": group_index(slug, label, title, logo, summary),
        CONTENT_DIR / slug / "members.md": (
            "---\ntitle: Members\nhide_hero: true\ncontent_frame: false\n---\n\n"
            f'{{{{< member_directory group="{slug}" >}}}}\n'
        ),
        CONTENT_DIR / slug / "publications.md": (
            "---\ntitle: Publications\nhide_hero: true\ncontent_frame: false\n---\n\n"
            f'{{{{< publication_directory group="{slug}" >}}}}\n'
        ),
        CONTENT_DIR / slug / "research" / "_index.md": (
            "---\ntitle: Research\nhide_hero: true\ncontent_frame: false\n---\n\n"
            "{{< research_index_list >}}\n"
        ),
        CONTENT_DIR / slug / "contact" / "_index.md": (
            "---\ntitle: Contact\nhide_hero: true\ncontent_frame: false\nhide_child_section: true\n---\n\n"
            "{{< contact_list >}}\n"
        ),
        NAVIGATION_DIR / f"{slug}.yaml": group_navigation(slug),
    }

    print("Files to create:")
    for path in files:
        print(f"- {path.relative_to(ROOT)}")
    print(f"- static{logo}")
    if args.dry_run:
        return 0

    for path, content in files.items():
        write_file(path, content)
    print(f"Created group '{label}' ({slug}). Add the logo at static{logo}, then run make validate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
