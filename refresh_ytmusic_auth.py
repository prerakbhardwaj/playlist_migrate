"""
Update browser.json from a Chrome DevTools header paste.

RECOMMENDED USAGE (avoids terminal paste issues):
  1. Open Chrome → YouTube Music → any page
  2. DevTools (F12) → Network tab → click any request
  3. Right-click → Copy → Copy request headers
  4. Open TextEdit / any text editor, paste, save as  headers.txt
     (anywhere is fine, e.g. your Desktop)
  5. python refresh_auth.py ~/Desktop/headers.txt

STDIN FALLBACK:
  python refresh_auth.py
  (paste headers, then press Ctrl+D to finish — NOT Enter)

What it updates:  authorization, cookie, x-goog-visitor-id,
                  x-goog-authuser, x-youtube-client-version
What it fixes:    removes content-encoding, strips br/zstd from accept-encoding
"""

import json
import sys
from pathlib import Path

BROWSER_JSON = Path(__file__).parent / "browser.json"

UPDATABLE = {
    "authorization",
    "cookie",
    "x-goog-visitor-id",
    "x-goog-authuser",
    "x-youtube-client-version",
    "x-youtube-client-name",
    "x-browser-validation",
    "x-browser-year",
    "x-client-data",
    "referer",
    "user-agent",
}


def parse_headers(raw: str) -> dict:
    """
    Handles two Chrome DevTools copy formats:

    Format A — "key: value" on one line (Copy as cURL / raw):
        authorization: SAPISIDHASH ...
        cookie: HSID=...

    Format B — alternating lines (Names + Values columns):
        authorization
        SAPISIDHASH ...
        cookie
        HSID=...
    """
    lines = [l.strip() for l in raw.splitlines() if l.strip()]

    # Detect format: if fewer than half of non-pseudo lines contain ":",
    # we're in alternating (name / value) format.
    non_pseudo = [l for l in lines if not l.startswith(":")]
    colon_count = sum(1 for l in non_pseudo if ":" in l)
    is_alternating = bool(non_pseudo) and colon_count < len(non_pseudo) // 2

    headers = {}

    if is_alternating:
        # Lines come in pairs: name then value. Pseudo-headers (:authority etc.)
        # also come in pairs — skip both lines of each pair.
        i = 0
        while i < len(lines):
            key_line = lines[i]
            val_line = lines[i + 1] if i + 1 < len(lines) else ""
            i += 2
            if key_line.startswith(":"):   # HTTP/2 pseudo-header — skip
                continue
            key = key_line.lower()
            val = val_line
            if key and val:
                headers[key] = val
    else:
        for line in lines:
            if line.startswith(":"):
                continue
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip().lower()
            val = val.strip()
            if key and val:
                headers[key] = val

    return headers


def update(raw: str):
    parsed = parse_headers(raw)

    if not parsed.get("authorization", "").startswith("SAPISIDHASH"):
        print("❌  Could not find a valid 'authorization: SAPISIDHASH ...' line.")
        print("    Make sure you pasted the full Chrome DevTools request headers.")
        sys.exit(1)

    data = json.loads(BROWSER_JSON.read_text())

    updated = []
    for key in UPDATABLE:
        if key in parsed:
            data[key] = parsed[key]
            updated.append(key)

    # Always fix these regardless of what was pasted
    data.pop("content-encoding", None)
    data["accept-encoding"] = "gzip, deflate"

    BROWSER_JSON.write_text(json.dumps(data, indent=4))

    print(f"✅  browser.json updated.")
    print(f"    Fields refreshed: {', '.join(updated)}")
    print(f"    accept-encoding locked to: gzip, deflate  (br/zstd removed)")
    print(f"    content-encoding: removed if present")
    print(f"\n    New auth prefix: {data['authorization'][:60]}...")


if __name__ == "__main__":
    header_file = Path(__file__).parent / "headers.txt"
    if not header_file.exists():
        print(f"❌  headers.txt not found in {Path(__file__).parent}")
        print("    Paste your Chrome DevTools headers into headers.txt and save it there.")
        sys.exit(1)
    raw = header_file.read_text(encoding="utf-8")
    print(f"📄  Reading headers from '{header_file.name}' ...")
    update(raw)
