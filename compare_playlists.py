"""
Compare Spotify and YouTube Music CSVs to find songs missing from YT Music.

Usage:
  python compare.py                                   # default file names
  python compare.py --spotify spotify_all_playlists.csv --ytmusic ytmusic_all_playlists.csv
  python compare.py --threshold 80                    # lower fuzzy bar (default 85)
  python compare.py --report                          # print a summary report
"""

import argparse
import csv
import re
from difflib import SequenceMatcher
from pathlib import Path


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_NOISE_PARENS = re.compile(
    r'\(.*?(?:remix|remaster|remastered|live|version|edit|mix|radio|acoustic|'
    r'instrumental|deluxe|bonus|extended|original|reprise).*?\)',
    re.IGNORECASE,
)
_FEAT = re.compile(
    r'\(?(?:feat(?:uring)?\.?|ft\.?)\s[^)]*\)?',
    re.IGNORECASE,
)
_NON_WORD = re.compile(r'[^\w\s]')
_SPACES = re.compile(r'\s+')


def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = _NOISE_PARENS.sub("", text)
    text = _FEAT.sub("", text)
    text = _NON_WORD.sub(" ", text)
    text = _SPACES.sub(" ", text).strip()
    return text


def norm_key(track_name: str, artists: str) -> str:
    """Primary match key: normalized 'title | first_artist'."""
    first_artist = artists.split(",")[0].strip() if artists else ""
    return normalize(track_name) + " | " + normalize(first_artist)


def fuzzy_score(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio() * 100


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------

def load_csv(path: str, name_col: str, artist_col: str, extra_cols: list[str] = None) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            track_name = row.get(name_col, "").strip()
            artists = row.get(artist_col, "").strip()
            entry = {
                "track_name": track_name,
                "artists": artists,
                "norm_key": norm_key(track_name, artists),
                "norm_title": normalize(track_name),
                "_raw": row,
            }
            for col in (extra_cols or []):
                entry[col] = row.get(col, "").strip()
            rows.append(entry)
    return rows


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def build_ytmusic_index(yt_rows: list[dict]) -> tuple[set[str], list[dict]]:
    """Return (exact-key set, list of rows with norm fields for fuzzy)."""
    exact = {r["norm_key"] for r in yt_rows if r["norm_key"]}
    return exact, yt_rows


def is_match(spot_row: dict, yt_exact: set[str], yt_rows: list[dict], threshold: float) -> bool:
    key = spot_row["norm_key"]

    # 1. Exact normalised key match
    if key in yt_exact:
        return True

    # 2. Fuzzy: compare full key string against every YT track
    spot_title = spot_row["norm_title"]
    for yt in yt_rows:
        # Must share at least first artist word to avoid false positives
        spot_artist_word = spot_row["artists"].split()[0].lower() if spot_row["artists"] else ""
        yt_artist_str = yt["artists"].lower()
        if spot_artist_word and spot_artist_word not in yt_artist_str:
            continue

        title_score = fuzzy_score(spot_title, yt["norm_title"])
        if title_score >= threshold:
            return True

    # 3. Fuzzy fallback: title only, stricter threshold
    for yt in yt_rows:
        title_score = fuzzy_score(spot_title, yt["norm_title"])
        if title_score >= min(threshold + 10, 97):
            return True

    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def compare(spotify_path: str, ytmusic_path: str, threshold: float, report: bool):
    print(f"📂  Loading Spotify CSV: {spotify_path}")
    spot_rows = load_csv(spotify_path, "track_name", "artists", ["playlist_name", "album"])
    print(f"    {len(spot_rows)} tracks across {len({r['_raw']['playlist_name'] for r in spot_rows})} playlists")

    print(f"📂  Loading YT Music CSV: {ytmusic_path}")
    yt_rows = load_csv(ytmusic_path, "track_name", "artists")
    print(f"    {len(yt_rows)} tracks")

    yt_exact, yt_all = build_ytmusic_index(yt_rows)

    print(f"\n🔍  Comparing (fuzzy threshold: {threshold}%) …")

    missing = []
    matched = 0

    for i, row in enumerate(spot_rows, 1):
        if i % 100 == 0:
            print(f"    … {i}/{len(spot_rows)}", flush=True)

        if is_match(row, yt_exact, yt_all, threshold):
            matched += 1
        else:
            missing.append({
                "playlist_name": row.get("playlist_name", ""),
                "track_name": row["track_name"],
                "artists": row["artists"],
                "album": row.get("album", ""),
            })

    out_path = "missing_songs.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["playlist_name", "track_name", "artists", "album"])
        writer.writeheader()
        writer.writerows(missing)

    print(f"\n{'─'*55}")
    print(f"  Total Spotify tracks : {len(spot_rows)}")
    print(f"  Matched on YT Music  : {matched}")
    print(f"  Missing              : {len(missing)}")
    print(f"{'─'*55}")
    print(f"\n✅  Missing songs saved → {out_path}")

    if report:
        from collections import Counter
        by_playlist = Counter(r["playlist_name"] for r in missing)
        print("\n📊  Missing by Spotify playlist:")
        for playlist, count in sorted(by_playlist.items(), key=lambda x: -x[1]):
            print(f"     {count:>4}  {playlist}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diff Spotify CSV vs YT Music CSV")
    parser.add_argument("--spotify",   default="spotify_all_playlists.csv")
    parser.add_argument("--ytmusic",   default="ytmusic_all_playlists.csv")
    parser.add_argument("--threshold", type=float, default=85.0,
                        help="Fuzzy match threshold 0-100 (default 85)")
    parser.add_argument("--report",    action="store_true",
                        help="Print breakdown by playlist")
    args = parser.parse_args()

    if not Path(args.spotify).exists():
        print(f"❌  Spotify CSV not found: {args.spotify}")
        raise SystemExit(1)
    if not Path(args.ytmusic).exists():
        print(f"❌  YT Music CSV not found: {args.ytmusic}")
        print("    Run: python fetch_ytmusic.py")
        raise SystemExit(1)

    compare(args.spotify, args.ytmusic, args.threshold, args.report)
