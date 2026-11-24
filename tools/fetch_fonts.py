"""Download the site's Google Fonts once and serve them from our own server (faster, no third-party request).

Usage (needs internet once):   python tools/fetch_fonts.py
Creates static/fonts/*.woff2 and static/css/fonts.css. After it, restart the app: base.html notices fonts.css
and stops loading fonts from Google. Delete static/css/fonts.css to go back.
"""
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS_URL = ("https://fonts.googleapis.com/css2?family=Archivo+Black&family=Space+Mono:wght@400;700&family=Inter:wght@400;500;600"
           "&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"   # asks for woff2
SKIP = ("vietnamese", "greek", "greek-ext", "hebrew", "arabic")       # languages the site does not use
FONTS = ROOT / "static" / "fonts"


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30).read()


def main():
    try:
        css = get(CSS_URL).decode()
    except Exception as exc:
        sys.exit(f"Google Fonts'ga ulanib boʻlmadi ({exc}). Internetni tekshirib qayta urinib koʻring.")
    FONTS.mkdir(parents=True, exist_ok=True)
    out, seen = [], {}
    for subset, block in re.findall(r"/\* ([\w-]+) \*/\s*(@font-face \{.*?\})", css, re.S):
        if subset in SKIP:
            continue
        url = re.search(r"url\((https://[^)]+)\)", block).group(1)
        if url not in seen:
            name = f"{len(seen):02d}-{subset}-{url.rsplit('/', 1)[-1]}"
            (FONTS / name).write_bytes(get(url))
            seen[url] = name
        out.append(f"/* {subset} */\n" + block.replace(url, f"../fonts/{seen[url]}"))
    (ROOT / "static" / "css" / "fonts.css").write_text("\n".join(out) + "\n")
    print(f"Tayyor: {len(seen)} ta shrift fayli, static/css/fonts.css. Ilovani qayta ishga tushiring.")


if __name__ == "__main__":
    main()
