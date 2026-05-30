import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import pandas as pd
import time

load_dotenv()

# ==============================
# 🔐 CONFIG
# ==============================
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

SCOPE = "playlist-read-private playlist-read-collaborative"

# ==============================
# 🔌 AUTHENTICATION
# ==============================
sp = spotipy.Spotify(
    auth_manager=SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE
    )
)

# ==============================
# 📥 FETCH PLAYLISTS
# ==============================
playlists = []
results = sp.current_user_playlists(limit=50)

while results:
    playlists.extend(results['items'])
    if results['next']:
        results = sp.next(results)
    else:
        break

print(f"Total playlists found: {len(playlists)}")
print(f"Playlists found: {playlists}")
# ==============================
# 📊 EXTRACT TRACKS
# ==============================
all_tracks = []

for playlist in playlists:
    playlist_name = playlist['name']
    playlist_id = playlist['id']

    print(f"Processing playlist: {playlist_name}")

    try:
        results = sp.playlist_items(playlist_id, additional_types=['track'])

        while results:
            for item in results['items']:
                track = item.get('item')

                if not track:
                    continue

                if track.get('type') != 'track':
                    continue

                track_data = {
                    "playlist_name": playlist_name,
                    "track_name": track.get('name'),
                    "artists": ", ".join([artist['name'] for artist in track.get('artists', [])]),
                    "album": track.get('album', {}).get('name'),
                    "duration_ms": track.get('duration_ms'),
                    "spotify_id": track.get('id'),
                    "spotify_url": track.get('external_urls', {}).get('spotify')
                }

                all_tracks.append(track_data)

            if results['next']:
                results = sp.next(results)
            else:
                break

    except Exception as e:
        print(f"❌ Skipping playlist due to error: {playlist_name}")
        print(e)
        continue
# ==============================
# 💾 SAVE TO CSV
# ==============================
df = pd.DataFrame(all_tracks)

print(df.head())

df.to_csv("spotify_all_playlists.csv", index=False)

print("✅ Done! Data saved to spotify_all_playlists.csv")