---
# PEOPLE TEMPLATE
# Copy this structure for any new member page under `content/people/`.
# If a new field is introduced in the project, it should also be documented here.

# Full public name shown on the page.
title: "Prof. New Member Name"

# Internal identifier used by CSS helpers and some templates.
# Keep it lowercase and slug-like.
id: "new-member-name"

# Canonical URL for the profile page.
# Example subgroup routes:
# /matcat/people/new-member-name/
# /isom/people/new-member-name/
# /biokt/people/new-member-name/
url: "/group-slug/people/new-member-name/"

# Optional alternative URLs that should redirect here.
# Remove this block if not needed.
aliases:
  - "/people/new-member-name/"

# Keep the large page hero disabled for people pages.
hide_page_hero: true

# Optional ordering value. Lower numbers appear first where sorting by weight is used.
weight: 999

# One of: researcher, postdoc, phd, former_postdoc, former_phd
member_type: "researcher"

# Profile layout: regular (default) or tx1.
template: "regular"

# Optional teaching entries displayed by the tx1 profile layout.
# teaching:
#   - title: "Course title"
#     description: "Optional course description"
#     url: "https://example.edu/course"

# Optional structured contact information.
# Leave the field empty or remove it if not available.
office: "Kimika Teorikoa Laboratory; Kimika Fakultatea"
location: "Euskal Herriko Unibertsitatea, PK 1072, 20080 Donostia, Spain"
phone: "+34 000 000 000"
email: "name.surname [@] ehu.eus"

# Optional CV file.
# Put the PDF in `static/files/cv/` and link it like this:
cv: "/files/cv/new-member-name-cv.pdf"

# Optional social links.
twitter: "https://x.com/username"
bluesky: "https://bsky.app/profile/username.bsky.social"

# Profile photo.
# Store the image in one of these folders, depending on the member type:
# `static/images/members/researchers/`
# `static/images/members/postdocs/`
# `static/images/members/phd/`
photo: "/images/members/researchers/new-member-name.jpg"

# Optional fine-tuning for the crop inside square cards/pages.
# Example: "center 12%" or "50% 20%"
photo_position: "center center"

# One or more internal group ids.
# Current values in the project include:
# matcat, isom, biokt, polkt, noft, moleles, qcd, momag
groups: ["matcat"]

# Group labels are derived automatically from `groups`.

# Optional role shown prominently below the name.
role: "MatCat-KT Group Leader"

# Optional academic/professional position.
position: "Profesor Agregado"

# Optional institutional affiliation line.
affiliation: "EHU & DIPC"

# Author-name variants used to match publications automatically.
# Add as many variants as needed.
publication_names:
  - "New Member Name"
  - "N. M. Name"
  - "N.M.Name"

# Optional academic/profile links.
orcid: "https://orcid.org/0000-0000-0000-0000"
researcher_id: "https://www.webofscience.com/wos/author/record/XXXX-0000"
google_scholar: "https://scholar.google.com/citations?user=XXXXXXXXXXX"
research_gate: "https://www.researchgate.net/profile/Example"
scopus: "https://www.scopus.com/authid/detail.uri?authorId=00000000000"
ikerbasque: " "

# Header configuration for the profile page.
# Keep `variant: subgroup` when the page should use a subgroup header.
header:
  variant: "subgroup"
  menu: "matcat"
  accent: "matcat"
  brand_name: "MatCat-KT Group"
  brand_note: "Euskal Herriko Unibertsitatea & DIPC"
  brand_url: "/matcat/"
---

<!--
Optional free-form markdown content starts below.
Use this area for personal sections such as:
- Main Research Interests
- Scientific Career
- Awards
- Projects
- Teaching

This content will appear before the publications list.
-->

## Main Research Interests

- Topic one
- Topic two
- Topic three

## Scientific Career

- `2024-today`: Current position and institution.
- `2021-2024`: Previous position and institution.

## Notes

Add any extra information here using normal Markdown.
