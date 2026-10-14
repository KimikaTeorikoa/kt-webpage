# Donostia Kimika Teorikoa — Hugo site

This repository contains the Hugo prototype/site for the Donostia Kimika Teorikoa (KT) research groups.

## How research groups are defined

Each group is a Hugo section under `content/<group>/`. The main source of truth for a group is its landing page:

```
content/<group>/_index.md
```

This file contains the group metadata, research lines and optional resources. The generator script reads this file and creates the per-research-line pages, the research index page and the resources page automatically.

### Minimal example: `content/biokt/_index.md`

```yaml
---
title: "Bio-KT Lab"
hide_hero: true
home_title: "Welcome to the Bio-KT Laboratory"
weight: 3
header:
  variant: "subgroup"
  menu: "biokt"
  accent: "biokt"
  brand_name: "Bio-KT Lab"
  brand_note: "Euskal Herriko Unibertsitatea & DIPC"
  brand_url: "/biokt/"
research_group_card:
  key: "biokt"
  label: "Bio-KT"
  logo: "/images/groups/biokt.png"
  summary: "Electronic structure and modelling strategies aimed at biologically relevant molecules, processes and interactions"
  leadership_label: "co-led by"
  leaders:
    - page: "/people/xabier-lopez"
      name: "Xabier Lopez"
    - page: "/people/david-de-sancho"
      name: "David de Sancho"
research_intro: false
research_lines:
  - slug: "protein-metal-interactions"
    eyebrow: "Protein Metal Interactions"
    title: "Quantum mechanics of protein-metal interactions"
    summary: "Aluminum is the third most abundant element..."
    dois:
      - "10.1039/d3cp03179a"
resources:
  title: "Software and Data Repositories"
  items:
    - name: MasterMSM
      summary: "Code for building master equation (Markov state) models of molecular kinetics."
      link: "https://github.com/daviddesancho/MasterMSM"
---

Bio-KT Laboratory operates within the Donostia Kimika Teorikoa research group...
```

### Key front-matter fields

| Field | Purpose |
|-------|---------|
| `header` | Navigation header: `menu`, `accent`, `brand_name`, `brand_url`. |
| `research_group_card` | Group card shown on the research-groups overview page. |
| `research_lines` | List of research lines. Each line becomes a page under `content/<group>/research/<slug>/`. |
| `research_intro` | Optional intro text above the grid; `false` suppresses it. |
| `resources` | Optional software/data list. Creates a `Resources` menu item and a page at `/resources/`. |

### Canonical content sources

Keep each kind of information in one place:

- A group is defined by `content/<group>/_index.md`. Its `research_group_card`
  supplies the public group label and logo to templates and maintenance scripts.
- A person is defined by `content/people/<person>.md`. Set `groups` with group
  keys such as `matcat` or `polkt`; labels are derived automatically.
- Published articles live in `data/publications/years/<year>.yaml`, while
  submissions live in `data/publications/submitted.yaml`.
- News, gallery, seminars and theses use their respective `content/news/` or
  `data/` sources. Do not create backups or templates under `content/`, because
  Hugo publishes every content file.

When adding a group, use its `_index.md` as the only source for its key, label,
logo, leaders, research lines and contact data. Navigation and scripts derive
the public label from that definition.

Create a standard internal group interactively:

```bash
python3 scripts/add_group.py
```

The command can also be scripted:

```bash
python3 scripts/add_group.py --slug new-kt --label New-KT --title "New-KT Lab"
```

It creates the group landing page, members, publications, research and contact
pages, plus its local navigation. Add the requested logo beneath `static/` and
run `make validate`. The global menus and home constellation pick up the new
group automatically.

## Generating research pages

The main generator script is:

```bash
scripts/generate_research_pages.py
```

### Basic usage

Generate pages for a single group:

```bash
python3 scripts/generate_research_pages.py -g biokt
```

Regenerate everything for a group, overwriting existing pages and persisting short excerpts:

```bash
python3 scripts/generate_research_pages.py -g biokt --force --update-index --excerpt-words 4
```

Run the generator for every group that has `research_lines` or `resources`:

```bash
python3 scripts/generate_research_pages.py --all-groups --update-index --force --excerpt-words 4
```

### Common options

| Option | Meaning |
|--------|---------|
| `-g, --group <name>` | Group to process (e.g. `biokt`, `isom`, `polkt`). |
| `--all-groups` | Process every group in `content/`. |
| `--dry-run` | Preview changes without writing files. |
| `--force` | Overwrite existing research-line pages and index pages. |
| `--update-index` | Write `card_excerpt` and `card_tone` back into `content/<group>/_index.md`. |
| `--excerpt-words <n>` | Number of words used for the grid card excerpt (default: 4). |
| `--slug <slug>` | Process only one research line. |

### What the script creates

For each group it creates/updates:

- `content/<group>/research/<slug>/_index.md` — one page per research line.
- `content/<group>/research/_index.md` — the research index page (like MatCat's).
- `content/<group>/resources/_index.md` — if a `resources:` section exists.
- `data/navigation/<group>.yaml` — adds a `Resources` menu item if needed.

## TOC images for research lines

The generator tries to populate a TOC image for each publication:

1. It queries the Crossref API for each DOI listed under a research line.
2. If Crossref advertises an image link, it downloads it.
3. If not, it tries to resolve the DOI landing page and looks for `og:image`, `twitter:image`, `image_src` or other heuristic image hints.
4. Downloaded images are saved to:

   ```
   static/images/publications/toc/<safe-doi>.<ext>
   ```

Many publishers block programmatic access (HTTP 403/404), so automatic downloads often fail. If you already have a TOC image, place it in the directory above and run:

```bash
python3 scripts/attach_found_toc_images.py
```

This script scans the existing images in `static/images/publications/toc/` and attaches them to the matching publication entries by DOI. It preserves any manually added `toc_image` fields.

## Adding submitted publications

Use the interactive helper to add a publication that has been submitted but does not yet have publication metadata:

```bash
python3 scripts/add_submitted_publication.py
```

Enter the title, authors separated by semicolons, submission date (the default is today), and optional research-group tags. The script compares author names with profile `publication_names`, assigns exact matches automatically, and asks whether to associate unmatched authors with a team member. The saved profile IDs determine which profiles display the entry; group tags also make the submission appear on that group's publications page, but not in the site-wide publications directory. Review the preview and confirm before writing.

To provide a non-default date:

```bash
python3 scripts/add_submitted_publication.py --date 2026-09-29
```

Group tags can be passed directly as well:

```bash
python3 scripts/add_submitted_publication.py --tags MatCat-KT
```

Build and deploy the site to publish the updated profile pages.

## Updating selected research publications

To replace one DOI selected for a research line:

```bash
python3 scripts/update_research_publication.py
```

The helper asks for the group, research line, current selected publication and replacement DOI. It validates the DOI, prevents selecting the same DOI twice in one line, and automatically regenerates the selected research-line page. Use `--no-regenerate` only when regeneration should be done separately. The equivalent MyTools wrappers are `update_research_pub` and `update_selected`; use `--group matcat` to skip the group selection.

To regenerate research-line pages interactively:

```bash
generate_research_pages
```

It asks for the group and line (or all lines). Command-line options remain available, for example `generate_research_pages --group matcat --slug polymers --force`.

When you later add the published article with `scripts/add_publication.py`, the script checks for submitted entries with the same normalized title. It shows the submitted and published authors and asks before removing each possible match; the default is to keep the submitted entry for manual review.

## Local preview and deploy

A `Makefile` is provided for common tasks. You can override any variable on the command line or in a local `.env` file.

### Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PROD_BASEURL` | `https://www.ehu.eus/chemistry/theory/new/` | Base URL used for the production build. |
| `SFTP_USER` | `scwtcg` | SFTP username. |
| `SFTP_HOST` | `alweb.ehu.eus` | SFTP server host. |
| `REMOTE_PATH` | `/users/scwtcg/public_html/new` | Destination directory on the server. |

### Makefile targets

```bash
# Local development server
make serve

# Validate data and produce the production build (uses PROD_BASEURL)
make validate

# Deploy the public/ folder via SFTP using lftp
make deploy

# Remove the generated public/ folder
make clean
```

### Example: deploy from scratch

```bash
# 1. Validate and build for production
make validate

# 2. Deploy using your configured SFTP authentication
make deploy
```

### Recommended `.env` file

Create a `.env` file in the repository root (it is already ignored by git):

```bash
PROD_BASEURL="https://www.ehu.eus/chemistry/theory/new/"
SFTP_USER="scwtcg"
SFTP_HOST="alweb.ehu.eus"
REMOTE_PATH="/users/scwtcg/public_html/new"
```

Then simply run:

```bash
make validate
make deploy
```

> **Security note:** never commit `.env` or any file containing passwords. The repository already ignores `.env`.

## Adding gallery photos

Add one or more local images to an event with:

```bash
python3 scripts/add_gallery.py "Group dinner (17.09.2026)" photos/*.jpg
```

The command also accepts directories, copies the images into
`static/images/gallery/`, updates `data/gallery.yaml`, reuses an event with
the same title, and sorts events from newest to oldest using the last date
found in each title. Use `--dry-run` to preview the operation.

## Adding news

Create a news post interactively:

```bash
python3 scripts/add_news.py
```

Enter a date (`DD.MM.YYYY`, or press Enter to use today's date), title, and
whether the news item has a banner photo (default: no). If yes, enter its image
path. The script then asks if the article has additional photos (default: no);
if yes, enter the number of photos and each image path. If any photos were
provided, choose whether to add them to the photo gallery (default: no).
Finish by entering the Markdown text, ending with a single `.` on its own line.
The script creates a dated post under `content/news/` and copies any media into
`static/images/news/`. If you opt in, it also copies the provided photos to
`static/images/gallery/` and creates a gallery event. News posts are shown
newest first on `/news/`; the home-page ticker also includes the next seminar,
the latest past seminar, and recent news. The local `make serve` target
includes future-dated news so scheduled items can be previewed; normal
production builds still publish them
on their date. For a banner, edit its `banner_scale` front-matter value to
control its width on the news article page (percentage, 1–100; default: 100).
Use `--dry-run` to walk through the prompts without writing files, or
`--help` to see the available option.

## Adding seminars

Add an upcoming seminar with:

```bash
python3 scripts/add_seminar.py
```

Enter its date (`DD.MM.YYYY`), time, optional place, talk title and speaker.
Upcoming seminars accumulate under `next.entries` in `data/seminars.yaml`
(shown as "Next seminars", each with an `iso` date). Every time the script
runs it moves the seminars whose date has passed to the past-seminar archive;
`python3 scripts/add_seminar.py --archive-only` does only that. Use
`--dry-run` to preview a change.

The site also classifies seminars by date at build time: a seminar is "next"
until its day is over, then it appears as the latest/past seminar. Because the
site is static, that switch happens on the next `make build`/deploy, so deploy
again (or schedule a daily deploy) after a seminar date passes. Do not run
`scripts/import_seminars.py`: it was a one-time import and is disabled to
protect the seminar data.

## Typical workflow

1. Add or edit `content/<group>/_index.md` with research lines and/or resources.
2. Run the generator:
   ```bash
   python3 scripts/generate_research_pages.py -g <group> --update-index --force --excerpt-words 4
   ```
3. Optionally attach TOC images:
   ```bash
   python3 scripts/attach_found_toc_images.py
   ```
4. Preview locally:
   ```bash
   make serve
   ```
5. Build and deploy:
   ```bash
   make validate
   make deploy
   ```

## Validation

Run the following before deploying manually edited YAML or generated content:

```bash
make validate
```

It validates every data YAML file, verifies person and publication group keys,
builds the production site, and rejects generated localhost links.

## Header themes

Two header layouts are available:

- `default`: the current multi-band header.
- `classic`: a compact one-row header with the KT logo and subgroup logo on the
  left, and the navigation on the right. The footer is unchanged.

Switch theme and build the site:

```bash
scripts/change_theme.sh classic
scripts/change_theme.sh default
```

Running `change_theme` without an argument opens an interactive selection. The
same command is available from any directory through:

```bash
~/MyTools/change_theme classic
```

---

## Legacy prototype notes

This folder started as a Hugo-based migration scaffold focused on structure first.

- Content already lives in Hugo-friendly files under `content/`
- subgroup landing pages are modeled as sections, which maps well to HugoBlox landing pages
- navigation is externalized in `data/navigation/`
- header behavior is isolated in reusable partials
