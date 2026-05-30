"""
YouTube Music Playlist Importer
================================
Imports songs from a Spotify-exported CSV into YouTube Music.

The CSV 'status' column is the single source of truth:
  Pending   → not yet processed
  Completed → successfully added to YT Music playlist
  NotFound  → could not be found on YT Music

USAGE:
  python ytmusic.py --test                        # check auth
  python ytmusic.py --csv missing_songs.csv       # run import
  python ytmusic.py --csv missing_songs.csv --delay 1.5  # if rate-limited

AUTH EXPIRY:
  Sessions last ~1 hour. When it expires the script stops cleanly.
    1. Paste fresh headers into headers.txt
    2. python refresh_auth.py
    3. Re-run — picks up exactly where it left off (status column tracks progress)
"""

import argparse
import csv
import json
import time
import sys
from collections import Counter
from pathlib import Path

BROWSER_JSON     = Path(__file__).parent / "browser.json"
PROGRESS_FILE    = "import_progress.json"   # stores playlist_id only
NOT_FOUND_FILE   = "not_found.csv"
NOT_FOUND_FIELDS = ["track", "artist", "reason"]
AUTH_FAIL_THRESHOLD = 3


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_ytmusic():
    from ytmusicapi import YTMusic
    return YTMusic(str(BROWSER_JSON))


def is_auth_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in (
        "401", "403", "unauthorized", "unauthenticated",
        "authentication", "forbidden", "invalid credentials",
    ))


def _print_refresh_hint():
    print()
    print("  ┌─ SESSION EXPIRED ──────────────────────────────────────────┐")
    print("  │  1. Paste fresh Chrome DevTools headers into headers.txt   │")
    print("  │  2. Run:  python refresh_auth.py                           │")
    print("  │  3. Re-run:  python ytmusic.py --csv missing_songs.csv     │")
    print("  │     (CSV status column tracks progress — safe to re-run)   │")
    print("  └────────────────────────────────────────────────────────────┘")


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _read_csv(csv_path: str) -> tuple[list[dict], list[str]]:
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    fieldnames = list(rows[0].keys()) if rows else []
    return rows, fieldnames


def _write_csv(csv_path: str, rows: list[dict], fieldnames: list[str]):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _mark_song(csv_path: str, track: str, artist: str, new_status: str):
    """Update the status of a single Pending row in the CSV, write it back."""
    rows, fieldnames = _read_csv(csv_path)
    for row in rows:
        if (row["track_name"].strip() == track
                and row["artists"].strip() == artist
                and row.get("status", "").strip().lower() == "pending"):
            row["status"] = new_status
            break
    _write_csv(csv_path, rows, fieldnames)


# ── not_found.csv — written per-song so Ctrl+C never loses data ──────────────

def _init_not_found():
    with open(NOT_FOUND_FILE, "w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=NOT_FOUND_FIELDS).writeheader()


def _append_not_found(track: str, artist: str, reason: str):
    with open(NOT_FOUND_FILE, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=NOT_FOUND_FIELDS).writerow(
            {"track": track, "artist": artist, "reason": reason}
        )


# ── Progress (playlist ID only) ───────────────────────────────────────────────

def load_progress() -> dict:
    if Path(PROGRESS_FILE).exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {}


def save_progress(progress: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


# ── Search ────────────────────────────────────────────────────────────────────

def search_song(ytmusic, track_name: str, artist: str, album: str = None):
    """
    Returns (video_id, auth_error):
      (video_id, None) → found
      (None, None)     → genuinely not on YT Music
      (None, exc)      → auth failure — caller should stop
    """
    queries = [
        f"{track_name} {artist}",
        f"{track_name} {artist} {album}" if album else None,
        track_name,
    ]
    for query in queries:
        if not query:
            continue
        try:
            results = ytmusic.search(query, filter="songs", limit=3)
            if results:
                return results[0].get("videoId"), None
        except Exception as e:
            if is_auth_error(e):
                return None, e
            time.sleep(1)
    return None, None


# ── Commands ──────────────────────────────────────────────────────────────────

def test_auth():
    print("🔄  Testing authentication...")
    try:
        yt = get_ytmusic()
        playlists = yt.get_library_playlists(limit=5)
        print(f"✅  Connected! Found {len(playlists)} playlists:")
        for p in playlists:
            print(f"      - {p['title']}")
    except Exception as e:
        print(f"❌  Auth failed: {e}")
        _print_refresh_hint()
        sys.exit(1)


def import_playlist(csv_path: str, delay: float = 0.5, limit: int = None):
    ytmusic = get_ytmusic()
    print("✅  Authenticated.\n")

    # Status column is the source of truth — only process Pending rows
    all_rows, fieldnames = _read_csv(csv_path)
    pending = [r for r in all_rows if r.get("status", "Pending").strip().lower() == "pending"]

    if not pending:
        print("❌  No pending songs in CSV.")
        sys.exit(1)

    rows = pending[:limit] if limit else pending
    print(f"📂  {len(rows)} songs to process  (total pending in CSV: {len(pending)}).")

    # Playlist ID lives in progress.json (the only thing left there)
    progress      = load_progress()
    PLAYLIST_NAME = "Spotify Migrated"
    pid_key       = f"playlist_id_{PLAYLIST_NAME}"
    playlist_id   = progress.get(pid_key)

    if not playlist_id:
        try:
            playlist_id = ytmusic.create_playlist(
                title=PLAYLIST_NAME,
                description="Migrated from Spotify"
            )
            progress[pid_key] = playlist_id
            save_progress(progress)
            print(f"✅  Created playlist '{PLAYLIST_NAME}' (ID: {playlist_id})")
        except Exception as e:
            print(f"❌  Could not create playlist: {e}")
            if is_auth_error(e):
                _print_refresh_hint()
            sys.exit(1)
    else:
        print(f"♻️   Resuming existing playlist '{PLAYLIST_NAME}' (ID: {playlist_id})")

    print(f"\n{'─'*55}")
    print(f"  ▶  {len(rows)} songs to add this session")
    print(f"{'─'*55}")

    _init_not_found()
    added = not_found_count = consecutive_failures = 0

    for i, song in enumerate(rows):
        track  = song.get("track_name", "").strip()
        artist = song.get("artists",    "").strip()
        album  = song.get("album",      "").strip()

        print(f"  [{i+1:>4}/{len(rows)}] {track[:45]:<45} — {artist[:25]}", end="", flush=True)

        video_id, auth_err = search_song(ytmusic, track, artist, album)

        if auth_err:
            print("  🔒 auth expired")
            consecutive_failures += 1

        elif video_id:
            try:
                ytmusic.add_playlist_items(playlist_id, [video_id])
                print("  ✅")
                added += 1
                consecutive_failures = 0
                _mark_song(csv_path, track, artist, "Completed")   # ← written to CSV immediately
            except Exception as e:
                if is_auth_error(e):
                    print("  🔒 auth expired")
                    consecutive_failures += 1
                else:
                    print(f"  ⚠️  {e}")
                    consecutive_failures = 0
                    _append_not_found(track, artist, str(e))
                    not_found_count += 1

        else:
            print("  ❌ not found")
            consecutive_failures = 0
            _mark_song(csv_path, track, artist, "NotFound")         # ← written to CSV immediately
            _append_not_found(track, artist, "not on YTMusic")
            not_found_count += 1

        if consecutive_failures >= AUTH_FAIL_THRESHOLD:
            print(f"\n  ⚠️  {AUTH_FAIL_THRESHOLD} consecutive auth failures — session has expired.")
            _print_refresh_hint()
            break

        time.sleep(delay)

    # Final counts straight from the CSV
    final_rows, _ = _read_csv(csv_path)
    counts = Counter(r["status"] for r in final_rows)
    print(f"\n  📊  Added this run:    {added}")
    print(f"       Not found:        {not_found_count}  (→ {NOT_FOUND_FILE})")
    print(f"       Total completed:  {counts.get('Completed', 0)} / {len(final_rows)}")
    print(f"       Still pending:    {counts.get('Pending', 0)}")

    if counts.get("Pending", 0) == 0:
        print("\n🎉  All songs processed!\n")
    elif consecutive_failures < AUTH_FAIL_THRESHOLD:
        print("\n  ⏸   Re-run to continue.\n")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not BROWSER_JSON.exists():
        print("❌  browser.json not found.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Import Spotify CSV → YouTube Music")
    parser.add_argument("--test",  action="store_true", help="Test authentication")
    parser.add_argument("--csv",   type=str,            help="Path to CSV file")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Seconds between requests (default 0.5)")
    parser.add_argument("--limit", type=int,   default=None,
                        help="Only process first N songs")
    args = parser.parse_args()

    if args.test:
        test_auth()
    elif args.csv:
        import_playlist(args.csv, delay=args.delay, limit=args.limit)
    else:
        print(__doc__)
