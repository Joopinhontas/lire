# Design brief

The product and design principles every change to Lire's interface is checked against.

## Users
A self-hoster and the few friends they share the server with, reading manga and comics on a tablet (designed on an iPad Pro 13") at home or on the move, often in the evening under low light. The job: find a series by name (often misspelled or typed in French), see at a glance which tomes are already on the shelf, which ones can be found and which ones are nowhere, then start everything missing in one tap and go read in Kavita.

## Product Purpose
A self-hosted "Seerr for manga": it resolves a series (AniList, Kitsu, MangaDex), searches the indexers configured in Prowlarr under every known title, understands tome numbering in messy release names, computes the smallest set of torrents that covers the most tomes (official ebooks and CBZ first), then files everything per series for Kavita. Success is "type a name, tap once, the whole series lands in Kavita overnight" without ever reading a release name.

## Brand Personality
Quiet, precise, confident. A tool that feels like a well-kept bookshelf in a dark room: the tomes are the interface, the text only explains what the shelf already shows. Voice is short and concrete in both languages ("42 et 43 à télécharger" / "42 and 43 to download", never "New releases available!").

## Anti-references
- Search-result UIs: dense tables of raw release names and technical columns.
- Generic streaming clones (Netflix-style hero banners, autoplay carousels).
- SaaS dashboards with metric cards and gradient accents.
- Seerr/Overseerr's purple-gradient look.

## Design Principles
- The shelf is the answer: owned, downloading, planned and missing tomes must read in one glance before any text.
- One tap for the common case, detail on demand: the recommended plan is the default, manual choices stay one level down.
- Never expose indexer noise by default: raw release names are secondary information.
- Honest states: say plainly when a tome does not exist anywhere or has no seeders, instead of pretending it will come.
- Fast to trust: every action reports what it did (added, skipped, moved) in plain words.

## Accessibility & Inclusion
WCAG 2.2 AA contrast on a dark surface, touch targets of at least 48px for finger use on iPad, no hover-only affordances, full keyboard support for the hardware keyboard, and a reduced-motion alternative for every animation. States are never conveyed by color alone (shape, fill pattern and text labels back them up).
