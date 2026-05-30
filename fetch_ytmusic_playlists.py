"""
Fetch all YouTube Music playlist tracks into a CSV.

Usage:
  python fetch_ytmusic.py              # fetches all playlists
  python fetch_ytmusic.py --test       # test auth only
  python fetch_ytmusic.py --liked      # also include Liked Music
"""

import argparse
import csv
import sys
import time
from pathlib import Path

# BROWSER_JSON = Path(__file__).parent / "browser.json" #Not needed anymore
OUTPUT_FILE = "ytmusic_all_playlists.csv"
FIELDNAMES = ["playlist_name", "track_name", "artists", "album", "duration_s", "video_id"]


def get_ytmusic():
    from ytmusicapi import YTMusic
    return YTMusic(str(Path(__file__).parent / "browser.json"))


def test_auth():
    ytmusic = get_ytmusic()
    # print(ytmusic)
    print("🔄  Testing authentication...")
    playlists = ytmusic.get_library_playlists(limit=5)
    # print(playlists)
    print(f"✅  Connected! Found {len(playlists)} playlists:")
    for p in playlists:
        print(f"      - {p['title']}  ({p.get('count', '?')} tracks)")


def extract_track(playlist_name, item):
    title = item.get("title", "").strip()
    artists = ", ".join(a["name"] for a in item.get("artists") or [] if a.get("name"))
    album_obj = item.get("album") or {}
    album = album_obj.get("name", "").strip() if isinstance(album_obj, dict) else ""
    duration_s = item.get("duration_seconds") or 0
    video_id = item.get("videoId", "")
    return {
        "playlist_name": playlist_name,
        "track_name": title,
        "artists": artists,
        "album": album,
        "duration_s": duration_s,
        "video_id": video_id,
    }


def fetch_playlist_tracks(ytmusic, playlist_id, playlist_name):
    if playlist_name != "Episodes for Later":    #Exluded a playlist of mine
        try:
            data = ytmusic.get_playlist(playlist_id, limit=None)
            tracks = data.get("tracks") or []
            rows = []
            for item in tracks:
                if not item:
                    continue
                rows.append(extract_track(playlist_name, item))
            return rows
        except Exception as e:
            print(f"  ⚠️  Error fetching '{playlist_name}': {e}")
            return []
    else:
        return []


def fetch_liked_tracks(ytmusic):
    try:
        tracks = ytmusic.get_liked_songs(limit=None)
        rows = []
        for item in (tracks.get("tracks") or []):
            if not item:
                continue
            rows.append(extract_track("Liked Music", item))
        return rows
    except Exception as e:
        print(f"  ⚠️  Error fetching Liked Music: {e}")
        return []


def fetch_all(include_liked=False):
    ytmusic = get_ytmusic()
    print("✅  Authenticated.\n")

    playlists = ytmusic.get_library_playlists(limit=None)
    print(f"📋  Found {len(playlists)} playlists.")

    all_rows = []

    if include_liked:
        print("  ↳  Liked Music ...", end=" ", flush=True)
        rows = fetch_liked_tracks(ytmusic)
        print(f"{len(rows)} tracks")
        all_rows.extend(rows)
        time.sleep(0.3)

    for playlist in playlists:
        name = playlist.get("title", "Untitled")
        pid = playlist.get("playlistId", "")
        count = playlist.get("count", "?")
        print(f"  ↳  {name}  ({count} tracks) ...", end=" ", flush=True)
        rows = fetch_playlist_tracks(ytmusic, pid, name)
        print(f"{len(rows)} fetched")
        all_rows.extend(rows)
        time.sleep(0.3)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n✅  Saved {len(all_rows)} tracks → {OUTPUT_FILE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch YouTube Music playlists → CSV")
    parser.add_argument("--test",  action="store_true", help="Test auth only")
    parser.add_argument("--liked", action="store_true", help="Include Liked Music")
    args = parser.parse_args()

    if args.test:
        test_auth()
    else:
        fetch_all(include_liked=args.liked)
