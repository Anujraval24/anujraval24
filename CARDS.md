# How the profile cards work

The README is a stack of SVG cards in `cards/`, drawn by one script from two JSON files.

| File | Purpose |
| --- | --- |
| `data/profile.json` | Name, tagline, links, tiles, featured repos, brand colours. Edit this to change the cards. |
| `data/contributions.json` | Contribution days and repo stats. Refreshed by the Action, don't edit by hand. |
| `scripts/fetch_data.py` | Pulls fresh data from GitHub. |
| `scripts/render_cards.py` | Renders every card into `cards/`. |
| `fonts/` | Bricolage Grotesque (SIL Open Font License). Subset per card with `pyftsubset` and embedded. |
| `docs/index.html` | The portfolio site, using the same colours and font. |

## Schedule

`.github/workflows/cards.yml` runs daily at 05:47 IST, on every push that touches the scripts, fonts or `profile.json`, and on demand from the Actions tab (Run workflow). It fetches data, renders the cards and commits any change.

## Preview the final frame

```bash
pip install fonttools
STATIC=1 python scripts/render_cards.py   # writes cards-static/, no animation
```

`cards-static/` is git-ignored. The normal run (`python scripts/render_cards.py`) writes the animated cards to `cards/`.

## Turn on the portrait

The Action saves your GitHub avatar to `data/avatar.jpg`. To show it in the hero, set `"portrait": "data/avatar.jpg"` in `data/profile.json`.

## Publish the site

Repository Settings, Pages, Source: "Deploy from a branch", branch `main`, folder `/docs`. The site is then at `https://anujraval24.github.io/anujraval24/`, which the Portfolio tile links to. If you host it elsewhere, change `links.site` in `profile.json` and the Portfolio link in `README.md`.

## If the calendar comes back empty

The built-in `GITHUB_TOKEN` is normally enough. If the Action fails with an empty calendar, create a classic personal access token with the `read:user` scope and save it as the repository secret `PROFILE_TOKEN`.
