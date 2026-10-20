#!/usr/bin/env python3
"""Generate per-research-line pages from content/<group>/_index.md

Prototype behavior:
- Reads research_lines from content/<group>/_index.md front matter
- For each research line creates content/<group>/research/<slug>/_index.md
- Optionally fetches Crossref metadata for DOIs listed under 'dois:' in each research_line
- Downloads any image links advertised by Crossref if available to static/images/publications/toc/

Usage:
  python3 scripts/generate_research_pages.py --group matcat
  python3 scripts/generate_research_pages.py --group matcat --dry-run

This is a prototype: robust error handling, rate limiting and retries are minimal.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
import time
import ssl
import html
import re as _re


ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = ROOT / "content"
STATIC_DIR = ROOT / "static"
NAV_DIR = ROOT / "data" / "navigation"
USER_AGENT = "kt-hugoblox-prototype/1.0 (generate_research_pages prototype)"


def load_front_matter(md_path: Path) -> tuple[dict, str]:
    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    _, fm_raw, body = parts
    data = yaml.safe_load(fm_raw) or {}
    return data, body.lstrip("\n")


def slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def safe_filename(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_.-]", "-", s)
    return s


def interactive_arguments() -> list[str]:
    """Collect group and research-line choices when no CLI arguments are given."""
    groups = []
    for subdir in sorted(CONTENT_DIR.iterdir()):
        if not subdir.is_dir():
            continue
        index = subdir / "_index.md"
        if not index.exists():
            continue
        fm, _ = load_front_matter(index)
        lines = fm.get("research_lines") or []
        if isinstance(lines, list) and lines:
            groups.append((subdir.name, lines))

    if not groups:
        raise ValueError("No groups with research lines were found.")

    print("Research groups:")
    for number, (group, _) in enumerate(groups, start=1):
        print(f"  {number}. {group}")
    while True:
        selected = input("Group number: ").strip()
        if selected.isdigit() and 1 <= int(selected) <= len(groups):
            break
        print(f"Enter a number from 1 to {len(groups)}.", file=sys.stderr)

    group, lines = groups[int(selected) - 1]
    print("\nResearch lines:")
    print("  0. All research lines")
    for number, line in enumerate(lines, start=1):
        title = line.get("title") or line.get("eyebrow") or line.get("slug", "")
        print(f"  {number}. {title}")
    while True:
        selected_line = input("Research line number [0=all]: ").strip() or "0"
        if selected_line.isdigit() and 0 <= int(selected_line) <= len(lines):
            break
        print(f"Enter a number from 0 to {len(lines)}.", file=sys.stderr)

    arguments = ["--group", group, "--force"]
    if int(selected_line) != 0:
        arguments.extend(["--slug", str(lines[int(selected_line) - 1].get("slug", ""))])
    return arguments


def fetch_crossref_record(doi: str) -> dict | None:
    doi = doi.strip()
    if not doi:
        return None
    api = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}"
    req = urllib.request.Request(api, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            import json

            payload = resp.read()
            obj = json.loads(payload)
            return obj.get("message")
    except Exception as exc:
        print(f"Warning: failed to fetch Crossref for {doi}: {exc}")
        return None


def download_image(url: str, out_path: Path) -> bool:
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        # allow HTTPS redirects and possibly unverified certs in fragile environments
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            data = resp.read()
            out_path.write_bytes(data)
        # be polite
        time.sleep(0.5)
        return True
    except Exception as exc:
        print(f"Warning: failed to download image {url}: {exc}")
        return False


def resolve_doi_url(doi: str) -> str | None:
    """Resolve https://doi.org/{doi} and return final landing URL or None."""
    try:
        url = f"https://doi.org/{urllib.parse.quote(doi, safe='') }"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            final = resp.geturl()
            return final
    except Exception as exc:
        print(f"Warning: failed to resolve DOI {doi}: {exc}")
        return None


def find_image_on_page(url: str) -> str | None:
    """Fetch HTML and attempt to find a suitable image URL (og:image, twitter:image, image_src, heuristic img)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            raw = resp.read()
            try:
                text = raw.decode('utf-8', errors='replace')
            except Exception:
                text = raw.decode('latin-1', errors='replace')
    except Exception as exc:
        print(f"Warning: failed to fetch landing page {url}: {exc}")
        return None

    # Prefer meta property og:image
    m = _re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', text, _re.I)
    if m:
        return html.unescape(m.group(1))
    m = _re.search(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']', text, _re.I)
    if m:
        return html.unescape(m.group(1))
    m = _re.search(r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)["\']', text, _re.I)
    if m:
        return html.unescape(m.group(1))

    # Look for images with alt/class hinting 'graphical abstract' or 'toc'
    imgs = _re.findall(r'<img[^>]+>', text, _re.I)
    for imgtag in imgs:
        if _re.search(r'(graphical|abstract|toc|toc-image|ga|graphical-abstract)', imgtag, _re.I):
            msrc = _re.search(r'src=["\']([^"\']+)["\']', imgtag, _re.I)
            if msrc:
                return html.unescape(msrc.group(1))
    # last-resort: first large image (heuristic by file extension)
    for imgtag in imgs:
        msrc = _re.search(r'src=["\']([^"\']+\.(?:png|jpg|jpeg|svg))["\']', imgtag, _re.I)
        if msrc:
            return html.unescape(msrc.group(1))
    return None


def build_publication_entry_from_crossref(message: dict, group: str, slug: str) -> dict:
    # Extract basic fields (robustness modest for prototype)
    def first_title(msg):
        titles = msg.get("title") or []
        if not titles:
            return ""
        # Crossref titles may carry JATS markup (e.g. <scp>ii</scp>) and embedded
        # newlines/indentation; strip tags and collapse whitespace.
        title = re.sub(r"<scp>(.*?)</scp>", lambda m: m.group(1).strip().upper(), str(titles[0]), flags=re.S)
        title = re.sub(r"<[^>]+>", "", title)
        title = re.sub(r"\s+", " ", title).strip()
        return re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", title))

    def extract_authors(msg):
        out = []
        for a in (msg.get("author") or []):
            given = a.get("given") or ""
            family = a.get("family") or ""
            name = (given + " " + family).strip()
            if name:
                out.append(name)
        return out

    doi = message.get("DOI") or ""
    title = first_title(message)
    authors = extract_authors(message)
    year = None
    for key in ("published-print", "published-online", "issued", "created"):
        val = message.get(key) or {}
        parts = val.get("date-parts") or []
        if parts and parts[0]:
            year = int(parts[0][0])
            break
    journal = (message.get("container-title") or [""])[0]
    volume = message.get("volume") or ""
    issue = message.get("issue") or ""
    pages = message.get("page") or message.get("article-number") or ""

    pub = {
        "doi": doi,
        "title": title,
        "authors": authors,
        "year": year,
        "journal": journal,
        "volume": volume,
        "issue": issue,
        "pages": pages,
    }

    # Try to find an image link in Crossref 'link' if present
    links = message.get("link") or []
    toc_image = None
    for link in links:
        content_type = (link.get("content-type") or "").lower()
        url = link.get("URL") or link.get("url") or link.get("URL")
        if not url:
            continue
        if content_type.startswith("image"):
            # download
            ext = os.path.splitext(urllib.parse.urlparse(url).path)[1] or ".png"
            fname = safe_filename(f"{slug}-{doi}") + ext
            out_path = STATIC_DIR / "images" / "publications" / "toc" / fname
            if download_image(url, out_path):
                # Expose the path relative to the site root (static/ maps to site root)
                try:
                    rel = out_path.relative_to(STATIC_DIR)
                except Exception:
                    rel = out_path.relative_to(ROOT)
                toc_image = "/" + str(rel).replace(os.sep, "/")
                break
    if toc_image:
        pub["toc_image"] = toc_image
    else:
        # Fallback: resolve DOI to landing page and look for og:image / twitter:image / heuristics
        landing = message.get("URL") or resolve_doi_url(doi)
        if landing:
            print(f"    No Crossref image; trying landing page {landing}")
            found = find_image_on_page(landing)
            if found:
                # Normalize found URL
                if found.startswith("//"):
                    found = "https:" + found
                if found.startswith("/"):
                    parsed = urllib.parse.urlparse(landing)
                    found = urllib.parse.urljoin(f"{parsed.scheme}://{parsed.netloc}", found)
                ext = os.path.splitext(urllib.parse.urlparse(found).path)[1] or ".png"
                fname = safe_filename(f"{slug}-{doi}") + ext
                out_path = STATIC_DIR / "images" / "publications" / "toc" / fname
                if download_image(found, out_path):
                    try:
                        rel = out_path.relative_to(STATIC_DIR)
                    except Exception:
                        rel = out_path.relative_to(ROOT)
                    pub["toc_image"] = "/" + str(rel).replace(os.sep, "/")
                    pub["toc_from"] = "landing_page"
                    pub["toc_landing"] = landing
    return pub


def make_card_excerpt(text: str | None, nwords: int = 5) -> str:
    if not text:
        return ""
    # remove simple HTML tags and decode entities
    t = re.sub(r'<[^>]+>', '', str(text))
    t = html.unescape(t)
    # collapse whitespace
    t = re.sub(r'\s+', ' ', t).strip()
    # drop placeholder ellipses like "Polymer research ...." so they don't pollute the excerpt
    t = re.sub(r'\.{3,}\s*$', '', t).strip()
    t = re.sub(r'\.{2,}\s*$', '', t).strip()
    parts = t.split(' ')
    if len(parts) <= nwords:
        return t
    return ' '.join(parts[:nwords])


def write_group_research_index(group: str, fm: dict, dry_run: bool = False, force: bool = False) -> Path:
    """Ensure content/<group>/research/_index.md exists, creating a simple index that lists research lines.
    The content matches the matcat example using the research_index_list shortcode.
    """
    out_dir = CONTENT_DIR / group / "research"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "_index.md"

    # Try to inherit header/branding from group's _index.md front matter (fm)
    header = {}
    if fm:
        # copy common header keys if present
        for k in ("variant", "menu", "accent", "brand_name", "brand_note", "brand_url"):
            if k in fm.get("header", {}):
                header[k] = fm.get("header").get(k)
    # Ensure subgroup header defaults
    header.setdefault("variant", "subgroup")
    header.setdefault("menu", group)
    header.setdefault("accent", fm.get("research_group_card", {}).get("key", fm.get("header", {}).get("accent", group)))
    header.setdefault("brand_name", fm.get("research_group_card", {}).get("label", group))
    header.setdefault("brand_url", f"/{group}/")

    front = {
        "title": "Research",
        "hide_page_hero": True,
        "content_frame": False,
        "hide_child_section": True,
        "weight": 2,
        "header": header,
    }
    # Preserve redirect aliases on the existing index (e.g. URLs of retired
    # research lines that now point to the research index).
    if out_file.exists():
        try:
            existing_fm, _ = load_front_matter(out_file)
            if existing_fm.get("aliases"):
                front["aliases"] = list(existing_fm["aliases"])
        except Exception as exc:
            print(f"Warning: could not read existing aliases from {out_file}: {exc}")
    body = "{{< research_index_list >}}\n"

    if dry_run:
        print(f"Dry-run: would ensure research index {out_file}")
        return out_file

    if out_file.exists() and not force:
        print(f"Research index exists for {group}, skipping (use --force to overwrite): {out_file}")
        return out_file

    out_file.write_text("---\n" + yaml.safe_dump(front, sort_keys=False, allow_unicode=True) + "---\n\n" + body, encoding="utf-8")
    print(f"Wrote research index {out_file}")
    return out_file


def update_navigation_for_resources(group: str, dry_run: bool = False) -> Path | None:
    """Add a Resources menu item to data/navigation/<group>.yaml if it doesn't exist."""
    nav_file = NAV_DIR / f"{group}.yaml"
    if not nav_file.exists():
        return None

    nav = yaml.safe_load(nav_file.read_text(encoding="utf-8")) or {}
    items = nav.get("items", [])
    if any(item.get("name") == "Resources" for item in items):
        return nav_file

    # Insert Resources right before Contact if present, otherwise append
    insert_idx = len(items)
    for i, item in enumerate(items):
        if item.get("name") == "Contact":
            insert_idx = i
            break
    items.insert(insert_idx, {"name": "Resources", "url": f"/{group}/resources/"})
    nav["items"] = items

    if dry_run:
        print(f"Dry-run: would update navigation {nav_file}")
        return nav_file

    nav_file.write_text(yaml.safe_dump(nav, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Updated navigation {nav_file}")
    return nav_file


def write_contact_page(group: str, contact: dict, fm: dict, dry_run: bool = False, force: bool = False) -> Path | None:
    """Ensure content/<group>/contact/_index.md exists from the contact section in the group's front matter."""
    people = contact.get("people") if isinstance(contact, dict) else None
    if not people:
        return None

    out_dir = CONTENT_DIR / group / "contact"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "_index.md"

    # Inherit header/branding from group's _index.md front matter
    header = {}
    if fm:
        for k in ("variant", "menu", "accent", "brand_name", "brand_note", "brand_url"):
            if k in fm.get("header", {}):
                header[k] = fm.get("header").get(k)
    header.setdefault("variant", "subgroup")
    header.setdefault("menu", group)
    header.setdefault("accent", fm.get("research_group_card", {}).get("key", fm.get("header", {}).get("accent", group)))
    header.setdefault("brand_name", fm.get("research_group_card", {}).get("label", group))
    header.setdefault("brand_url", f"/{group}/")

    front = {
        "title": contact.get("title", "Contact"),
        "hide_page_hero": True,
        "content_frame": False,
        "hide_child_section": True,
        "weight": 4,
        "header": header,
        "contact": contact,
    }
    body = "{{< contact_list >}}\n"

    if dry_run:
        print(f"Dry-run: would ensure contact page {out_file}")
        return out_file

    if out_file.exists() and not force:
        print(f"Contact page exists for {group}, skipping (use --force to overwrite): {out_file}")
        return out_file

    out_file.write_text("---\n" + yaml.safe_dump(front, sort_keys=False, allow_unicode=True) + "---\n\n" + body, encoding="utf-8")
    print(f"Wrote contact page {out_file}")
    return out_file


def write_resources_page(group: str, resources: dict, fm: dict, dry_run: bool = False, force: bool = False) -> Path | None:
    """Ensure content/<group>/resources/_index.md exists from the resources section in the group's front matter."""
    items = resources.get("items") if isinstance(resources, dict) else None
    if not items:
        return None

    out_dir = CONTENT_DIR / group / "resources"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "_index.md"

    # Inherit header/branding from group's _index.md front matter
    header = {}
    if fm:
        for k in ("variant", "menu", "accent", "brand_name", "brand_note", "brand_url"):
            if k in fm.get("header", {}):
                header[k] = fm.get("header").get(k)
    header.setdefault("variant", "subgroup")
    header.setdefault("menu", group)
    header.setdefault("accent", fm.get("research_group_card", {}).get("key", fm.get("header", {}).get("accent", group)))
    header.setdefault("brand_name", fm.get("research_group_card", {}).get("label", group))
    header.setdefault("brand_url", f"/{group}/")

    front = {
        "title": resources.get("title", "Resources"),
        "hide_page_hero": True,
        "content_frame": False,
        "hide_child_section": True,
        "weight": 3,
        "header": header,
        "resources": resources,
    }
    body = "{{< resources_list >}}\n"

    if dry_run:
        print(f"Dry-run: would ensure resources page {out_file}")
        return out_file

    if out_file.exists() and not force:
        print(f"Resources page exists for {group}, skipping (use --force to overwrite): {out_file}")
        return out_file

    out_file.write_text("---\n" + yaml.safe_dump(front, sort_keys=False, allow_unicode=True) + "---\n\n" + body, encoding="utf-8")
    print(f"Wrote resources page {out_file}")
    return out_file


def write_research_page(group: str, rl: dict, publications: list[dict], dry_run: bool = False, force: bool = False) -> Path:
    slug = rl.get("slug") or slugify(rl.get("title", "line"))
    out_dir = CONTENT_DIR / group / "research" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "_index.md"

    fm = {
        "title": rl.get("title") or rl.get("eyebrow") or slug,
        "eyebrow": rl.get("eyebrow"),
        "slug": slug,
        "weight": rl.get("weight", 1),
        # start with the newly generated publications list
        "publications": publications,
        "hide_page_hero": True,
        "content_frame": False,
    }
    # Hugo redirect aliases (e.g. old URLs after a slug rename) are declared on the
    # research line in the group's _index.md so they survive regeneration.
    if rl.get("aliases"):
        fm["aliases"] = list(rl["aliases"])

    # If a page already exists, preserve any existing toc_image/toc_from/toc_landing
    # for matching publications (match by DOI). The generated list is authoritative:
    # removing a DOI from the research line must also remove it from the page.
    if out_file.exists():
        try:
            existing_fm, _ = load_front_matter(out_file)
            existing_pubs_map = {}
            existing_pubs_list = existing_fm.get("publications", []) or []
            for ep in existing_pubs_list:
                if isinstance(ep, dict) and ep.get("doi"):
                    existing_pubs_map[ep.get("doi").lower()] = ep

            # Merge preserved fields into the new publications list
            new_pubs = fm.get("publications", []) or []
            new_dois = set()
            for idx, newp in enumerate(new_pubs):
                if not isinstance(newp, dict):
                    continue
                doi = (newp.get("doi") or "").strip()
                if doi:
                    doi_lower = doi.lower()
                    new_dois.add(doi_lower)
                    old = existing_pubs_map.get(doi_lower)
                    if old:
                        # Preserve toc_image/toc_from/toc_landing if new entry lacks them
                        for k in ("toc_image", "toc_from", "toc_landing"):
                            if (not newp.get(k)) and old.get(k):
                                newp[k] = old.get(k)
                        new_pubs[idx] = newp

            fm["publications"] = new_pubs
        except Exception as exc:
            print(f"Warning: could not merge existing front matter from {out_file}: {exc}")
    header_text = rl.get("summary") or rl.get("header_text") or rl.get("intro") or ""

    # Build a visible body: include the summary/introduction and render publications via shortcode.
    # Do NOT include an explicit H1 title or a duplicate 'Selected publications' heading here —
    # the site template and the shortcode already render those headings to avoid duplication.
    body_lines: list[str] = []
    if header_text:
        body_lines.append(header_text)
        body_lines.append("")

    # Insert the research_line_publications shortcode (the shortcode renders its own heading)
    body_lines.append("{{< research_line_publications >}}")
    body_lines.append("")

    body = "\n".join(body_lines) + "\n"

    front = "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n\n"

    if dry_run:
        print(f"Dry-run: would write {out_file} with {len(publications)} publications")
        return out_file

    if out_file.exists() and not force:
        print(f"Skipping existing file {out_file} (use --force to overwrite)")
        return out_file

    out_file.write_text(front + body, encoding="utf-8")
    print(f"Wrote {out_file}")
    return out_file


def process_group(group: str, args) -> int:
    md = CONTENT_DIR / group / "_index.md"
    if not md.exists():
        print(f"Group index not found: {md}")
        return 2

    fm, body = load_front_matter(md)
    lines = fm.get("research_lines") or []
    if args.slug:
        lines = [l for l in lines if l.get("slug") == args.slug]
    if not lines:
        print("No research_lines found in front matter; nothing to do.")
        return 0

    # Optionally compute and attach short excerpts and card tone back into the group's front matter
    excerpt_words = args.excerpt_words
    modified = False
    for idx, rl in enumerate(lines):
        slug = rl.get("slug") or slugify(rl.get("title", "line"))
        # ensure card_excerpt (short, 4-5 words) and card_tone (group key) exist;
        # keep a hand-written card_excerpt if one is already set
        summary = rl.get("summary") or rl.get("intro") or ""
        short = make_card_excerpt(summary, nwords=excerpt_words)
        if not rl.get("card_excerpt"):
            rl["card_excerpt"] = short
            modified = True
        if rl.get("card_tone") != group:
            rl["card_tone"] = group
            modified = True

        print(f"Processing {group} -> {slug}")
        dois = rl.get("dois") or []
        pubs = []
        if dois:
            for doi in dois:
                doi_norm = doi.strip()
                print(f"  Fetching {doi_norm} ...")
                msg = fetch_crossref_record(doi_norm)
                if not msg:
                    print(f"    No metadata for {doi_norm}")
                    continue
                pub = build_publication_entry_from_crossref(msg, group, slug)
                pubs.append(pub)
        else:
            print("  No DOIs for this research line; creating page without publications")

        write_research_page(group, rl, pubs, dry_run=args.dry_run, force=args.force)

    # Ensure the group's research index page exists (like MatCat's research index)
    try:
        write_group_research_index(group, fm, dry_run=args.dry_run, force=args.force)
    except Exception as exc:
        print(f"Warning: failed to write group research index for {group}: {exc}")

    # Ensure the group's contact page exists if a contact section is defined
    contact = fm.get("contact")
    if contact:
        try:
            write_contact_page(group, contact, fm, dry_run=args.dry_run, force=args.force)
        except Exception as exc:
            print(f"Warning: failed to write contact page for {group}: {exc}")

    # Ensure the group's resources page exists if a resources section is defined
    resources = fm.get("resources")
    if resources:
        try:
            write_resources_page(group, resources, fm, dry_run=args.dry_run, force=args.force)
        except Exception as exc:
            print(f"Warning: failed to write resources page for {group}: {exc}")
        try:
            update_navigation_for_resources(group, dry_run=args.dry_run)
        except Exception as exc:
            print(f"Warning: failed to update navigation for {group}: {exc}")

    # If requested, write back the modified research_lines into the group's _index.md
    if modified:
        if args.update_index:
            print(f"Updating {md} with card_excerpt and card_tone fields...")
            fm["research_lines"] = lines
            new_front = "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n\n"
            # Preserve existing body
            body_text = body or ""
            md.write_text(new_front + body_text, encoding='utf-8')
            print(f"Wrote updated group index {md}")
        else:
            print("Note: extracted card_excerpt/card_tone values (not written). Run with --update-index to persist these changes.")

    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", "-g", help="group to process (e.g. matcat)")
    ap.add_argument("--all-groups", action="store_true", help="Run for every subdirectory of content/ that has a _index.md with research_lines or resources")
    ap.add_argument("--slug", "-s", help="specific research line slug to process")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--update-index", action="store_true", help="Write back modified research_lines to the group's _index.md (add card_excerpt and card_tone)")
    ap.add_argument("--excerpt-words", type=int, default=4, help="Number of words to keep for grid card excerpts (default: 4)")
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if not raw_args:
        try:
            raw_args = interactive_arguments()
        except (OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    args = ap.parse_args(raw_args)

    if not args.group and not args.all_groups:
        ap.error("Specify --group/-g or --all-groups")

    groups = []
    if args.all_groups:
        for subdir in sorted(CONTENT_DIR.iterdir()):
            md = subdir / "_index.md"
            if subdir.is_dir() and md.exists():
                fm, _ = load_front_matter(md)
                if fm.get("research_lines") or fm.get("resources"):
                    groups.append(subdir.name)
    else:
        groups = [args.group]

    exit_code = 0
    for group in groups:
        code = process_group(group, args)
        if code != 0:
            exit_code = code
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
