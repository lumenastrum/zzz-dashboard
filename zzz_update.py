#!/usr/bin/env python3
"""ZZZ dashboard CLI — add / update agents, audit, sessions & pull recs.

Writes LIVE to the same Supabase row the dashboard reads (source of truth),
and mirrors the local data.json / wife-data.json seed unless --remote-only.

Zero dependencies (stdlib only) so any Clio surface can run it:
  in PowerShell (Windows):   py zzz_update.py <command> [args]
  in bash (Mac / VPS):       python3 zzz_update.py <command> [args]

Quick start:
  py zzz_update.py list
  py zzz_update.py addagent "Trigger" STUN Electric --mindscape M0 --wengine W1
  py zzz_update.py level "Evelyn" 60
  py zzz_update.py stat "Miyabi" "CRIT DMG" 150%
  py zzz_update.py help            # full command surface

Global flags (any command):
  --profile andres|wife   which roster (default: andres)
  --remote-only           skip mirroring to the local JSON seed
  --dry                   print the resulting JSON, save nothing
"""

import json
import sys
import os
import urllib.request
import urllib.error
from datetime import datetime, date, timezone

# ── Supabase (same project + anon key the dashboard uses; anon is public by design) ──
SUPABASE_URL = "https://ayhrqkxdeecybjhmgdoq.supabase.co"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF5aHJxa3hkZWVjeWJqaG1nZG9xIiwicm9sZSI6ImFub24i"
    "LCJpYXQiOjE3NzgyOTI0NjcsImV4cCI6MjA5Mzg2ODQ2N30.GN-y9xEyNfQUVUXCqOGJC5cpN35X7B8PpOlFJPn10A8"
)
SUPABASE_TABLE = "dashboard_profiles"

# profile key (Supabase) → local seed file (mirrored next to this script)
PROFILE_CONFIG = {
    "andres": "data.json",
    "wife": "wife-data.json",
}

SECTIONS = ["ATTACK", "ANOMALY", "STUN", "SUPPORT", "RAPTURE"]
ATTRS = ["Physical", "Fire", "Electric", "Ice", "Ether", "Wind"]
STATUSES = ["green", "yellow", "red", "neutral"]

# Windows consoles default to cp1252 and choke on ✓/✕/· — force UTF-8 (no-op elsewhere).
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

HERE = os.path.dirname(os.path.abspath(__file__))

# value-taking long options; everything else after -- is a boolean flag
VALUE_OPTS = {"profile", "mindscape", "wengine", "level", "specialty",
              "discs", "notes", "max", "unit", "note", "priority", "why", "team"}
BOOL_FLAGS = {"remote-only", "dry", "capmax"}


class Offline(Exception):
    pass


# ── tiny output helpers ──────────────────────────────────────────────────────
def die(msg):
    sys.stderr.write("✕ " + str(msg) + "\n")
    sys.exit(1)


def ok(msg):
    print("✓ " + str(msg))


def note(msg):
    print("· " + str(msg))


# ── arg parsing (positional + --key value + --flag) ──────────────────────────
def parse_args(argv):
    pos, opts, flags = [], {}, set()
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            key = a[2:]
            if key in BOOL_FLAGS:
                flags.add(key)
                i += 1
            elif key in VALUE_OPTS:
                if i + 1 >= len(argv):
                    die("option --" + key + " needs a value")
                opts[key] = argv[i + 1]
                i += 2
            else:
                die("unknown option --" + key)
        else:
            pos.append(a)
            i += 1
    return pos, opts, flags


# ── HTTP ─────────────────────────────────────────────────────────────────────
def _headers():
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": "Bearer " + SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }


def fetch_remote(profile):
    url = SUPABASE_URL + "/rest/v1/" + SUPABASE_TABLE + "?select=data&profile=eq." + profile
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            rows = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        die("Supabase read failed: HTTP " + str(e.code) + " " + e.read().decode()[:200])
    except urllib.error.URLError:
        raise Offline()
    if not rows:
        return None
    return rows[0].get("data")


def save_remote(profile, data):
    url = SUPABASE_URL + "/rest/v1/" + SUPABASE_TABLE + "?on_conflict=profile"
    body = json.dumps({
        "profile": profile,
        "data": data,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).encode()
    h = _headers()
    h["Prefer"] = "resolution=merge-duplicates,return=minimal"
    req = urllib.request.Request(url, data=body, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
    except urllib.error.HTTPError as e:
        die("Supabase save failed: HTTP " + str(e.code) + " " + e.read().decode()[:300])
    except urllib.error.URLError:
        die("Supabase save failed: can't reach the network.")


def local_path(profile):
    fname = PROFILE_CONFIG.get(profile)
    return os.path.join(HERE, fname) if fname else None


def read_local(profile):
    p = local_path(profile)
    if not p or not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def write_local(profile, data):
    p = local_path(profile)
    if not p:
        return False
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return True


# ── finders ──────────────────────────────────────────────────────────────────
def find_agent(data, name):
    for a in data["agents"]:
        if a["name"] == name:
            return a
    names = ", ".join(a["name"] for a in data["agents"])
    die('no agent named "' + name + '". Known: ' + names)


def find_audit(data, name):
    for a in data["audit"]:
        if a["name"] == name:
            return a
    die('no audit row for "' + name + '" (create one: addaudit "' + name + '" "<type>")')


def find_stat(audit, label):
    for s in audit["stats"]:
        if s["label"] == label:
            return s
    has = ", ".join(s["label"] for s in audit["stats"])
    die('stat "' + label + '" not on ' + audit["name"] + ". Has: " + has)


def find_pull(data, rank):
    for p in data.get("pullRecommendations", []):
        if int(p.get("rank", -1)) == rank:
            return p
    die("no pull recommendation with rank #" + str(rank))


# ── validators / normalizers ─────────────────────────────────────────────────
def need(cond, msg):
    if not cond:
        die(msg)


def vsection(s):
    su = s.upper()
    need(su in SECTIONS, "section must be one of: " + ", ".join(SECTIONS) + ' (got "' + s + '")')
    return su


def vattr(a):
    ac = a.capitalize()
    need(ac in ATTRS, "attribute must be one of: " + ", ".join(ATTRS) + ' (got "' + a + '")')
    return ac


def vstatus(s):
    need(s in STATUSES, "status must be one of: " + ", ".join(STATUSES) + ' (got "' + s + '")')
    return s


def vmindscape(v):
    raw = str(v).upper().lstrip("M")
    need(raw.isdigit() and 0 <= int(raw) <= 6, 'mindscape must be M0..M6 (got "' + str(v) + '")')
    return "M" + raw


def vwengine(v):
    raw = str(v).upper().lstrip("W")
    need(raw.isdigit() and 0 <= int(raw) <= 5, 'wengine must be W0..W5 (got "' + str(v) + '")')
    return "W" + raw


def vint(v, label="value"):
    try:
        return int(v)
    except (TypeError, ValueError):
        die("expected an integer for " + label + ' (got "' + str(v) + '")')


def vfloat(v, label="value"):
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        die("expected a number for " + label + ' (got "' + str(v) + '")')


def portrait_guard(data_profile_path, name):
    """Warn if a new agent has no portrait wired — dashboard falls back to initials."""
    idx = os.path.join(HERE, "index.html")
    mapped = False
    if os.path.exists(idx):
        with open(idx, "r", encoding="utf-8") as f:
            mapped = ('"' + name + '"') in f.read()
    derived = name.lower().replace(" ", "").replace("'", "")
    file_guess = os.path.join(HERE, "Portraits", derived + ".png")
    if mapped:
        return
    note('no portrait wired for "' + name + '" — it will show initials until you:')
    note('    1. drop a PNG in Portraits/ (e.g. ' + derived + ".png)")
    note('    2. add  "' + name + '": "' + derived + '.png"  to PORTRAIT_MAP in index.html')
    if os.path.exists(file_guess):
        note("    (found Portraits/" + derived + ".png already — just add the map line)")


# ── command surface ──────────────────────────────────────────────────────────
HELP = """ZZZ dashboard CLI · profiles: """ + " / ".join(PROFILE_CONFIG.keys()) + """

usage (PowerShell):  py zzz_update.py <command> [args] [--profile andres]
usage (bash):        python3 zzz_update.py <command> [args]

roster:
  addagent <name> <section> <attribute>   add an agent (sections: """ + "/".join(SECTIONS) + """)
      [--mindscape M0] [--wengine W0] [--level 60] [--specialty X]
      [--discs "4pc ... + 2pc ..."] [--notes "..."]
  rmagent <name>                          remove an agent
  setagent <name> <field> <value...>      field: section|specialty|attribute|
                                          mindscape|wengine|level|discs|notes
  level <name> <int>                      shortcut: set level
  mindscape <name> <M0..M6>               shortcut
  wengine <name> <W0..W5>                 shortcut
  discs <name> <text...>                  shortcut (use "-" to clear)
  note <name> <text...>                   shortcut (use "-" to clear)
  section <name> <SECTION>                shortcut

audit (the Stat Audit tab; colors recompute live from min/max):
  addaudit <name> <type...>               create a blank audit card
  rmaudit <name>
  auditfield <name> <field> <value...>    field: type|before|delta|priority|prioritystatus
  addstat <name> <label> <optimal> <current> <min>
      [--max N] [--unit %] [--capmax] [--note X]
  stat <name> <label> <current...>        set a stat's current value
  statopt <name> <label> <text...>        set a stat's optimal range text
  statmin <name> <label> <num>            set a stat's min threshold (drives color)
  rmstat <name> <label>

sessions (Session Results list):
  addsession <label> <detail> <status>    status: """ + "/".join(STATUSES) + """
  session <idx> <field> <value...>        field: label|detail|status
  rmsession <idx>

pull priority:
  addpull <rank> <name> [--priority X] [--why "..."] [--team "..."]
  setpull <rank> <field> <value...>       field: rank|name|priority|why|team
  rmpull <rank>

meta / info:
  meta <field> <value...>                 field: title|updated|maxlevel|sessiontitle
  list                                    summary of the roster
  show <name>                             one agent + its audit
  help                                    this message"""


def cmd_list(data):
    m = data.get("meta", {})
    print("title:   " + str(m.get("title", "?")))
    print("updated: " + str(m.get("updated", "?")))
    print("agents:  " + str(len(data["agents"])) + "   audit cards: " + str(len(data["audit"]))
          + "   sessions: " + str(len(data.get("sessions", [])))
          + "   pull recs: " + str(len(data.get("pullRecommendations", []))))
    for sec in SECTIONS:
        rows = [a for a in data["agents"] if a.get("section") == sec]
        if not rows:
            continue
        print("\n" + sec + " (" + str(len(rows)) + ")")
        for a in rows:
            audited = " ✓audit" if any(x["name"] == a["name"] for x in data["audit"]) else ""
            print("  " + a["name"].ljust(16) + " " + str(a.get("attribute", "")).ljust(9)
                  + " " + str(a.get("mindscape", "")) + " " + str(a.get("wengine", ""))
                  + " Lv." + str(a.get("level", "")) + audited)


def cmd_show(data, name):
    a = find_agent(data, name)
    print(json.dumps(a, indent=2, ensure_ascii=False))
    for au in data["audit"]:
        if au["name"] == name:
            print("\naudit:")
            print(json.dumps(au, indent=2, ensure_ascii=False))
            return
    note("(no audit card for this agent)")


def run(cmd, pos, opts, flags, data):
    """Returns True if data was mutated."""
    # ── roster ──
    if cmd == "addagent":
        need(len(pos) >= 3, 'usage: addagent <name> <section> <attribute> [--mindscape ...]')
        name = pos[0]
        if any(a["name"] == name for a in data["agents"]):
            die('agent "' + name + '" already exists (use setagent to edit)')
        section = vsection(pos[1])
        agent = {
            "name": name,
            "section": section,
            "specialty": opts.get("specialty", section.capitalize()),
            "attribute": vattr(pos[2]),
            "mindscape": vmindscape(opts.get("mindscape", "M0")),
            "wengine": vwengine(opts.get("wengine", "W0")),
            "level": vint(opts.get("level", data.get("meta", {}).get("maxLevel", 60)), "level"),
            "discs": opts.get("discs"),
            "notes": opts.get("notes"),
        }
        data["agents"].append(agent)
        ok("added " + name + " (" + section + " · " + agent["attribute"]
           + " · " + agent["mindscape"] + " " + agent["wengine"] + " Lv." + str(agent["level"]) + ")")
        portrait_guard(data, name)
        return True

    if cmd == "rmagent":
        need(len(pos) >= 1, "usage: rmagent <name>")
        find_agent(data, pos[0])
        data["agents"] = [a for a in data["agents"] if a["name"] != pos[0]]
        ok("removed agent " + pos[0])
        return True

    if cmd == "setagent":
        need(len(pos) >= 3, "usage: setagent <name> <field> <value...>")
        a = find_agent(data, pos[0])
        field = pos[1].lower()
        val = " ".join(pos[2:])
        if field == "section":
            a["section"] = vsection(val)
        elif field == "attribute":
            a["attribute"] = vattr(val)
        elif field == "mindscape":
            a["mindscape"] = vmindscape(val)
        elif field == "wengine":
            a["wengine"] = vwengine(val)
        elif field == "level":
            a["level"] = vint(val, "level")
        elif field in ("specialty", "discs", "notes"):
            a[field] = None if val == "-" else val
        else:
            die("setagent field must be: section|specialty|attribute|mindscape|wengine|level|discs|notes")
        ok(pos[0] + " " + field + " → " + str(a[field]))
        return True

    if cmd in ("level", "mindscape", "wengine", "discs", "note", "section"):
        need(len(pos) >= 2, "usage: " + cmd + " <name> <value...>")
        a = find_agent(data, pos[0])
        val = " ".join(pos[1:])
        if cmd == "level":
            a["level"] = vint(val, "level")
        elif cmd == "mindscape":
            a["mindscape"] = vmindscape(val)
        elif cmd == "wengine":
            a["wengine"] = vwengine(val)
        elif cmd == "section":
            a["section"] = vsection(val)
        elif cmd == "discs":
            a["discs"] = None if val == "-" else val
        elif cmd == "note":
            a["notes"] = None if val == "-" else val
        key = "notes" if cmd == "note" else cmd
        ok(pos[0] + " " + key + " → " + str(a[key]))
        return True

    # ── audit ──
    if cmd == "addaudit":
        need(len(pos) >= 2, 'usage: addaudit <name> <type...>')
        name = pos[0]
        if any(x["name"] == name for x in data["audit"]):
            die('audit card for "' + name + '" already exists')
        data["audit"].append({
            "name": name, "type": " ".join(pos[1:]), "stats": [],
            "before": None, "delta": None, "priority": "", "priorityStatus": "neutral",
        })
        ok("added audit card for " + name + " — add stats with: addstat \"" + name + "\" <label> <optimal> <current> <min>")
        return True

    if cmd == "rmaudit":
        need(len(pos) >= 1, "usage: rmaudit <name>")
        find_audit(data, pos[0])
        data["audit"] = [x for x in data["audit"] if x["name"] != pos[0]]
        ok("removed audit card for " + pos[0])
        return True

    if cmd == "auditfield":
        need(len(pos) >= 3, "usage: auditfield <name> <field> <value...>")
        au = find_audit(data, pos[0])
        field = pos[1].lower()
        val = " ".join(pos[2:])
        keymap = {"type": "type", "before": "before", "delta": "delta",
                  "priority": "priority", "prioritystatus": "priorityStatus"}
        need(field in keymap, "auditfield field must be: " + ", ".join(keymap))
        if field == "prioritystatus":
            val = vstatus(val)
        au[keymap[field]] = None if val == "-" else val
        ok(pos[0] + " " + keymap[field] + " → " + str(au[keymap[field]]))
        return True

    if cmd == "addstat":
        need(len(pos) >= 5, 'usage: addstat <name> <label> <optimal> <current> <min> [--max N] [--unit %] [--capmax] [--note X]')
        au = find_audit(data, pos[0])
        label = pos[1]
        if any(s["label"] == label for s in au["stats"]):
            die('stat "' + label + '" already on ' + pos[0])
        stat = {"label": label, "optimal": pos[2], "current": pos[3], "min": vfloat(pos[4], "min")}
        if "max" in opts:
            stat["max"] = vfloat(opts["max"], "max")
        if "capmax" in flags:
            stat["capMax"] = True
        if "unit" in opts:
            stat["unit"] = opts["unit"]
        if "note" in opts:
            stat["note"] = opts["note"]
        au["stats"].append(stat)
        ok("added stat " + label + " to " + pos[0] + " (current " + pos[3] + ", min " + pos[4] + ")")
        return True

    if cmd == "stat":
        need(len(pos) >= 3, "usage: stat <name> <label> <current...>")
        au = find_audit(data, pos[0])
        s = find_stat(au, pos[1])
        old = s["current"]
        s["current"] = " ".join(pos[2:])
        ok(pos[0] + " " + pos[1] + ": " + str(old) + " → " + str(s["current"]))
        return True

    if cmd == "statopt":
        need(len(pos) >= 3, "usage: statopt <name> <label> <text...>")
        au = find_audit(data, pos[0])
        s = find_stat(au, pos[1])
        s["optimal"] = " ".join(pos[2:])
        ok(pos[0] + " " + pos[1] + " optimal → " + s["optimal"])
        return True

    if cmd == "statmin":
        need(len(pos) >= 3, "usage: statmin <name> <label> <num>")
        au = find_audit(data, pos[0])
        s = find_stat(au, pos[1])
        s["min"] = vfloat(pos[2], "min")
        ok(pos[0] + " " + pos[1] + " min → " + str(s["min"]))
        return True

    if cmd == "rmstat":
        need(len(pos) >= 2, "usage: rmstat <name> <label>")
        au = find_audit(data, pos[0])
        find_stat(au, pos[1])
        au["stats"] = [s for s in au["stats"] if s["label"] != pos[1]]
        ok("removed stat " + pos[1] + " from " + pos[0])
        return True

    # ── sessions ──
    if cmd == "addsession":
        need(len(pos) >= 3, "usage: addsession <label> <detail> <status>")
        data.setdefault("sessions", []).append(
            {"label": pos[0], "detail": pos[1], "status": vstatus(pos[2])})
        ok("added session: " + pos[0])
        return True

    if cmd == "session":
        need(len(pos) >= 3, "usage: session <idx> <field> <value...>")
        idx = vint(pos[0], "idx")
        sess = data.get("sessions", [])
        need(0 <= idx < len(sess), "session idx must be 0.." + str(len(sess) - 1))
        field = pos[1].lower()
        need(field in ("label", "detail", "status"), "session field: label|detail|status")
        val = " ".join(pos[2:])
        sess[idx][field] = vstatus(val) if field == "status" else val
        ok("session[" + str(idx) + "] " + field + " → " + sess[idx][field])
        return True

    if cmd == "rmsession":
        need(len(pos) >= 1, "usage: rmsession <idx>")
        idx = vint(pos[0], "idx")
        sess = data.get("sessions", [])
        need(0 <= idx < len(sess), "session idx must be 0.." + str(len(sess) - 1))
        removed = sess.pop(idx)
        ok("removed session: " + removed.get("label", ""))
        return True

    # ── pull recommendations ──
    if cmd == "addpull":
        need(len(pos) >= 2, 'usage: addpull <rank> <name> [--priority X] [--why "..."] [--team "..."]')
        rank = vint(pos[0], "rank")
        recs = data.setdefault("pullRecommendations", [])
        if any(int(p.get("rank", -1)) == rank for p in recs):
            die("a pull rec with rank #" + str(rank) + " already exists")
        recs.append({
            "rank": rank, "name": pos[1],
            "priority": opts.get("priority", ""),
            "why": opts.get("why", ""),
            "team": opts.get("team", ""),
        })
        recs.sort(key=lambda p: int(p.get("rank", 0)))
        ok("added pull rec #" + str(rank) + " " + pos[1])
        return True

    if cmd == "setpull":
        need(len(pos) >= 3, "usage: setpull <rank> <field> <value...>")
        p = find_pull(data, vint(pos[0], "rank"))
        field = pos[1].lower()
        need(field in ("rank", "name", "priority", "why", "team"), "setpull field: rank|name|priority|why|team")
        val = " ".join(pos[2:])
        p[field] = vint(val, "rank") if field == "rank" else val
        data["pullRecommendations"].sort(key=lambda x: int(x.get("rank", 0)))
        ok("pull #" + pos[0] + " " + field + " → " + str(p[field]))
        return True

    if cmd == "rmpull":
        need(len(pos) >= 1, "usage: rmpull <rank>")
        rank = vint(pos[0], "rank")
        find_pull(data, rank)
        data["pullRecommendations"] = [p for p in data["pullRecommendations"] if int(p.get("rank", -1)) != rank]
        ok("removed pull rec #" + str(rank))
        return True

    # ── meta ──
    if cmd == "meta":
        need(len(pos) >= 2, "usage: meta <field> <value...>")
        field = pos[0].lower()
        val = " ".join(pos[1:])
        keymap = {"title": "title", "updated": "updated", "maxlevel": "maxLevel",
                  "sessiontitle": "sessionTitle"}
        need(field in keymap, "meta field must be: " + ", ".join(keymap))
        m = data.setdefault("meta", {})
        m[keymap[field]] = vint(val, "maxLevel") if field == "maxlevel" else val
        ok("meta." + keymap[field] + " → " + str(m[keymap[field]]))
        return True

    die('unknown command "' + cmd + '" — run: py zzz_update.py help')


READONLY = {"list", "show", "help"}


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("help", "--help", "-h"):
        print(HELP)
        return

    cmd = argv[0]
    pos, opts, flags = parse_args(argv[1:])
    profile = opts.get("profile", "andres")
    remote_only = "remote-only" in flags
    dry = "dry" in flags

    # load: remote first (source of truth), fall back to local seed
    online = True
    try:
        data = fetch_remote(profile)
        source = "remote"
    except Offline:
        online = False
        data = None
        source = None

    if data is None:
        local = read_local(profile)
        if local is None:
            if not online:
                die("offline and no local seed for profile '" + profile + "'")
            die("no Supabase row for profile '" + profile + "' and no local seed to seed from")
        data = local
        source = "local-seed" if online else "local-offline"
        note("no live row — working from local " + (PROFILE_CONFIG.get(profile) or "?"))

    # ensure shape
    data.setdefault("meta", {})
    data.setdefault("agents", [])
    data.setdefault("audit", [])
    data.setdefault("sessions", [])
    data.setdefault("pullRecommendations", [])

    if cmd == "list":
        cmd_list(data)
        return
    if cmd == "show":
        need(len(pos) >= 1, "usage: show <name>")
        cmd_show(data, pos[0])
        return

    if not online and cmd not in READONLY:
        die("offline — can't save to Supabase. (read-only commands: " + ", ".join(READONLY) + ")")

    mutated = run(cmd, pos, opts, flags, data)
    if not mutated:
        return

    # keep meta honest
    data["meta"]["updated"] = date.today().isoformat()
    data["meta"]["totalAgents"] = len(data["agents"])

    if dry:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        note("--dry: nothing saved")
        return

    save_remote(profile, data)
    ok("saved to Supabase (profile=" + profile + ")")

    if not remote_only:
        if write_local(profile, data):
            ok("mirrored to local " + PROFILE_CONFIG[profile])
        else:
            note("no local mirror for profile '" + profile + "' (remote only)")


if __name__ == "__main__":
    main()
