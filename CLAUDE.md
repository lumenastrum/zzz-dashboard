# ZZZ Dashboard — context for Claude / Clio / Couch-Clio / VPS-Clio

Single-page Zenless Zone Zero roster + stat-audit dashboard for Andres. Vanilla
HTML/CSS/JS (`index.html`), **no build step, no framework**. Data lives in Supabase
(source of truth) and is mirrored to a git-tracked JSON seed.

## Stack at a glance

- **`index.html`** — the whole app (CSS + HTML + vanilla JS, ~1000 lines). Loads
  `@supabase/supabase-js@2` from jsDelivr. Two tabs: **Agent Roster**, **Stat Audit**.
- **Supabase** — `dashboard_profiles` table, JSONB `data` column, keyed by `profile`.
  Anon key is in the client by design (public). Same project as the WuWa dashboard.
- **Two profiles** — `andres` (→ `data.json`) and `wife` (→ `wife-data.json`).
  Switch in the UI or with `?profile=wife`.
- **Dev server** — `py -m http.server 8090` (use `py`, not `python3`, on Windows),
  then open `http://localhost:8090`. Config in `.claude/launch.json`.

## How writes work

- Load order: **Supabase first** → fall back to the local JSON seed → seed Supabase
  if its row is empty. So **Supabase is the source of truth**; the JSON files are the
  git-tracked backup/seed.
- The **browser** can only edit Stat-Audit *current values* (click a stat → type).
  Everything else — adding agents, roster fields, sessions, pull recs — goes through
  the CLI below. (Stat colors recompute live from each stat's `min`/`max`.)

## The CLI — `zzz_update.py` (this is the hands)

Zero-dependency Python (stdlib only). Runs on every Clio surface:

```
in PowerShell (Windows):   py zzz_update.py <command> [args]
in bash (Mac / VPS):       python3 zzz_update.py <command> [args]
```

It reads the live Supabase row, mutates it, writes it back, **and mirrors the local
JSON seed** (unless `--remote-only`). Run `py zzz_update.py help` for the full surface.
Highlights:

```
list                                  roster summary (read-only)
show "Miyabi"                         one agent + its audit (read-only)
addagent "Trigger" STUN Electric [--mindscape M0 --wengine W1 --level 60 \
                                   --specialty Stun --discs "..." --notes "..."]
rmagent "Trigger"
setagent "Vivian" mindscape M3        (or shortcuts: level/mindscape/wengine/discs/note/section)
addaudit "Trigger" "Anomaly Stunner"  then: addstat "Trigger" <label> <optimal> <current> <min>
stat "Miyabi" "CRIT DMG" 150%         set a stat's current value (color follows automatically)
addsession "Label" "Detail" green
addpull 1 "Orpheus" --priority "Save" --why "..." --team "..."
meta updated 2026-06-17
```

Global flags: `--profile andres|wife` (default andres), `--remote-only` (skip the
local JSON mirror), `--dry` (print the resulting JSON, save nothing — good for previews).

After any mutation it auto-sets `meta.updated` to today and recomputes `meta.totalAgents`.

## Portraits (when you add a new agent)

Portraits are filesystem PNGs in `Portraits/`, wired by a `PORTRAIT_MAP` dict near the
top of `index.html`'s `<script>`. Convention: lowercase, spaces stripped
(`"Soldier 0 Anby"` → `soldier0anby.png`), but a few are irregular (`Seed.png`,
`"Anby"` → `anbyarank.png`). A missing portrait gracefully falls back to initials, so
nothing breaks — but `addagent` **warns** when an agent isn't in `PORTRAIT_MAP` and
tells you the two lines to add. Do both: drop the PNG, add the map entry.

## Data shape (the JSONB blob)

```
meta:    { title, updated (YYYY-MM-DD), totalAgents, maxLevel, sessionTitle }
agents:  [{ name, section, specialty, attribute, mindscape, wengine, level, discs, notes }]
audit:   [{ name, type, stats: [{label, optimal, current, min, max?, capMax?, unit?, note?}],
            before, delta, priority, priorityStatus }]
sessions:[{ label, detail, status }]
pullRecommendations: [{ rank, name, priority, why, team }]
```

Sections: `ATTACK ANOMALY STUN SUPPORT RAPTURE`. Attributes: `Physical Fire Electric Ice Ether`.
Status colors: `green yellow red neutral`. The audit card color is **derived live** from
the stats' `min`/`max` (`getStatStatus`/`recalcPriority` in `index.html`), so set good
`min` values — the stored `priorityStatus` is backup, not what's rendered.

## Gotchas

- **Supabase is truth, not the JSON file.** If you hand-edit `data.json`, it only takes
  effect when the Supabase row is empty (seed). To make a live change, use the CLI (it
  writes both) or the browser. The CLI keeps them in sync going forward.
- **Use `py` on Windows**, `python3` on Mac/VPS. The script forces UTF-8 stdout so the
  ✓/✕ marks don't crash Windows' cp1252 console.
- **Label the shell for Andres** — say "in PowerShell" / "in bash on the VPS" when handing
  him a command; he juggles three terminals.
