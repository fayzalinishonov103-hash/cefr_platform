"""Build static/css/tailwind.css so the site no longer loads Tailwind from a CDN (faster, works offline).

Usage (needs internet once, to download the official standalone Tailwind program):
    python tools/build_css.py            # downloads tools/bin/tailwindcss(.exe) the first time, then builds
After it, restart the app: base.html notices the file and stops using the CDN automatically.
Re-run it whenever you add new Tailwind classes to templates.
Delete static/css/tailwind.css to go back to the CDN.
"""
import os
import platform
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

VERSION = "3.4.17"          # must match the CDN version used before
ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "tools" / "bin"


def asset_name():
    system, machine = platform.system().lower(), platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if system == "windows":
        return "tailwindcss-windows-x64.exe"
    if system == "darwin":
        return "tailwindcss-macos-arm64" if arm else "tailwindcss-macos-x64"
    return "tailwindcss-linux-arm64" if arm else "tailwindcss-linux-x64"


def ensure_binary():
    name = asset_name()
    target = BIN_DIR / name
    if target.exists():
        return target
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/tailwindlabs/tailwindcss/releases/download/v{VERSION}/{name}"
    print(f"Yuklab olinmoqda: {url}")
    try:
        urllib.request.urlretrieve(url, target)
    except Exception as exc:                                   # no internet, proxy, GitHub blocked ...
        target.unlink(missing_ok=True)
        sys.exit(f"Yuklab boʻlmadi ({exc}).\nQoʻlda: {url} ni tools/bin/ papkasiga {name} nomi bilan saqlang va qayta ishga tushiring.")
    target.chmod(target.stat().st_mode | stat.S_IEXEC)
    return target


def main():
    binary = ensure_binary()
    out = ROOT / "static" / "css" / "tailwind.css"
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(binary), "-c", str(ROOT / "tailwind.config.js"), "-i", str(ROOT / "tools" / "tailwind-input.css"), "-o", str(out), "--minify"]
    print("Yigʻilmoqda ...")
    subprocess.run(cmd, cwd=ROOT, check=True)
    print(f"Tayyor: {out} ({out.stat().st_size // 1024} KB). Ilovani qayta ishga tushiring.")


if __name__ == "__main__":
    main()
