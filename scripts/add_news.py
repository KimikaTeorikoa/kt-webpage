#!/usr/bin/env python3
"""Interactively add a dated news item, its photos, and a gallery event."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import date
from pathlib import Path

import yaml

from import_gallery import DATA_PATH as GALLERY_DATA_PATH
from import_gallery import IMAGE_DIR as GALLERY_IMAGE_DIR
from import_gallery import slugify, sort_events, write_yaml


ROOT = Path(__file__).resolve().parents[1]
NEWS_DIR = ROOT / "content" / "news"
NEWS_IMAGE_DIR = ROOT / "static" / "images" / "news"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def prompt_date() -> date:
    today = date.today()
    while True:
        value = input(f"Date (DD.MM.YYYY) [{today.strftime('%d.%m.%Y')}]: ").strip()
        if not value:
            return today
        if not re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", value):
            print("Enter a valid date in DD.MM.YYYY format.")
            continue
        try:
            return date.fromisoformat(f"{value[6:10]}-{value[3:5]}-{value[0:2]}")
        except ValueError:
            print("Enter a valid date in DD.MM.YYYY format.")


def prompt_required(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print(f"{label} cannot be empty.")


def prompt_image(label: str) -> Path:
    while True:
        value = input(f"{label} (image path): ").strip().strip("\"'")
        path = Path(value).expanduser()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            return path.resolve()
        print(f"Image not found or unsupported format: {path}")


def prompt_optional_image(label: str) -> Path | None:
    while True:
        answer = input(f"Does this news item have a {label.lower()}? [y/N]: ").strip().lower()
        if answer in {"", "n", "no"}:
            return None
        if answer in {"y", "yes"}:
            return prompt_image(label)
        print("Enter yes or no; press Enter for no.")


def prompt_photos() -> list[Path]:
    while True:
        answer = input("Does the article have additional photos? [y/N]: ").strip().lower()
        if answer in {"", "n", "no"}:
            return []
        if answer in {"y", "yes"}:
            break
        print("Enter yes or no; press Enter for no.")

    while True:
        value = input("Number of article photos: ").strip()
        try:
            count = int(value)
        except ValueError:
            print("Enter a whole number greater than zero.")
            continue
        if count < 1:
            print("Enter a whole number greater than zero.")
            continue
        break

    photos: list[Path] = []
    for index in range(1, count + 1):
        photos.append(prompt_image(f"Article photo {index} of {count}"))
    return photos


def prompt_include_in_gallery() -> bool:
    while True:
        value = input("Also add the banner and article photos to the photo gallery? [y/N]: ").strip().lower()
        if value in {"", "n", "no"}:
            return False
        if value in {"y", "yes"}:
            return True
        print("Enter yes or no; press Enter for no.")


def prompt_body() -> str:
    print("Article text in Markdown; finish by entering a single dot on its own line:")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == ".":
            break
        lines.append(line)
    body = "\n".join(lines).strip()
    if not body:
        raise ValueError("Article text cannot be empty.")
    return body


def summary_from_body(body: str) -> str:
    paragraph = next((line.strip() for line in body.splitlines() if line.strip()), "")
    paragraph = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", paragraph)
    paragraph = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", paragraph)
    paragraph = re.sub(r"[*_`#>]", "", paragraph)
    paragraph = re.sub(r"\s+", " ", paragraph).strip()
    if len(paragraph) > 220:
        paragraph = paragraph[:217].rsplit(" ", 1)[0] + "..."
    return paragraph


def unique_slug(value: str, suffix: str, existing: set[str]) -> str:
    base_slug = slugify(value)
    candidate = f"{suffix}-{base_slug}"
    if candidate not in existing:
        return candidate
    counter = 2
    while f"{candidate}-{counter}" in existing:
        counter += 1
    return f"{candidate}-{counter}"


def create_news_item(
    news_date: date,
    title: str,
    banner: Path | None,
    photos: list[Path],
    body: str,
    include_in_gallery: bool = False,
    dry_run: bool = False,
) -> tuple[Path, str, int]:
    date_slug = news_date.isoformat()
    existing_news = {
        path.name for path in NEWS_DIR.iterdir() if path.is_dir()
    } if NEWS_DIR.exists() else set()
    news_slug = unique_slug(title, date_slug, existing_news)
    article_dir = NEWS_DIR / news_slug
    banner_dir = NEWS_IMAGE_DIR / news_slug

    gallery_payload = yaml.safe_load(GALLERY_DATA_PATH.read_text(encoding="utf-8")) or {}
    events = gallery_payload.get("items", [])
    if not isinstance(events, list):
        raise ValueError(f"Expected a list at items in {GALLERY_DATA_PATH}")

    event_title = f"{title} ({news_date.strftime('%d.%m.%Y')})"
    event_slug = slugify(event_title)
    if include_in_gallery and banner is None and not photos:
        raise ValueError("Cannot create a gallery event without photos.")
    if include_in_gallery and any(str(event.get("slug", "")) == event_slug for event in events):
        raise FileExistsError(f"A gallery event already exists for {event_title}")

    banner_name = f"banner{banner.suffix.lower()}" if banner else None
    banner_url = f"/images/news/{news_slug}/{banner_name}" if banner_name else None
    gallery_images: list[dict[str, str]] = []
    gallery_urls: list[str] = []
    for index, photo in enumerate(photos, start=1):
        photo_name = f"{index:02d}-{slugify(photo.stem)}{photo.suffix.lower()}"
        article_image_url = f"/images/news/{news_slug}/{photo_name}"
        gallery_urls.append(article_image_url)
        gallery_images.append({"src": article_image_url, "alt": title})

    summary = summary_from_body(body)
    front_matter: dict[str, object] = {
        "title": title,
        "date": date_slug,
        "summary": summary,
        "gallery_images": gallery_urls,
    }
    if banner_url:
        front_matter["banner"] = banner_url
        front_matter["banner_scale"] = 100
    article_content = (
        "---\n"
        + yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=True)
        + "---\n\n"
        + body.strip()
        + "\n"
    )
    gallery_event_images: list[dict[str, str]] = []
    if include_in_gallery:
        if banner:
            gallery_event_images.append(
                {
                    "src": f"/images/gallery/{event_slug}/00-banner{banner.suffix.lower()}",
                    "alt": title,
                }
            )
        for index, photo in enumerate(photos, start=1):
            photo_name = f"{index:02d}-{slugify(photo.stem)}{photo.suffix.lower()}"
            gallery_event_images.append(
                {"src": f"/images/gallery/{event_slug}/{photo_name}", "alt": title}
            )
    event = {"title": event_title, "slug": event_slug, "images": gallery_event_images}

    if dry_run:
        return article_dir / "index.md", event_title, len(gallery_event_images)
    if (
        article_dir.exists()
        or (banner_dir.exists() and (banner is not None or photos))
        or (include_in_gallery and (GALLERY_IMAGE_DIR / event_slug).exists())
    ):
        raise FileExistsError(f"Files already exist for news item: {title}")

    created_paths: list[Path] = []
    created_directories: list[Path] = []
    old_gallery_yaml = GALLERY_DATA_PATH.read_text(encoding="utf-8")
    try:
        if banner or photos:
            banner_dir.mkdir(parents=True)
            created_directories.append(banner_dir)
            if banner and banner_name:
                banner_target = banner_dir / banner_name
                shutil.copy2(banner, banner_target)
                created_paths.append(banner_target)

            for photo, image in zip(photos, gallery_images):
                target = banner_dir / Path(image["src"]).name
                shutil.copy2(photo, target)
                created_paths.append(target)

        gallery_dir = GALLERY_IMAGE_DIR / event_slug
        if include_in_gallery:
            gallery_dir.mkdir(parents=True)
            created_directories.append(gallery_dir)
            gallery_photo_images = gallery_event_images
            if banner and gallery_photo_images:
                banner_gallery_target = gallery_dir / Path(gallery_photo_images[0]["src"]).name
                shutil.copy2(banner, banner_gallery_target)
                created_paths.append(banner_gallery_target)
                gallery_photo_images = gallery_photo_images[1:]
            for photo, image in zip(photos, gallery_photo_images):
                target = gallery_dir / Path(image["src"]).name
                shutil.copy2(photo, target)
                created_paths.append(target)

        article_dir.mkdir(parents=True)
        created_directories.append(article_dir)
        article_path = article_dir / "index.md"
        article_path.write_text(article_content, encoding="utf-8")
        created_paths.append(article_path)

        if include_in_gallery:
            events.append(event)
            write_yaml(sort_events(events))
        return article_path, event_title, len(gallery_event_images)
    except Exception:
        GALLERY_DATA_PATH.write_text(old_gallery_yaml, encoding="utf-8")
        for path in reversed(created_paths):
            path.unlink(missing_ok=True)
        for directory in reversed(created_directories):
            try:
                directory.rmdir()
            except (FileNotFoundError, OSError):
                pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="walk through the questions without copying images or writing files",
    )
    args = parser.parse_args()
    news_date = prompt_date()
    title = prompt_required("News title")
    banner = prompt_optional_image("Banner photo")
    photos = prompt_photos()
    has_photos = banner is not None or bool(photos)
    include_in_gallery = prompt_include_in_gallery() if has_photos else False
    body = prompt_body()

    article_path, event_title, photo_count = create_news_item(
        news_date,
        title,
        banner,
        photos,
        body,
        include_in_gallery=include_in_gallery,
        dry_run=args.dry_run,
    )
    prefix = "Would create" if args.dry_run else "Created"
    print(f"{prefix} news item: {article_path}")
    if photo_count:
        print(f"{prefix} gallery event: {event_title} ({photo_count} image(s))")
    elif has_photos and not include_in_gallery:
        print("Banner and article photos will stay with the news item and won't be added to the photo gallery.")
    if args.dry_run:
        print("Dry run: no files were copied or changed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (FileNotFoundError, FileExistsError, ValueError, yaml.YAMLError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
