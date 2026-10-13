#!/usr/bin/env python3
"""
serato_tidy.py - find duplicates and organize a Serato DJ music library.

Safe by default: every command is a DRY RUN until you pass --apply.
Every applied change is logged so you can undo it.

Install (optional but strongly recommended, reads ID3/FLAC/M4A tags):
    pip install mutagen

Examples:
    python serato_tidy.py report   ~/Music/DJ --csv library.csv
    python serato_tidy.py dupes    ~/Music/DJ --quarantine ~/Music/_Dupes
    python serato_tidy.py dupes    ~/Music/DJ --quarantine ~/Music/_Dupes --apply
    python serato_tidy.py organize ~/Music/DJ --dest ~/Music/DJ_Sorted \
                          --template "{genre}/{artist}/{year}" --copy --apply
    python serato_tidy.py undo     serato_tidy_log_20261013_120000.json

Serato notes:
  * Cues, loops, beatgrids and BPM are stored INSIDE the audio files (GEOB tags),
    so they travel with the file when moved/copied.
  * Crates and library entries store file PATHS. After MOVING files, open Serato and
    use Files > "Show Missing Files" > "Relocate Lost Files" and point it at the new
    folder. Using --copy leaves the originals (and your crates) untouched.
  * Close Serato before running with --apply. Back up the _Serato_ folder first.
"""
import argparse, csv, hashlib, json, os, re, shutil, sys, unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    import mutagen
except ImportError:
    mutagen = None

AUDIO_EXTS = {".mp3", ".flac", ".wav", ".aif", ".aiff", ".m4a", ".aac", ".ogg", ".alac", ".mp4"}
# higher = better when choosing which duplicate to keep
FORMAT_RANK = {".flac": 5, ".aif": 4, ".aiff": 4, ".wav": 4, ".alac": 4, ".m4a": 3, ".mp3": 2, ".aac": 2, ".ogg": 2, ".mp4": 1}


# ----------------------------------------------------------------- tags -----
def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(feat|ft|featuring)\.?\b.*?(?=[\(\[]|$)", "", s)  # drop featured-artist text
    s = re.sub(r"[^a-z0-9()\[\] ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def first(v):
    if isinstance(v, (list, tuple)):
        v = v[0] if v else ""
    return str(v).strip() if v is not None else ""


def read_tags(path):
    t = {"artist": "", "title": "", "album": "", "genre": "", "year": "", "bpm": "",
         "bitrate": 0, "duration": 0.0}
    if mutagen:
        try:
            f = mutagen.File(path, easy=True)
            if f is not None:
                t["artist"] = first(f.get("artist"))
                t["title"] = first(f.get("title"))
                t["album"] = first(f.get("album"))
                t["genre"] = first(f.get("genre"))
                t["bpm"] = first(f.get("bpm"))
                m = re.search(r"(\d{4})", first(f.get("date")) or first(f.get("originaldate")))
                t["year"] = m.group(1) if m else ""
                if f.info:
                    t["bitrate"] = int(getattr(f.info, "bitrate", 0) or 0)
                    t["duration"] = float(getattr(f.info, "length", 0) or 0)
        except Exception:
            pass
    if not t["artist"] or not t["title"]:  # fall back to "Artist - Title.ext"
        stem = Path(path).stem
        stem = re.sub(r"^\d{1,3}[\s._-]+", "", stem)  # leading track number
        if " - " in stem:
            a, ti = stem.split(" - ", 1)
            t["artist"] = t["artist"] or a.strip()
            t["title"] = t["title"] or ti.strip()
        else:
            t["title"] = t["title"] or stem
    return t


# ------------------------------------------------------------ serato db -----
def parse_chunks(data):
    i, n = 0, len(data)
    while i + 8 <= n:
        tag = data[i:i + 4].decode("ascii", "ignore")
        ln = int.from_bytes(data[i + 4:i + 8], "big")
        yield tag, data[i + 8:i + 8 + ln]
        i += 8 + ln


def load_serato_paths(root):
    """Return set of absolute file paths referenced by Serato's 'database V2', if found."""
    found = set()
    for cand in [Path(root), *Path(root).parents]:
        db = cand / "_Serato_" / "database V2"
        if db.exists():
            base = cand
            try:
                for tag, payload in parse_chunks(db.read_bytes()):
                    if tag != "otrk":
                        continue
                    for st, sp in parse_chunks(payload):
                        if st == "pfil":
                            p = sp.decode("utf-16-be", "ignore").replace("\\", "/")
                            for c in (Path("/") / p, base / p, Path(p)):
                                if c.exists():
                                    found.add(str(c.resolve()))
                                    break
            except Exception as e:
                print(f"! could not parse Serato database: {e}", file=sys.stderr)
            break
    return found


# ----------------------------------------------------------------- scan -----
def scan(roots, serato_paths=None):
    tracks = []
    seen = set()
    for root in roots:
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d != "_Serato_" and not d.startswith(".")]
            for name in fn:
                p = Path(dp) / name
                if p.suffix.lower() not in AUDIO_EXTS or name.startswith("._"):
                    continue
                rp = str(p.resolve())
                if rp in seen:
                    continue
                seen.add(rp)
                t = read_tags(rp)
                t.update(path=rp, ext=p.suffix.lower(), size=p.stat().st_size,
                         in_serato=bool(serato_paths and rp in serato_paths))
                tracks.append(t)
    return tracks


def quality(t):
    # prefer: in Serato library, better format, higher bitrate, more tags filled, bigger file
    tags = sum(bool(t[k]) for k in ("artist", "title", "album", "genre", "year"))
    return (t["in_serato"], FORMAT_RANK.get(t["ext"], 0), t["bitrate"], tags, t["size"])


def sha1(path, chunk=1 << 20):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def find_duplicates(tracks):
    """Returns list of (kind, [tracks sorted best-first])."""
    groups, claimed = [], set()
    by_size = defaultdict(list)
    for t in tracks:
        by_size[t["size"]].append(t)
    for same in by_size.values():
        if len(same) < 2:
            continue
        by_hash = defaultdict(list)
        for t in same:
            by_hash[sha1(t["path"])].append(t)
        for g in by_hash.values():
            if len(g) > 1:
                g.sort(key=quality, reverse=True)
                groups.append(("exact", g))
                claimed.update(t["path"] for t in g)

    # same artist+title (+similar length) in different files/formats.
    # Keeps "(Clean)", "(Dirty)", "(Remix)" etc. in the title key, so edits are NOT flagged.
    by_key = defaultdict(list)
    for t in tracks:
        if t["path"] in claimed or not t["title"]:
            continue
        by_key[(norm(t["artist"]), norm(t["title"]))].append(t)
    for g in by_key.values():
        if len(g) < 2:
            continue
        g.sort(key=lambda x: x["duration"])
        cluster = [g[0]]
        for t in g[1:]:
            if abs(t["duration"] - cluster[-1]["duration"]) <= 3:
                cluster.append(t)
            else:
                if len(cluster) > 1:
                    groups.append(("likely", sorted(cluster, key=quality, reverse=True)))
                cluster = [t]
        if len(cluster) > 1:
            groups.append(("likely", sorted(cluster, key=quality, reverse=True)))
    return groups


# ------------------------------------------------------------- helpers -----
def safe(s, default="Unknown"):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (s or "").strip()).strip(". ")
    return s[:80] or default


_planned = set()


def unique_path(p):
    """Pick a destination that doesn't exist on disk and isn't already planned this run."""
    p = Path(p)
    c, i = p, 0
    while c.exists() or str(c) in _planned:
        i += 1
        c = p.with_name(f"{p.stem} ({i}){p.suffix}")
    _planned.add(str(c))
    return c


def apply_ops(ops, apply, label):
    """ops: list of (action, src, dst). action in move|copy"""
    log = []
    for action, src, dst in ops:
        print(f"  {action.upper():4} {src}\n    -> {dst}")
        if apply:
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            (shutil.copy2 if action == "copy" else shutil.move)(src, dst)
            log.append({"action": action, "src": src, "dst": str(dst)})
    if apply and log:
        name = f"serato_tidy_log_{datetime.now():%Y%m%d_%H%M%S}.json"
        Path(name).write_text(json.dumps(log, indent=2))
        print(f"\n{label}: {len(log)} file(s) processed. Undo log: {name}")
    elif not apply:
        print(f"\nDRY RUN - {len(ops)} operation(s) planned. Re-run with --apply to execute.")


def load(args):
    roots = [str(Path(r).expanduser()) for r in args.folders]
    sp = load_serato_paths(roots[0]) if not args.no_serato_db else set()
    if sp:
        print(f"Serato library found: {len(sp)} tracks referenced.")
    if not mutagen:
        print("! mutagen not installed - falling back to filenames only (pip install mutagen)")
    tracks = scan(roots, sp)
    print(f"Scanned {len(tracks)} audio files.\n")
    return tracks


# ------------------------------------------------------------- commands -----
def cmd_report(a):
    tracks = load(a)
    missing = lambda k: sum(not t[k] for t in tracks)
    print(f"Missing artist: {missing('artist')} | genre: {missing('genre')} | year: {missing('year')}")
    exts = defaultdict(int)
    for t in tracks:
        exts[t["ext"]] += 1
    print("Formats:", dict(sorted(exts.items(), key=lambda x: -x[1])))
    groups = find_duplicates(tracks)
    print(f"Duplicate groups: {sum(k=='exact' for k,_ in groups)} exact, {sum(k=='likely' for k,_ in groups)} likely")
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["artist", "title", "album", "genre", "year", "bpm", "ext",
                                              "bitrate", "duration", "size", "in_serato", "path"])
            w.writeheader()
            for t in sorted(tracks, key=lambda x: (x["artist"].lower(), x["title"].lower())):
                w.writerow({k: t[k] for k in w.fieldnames})
        print(f"Wrote {a.csv}")


def cmd_dupes(a):
    tracks = load(a)
    groups = find_duplicates(tracks)
    if not groups:
        print("No duplicates found.")
        return
    qdir = Path(a.quarantine).expanduser()
    ops = []
    for kind, g in groups:
        if kind == "likely" and not a.include_likely:
            print(f"[likely] {g[0]['artist']} - {g[0]['title']}  (review only; use --include-likely to quarantine)")
        else:
            print(f"[{kind}] {g[0]['artist']} - {g[0]['title']}")
        keep = g[0]
        print(f"  KEEP  {keep['path']}  [{keep['ext']} {keep['bitrate']//1000}k{' | in Serato' if keep['in_serato'] else ''}]")
        for t in g[1:]:
            print(f"  dupe  {t['path']}  [{t['ext']} {t['bitrate']//1000}k{' | in Serato' if t['in_serato'] else ''}]")
            if kind == "exact" or a.include_likely:
                ops.append(("move", t["path"], str(unique_path(qdir / Path(t["path"]).name))))
    print()
    apply_ops(ops, a.apply, "Quarantined")
    if a.apply:
        print("Nothing is deleted - review the quarantine folder, then delete it yourself when happy.")


def cmd_organize(a):
    tracks = load(a)
    dest = Path(a.dest).expanduser()
    ops = []
    for t in tracks:
        year = t["year"] or "Unknown Year"
        decade = f"{year[:3]}0s" if t["year"] else "Unknown Decade"
        fields = {"artist": safe(t["artist"], "Unknown Artist"), "genre": safe(t["genre"], "Unknown Genre"),
                  "year": safe(year), "decade": decade, "album": safe(t["album"], "Unknown Album"),
                  "bpm": safe(str(round(float(t["bpm"]))) if re.match(r"^\d+(\.\d+)?$", t["bpm"] or "") else "Unknown BPM")}
        sub = a.template.format(**fields)
        name = f"{safe(t['artist'], 'Unknown Artist')} - {safe(t['title'])}{t['ext']}" if t["artist"] else f"{safe(t['title'])}{t['ext']}"
        target = dest / sub / name
        if Path(t["path"]) == target:
            continue
        ops.append(("copy" if a.copy else "move", t["path"], str(unique_path(target))))
    apply_ops(ops, a.apply, "Organized")
    if a.apply and not a.copy:
        print("Files were MOVED: in Serato use 'Relocate Lost Files' on the new folder.")


def cmd_undo(a):
    log = json.loads(Path(a.log).read_text())
    for e in reversed(log):
        if e["action"] == "move" and Path(e["dst"]).exists():
            Path(e["src"]).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(e["dst"], e["src"])
            print(f"restored {e['src']}")
        elif e["action"] == "copy" and Path(e["dst"]).exists():
            os.remove(e["dst"])
            print(f"removed copy {e['dst']}")


def main():
    p = argparse.ArgumentParser(description="Analyze, dedupe and organize a Serato DJ library.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("folders", nargs="+", help="music folder(s) to scan")
        sp.add_argument("--no-serato-db", action="store_true", help="don't read Serato's database V2")
        sp.add_argument("--apply", action="store_true", help="actually do it (default is dry run)")

    r = sub.add_parser("report"); common(r); r.add_argument("--csv"); r.set_defaults(fn=cmd_report)
    d = sub.add_parser("dupes"); common(d)
    d.add_argument("--quarantine", required=True, help="folder to move duplicates into")
    d.add_argument("--include-likely", action="store_true", help="also quarantine same artist/title files (different formats/rips)")
    d.set_defaults(fn=cmd_dupes)
    o = sub.add_parser("organize"); common(o)
    o.add_argument("--dest", required=True)
    o.add_argument("--template", default="{genre}/{artist}",
                   help="fields: {genre} {artist} {year} {decade} {album} {bpm}. e.g. '{decade}/{genre}/{artist}'")
    o.add_argument("--copy", action="store_true", help="copy instead of move (safest for Serato crates)")
    o.set_defaults(fn=cmd_organize)
    u = sub.add_parser("undo"); u.add_argument("log"); u.set_defaults(fn=cmd_undo)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
