#!/usr/bin/env python3
"""Ask Xiaomi's update service for the watch firmware URL (read-only).

This reproduces the request Mi Fitness 9.8.348i sends for a native/Bluetooth watch:
``POST https://hlth.io.mi.com/healthapp/device/latest_ver`` with a JSON body built from
``GetLatestVersion`` (``did``, ``model``, ``app_level``, ``fw_ver``, ``platform``) and a
``locale`` header. It prints the JSON the server returns and can download the full image,
verifying the server's MD5. Nothing is written to the watch.

The ``did`` and ``model`` are read from the git-ignored ``secrets/device.md`` unless
overridden. The endpoint may expect the account token the app adds through its OkHttp
client; if it answers 401/403, capture the app's own request instead of guessing.

Usage:
    uv run python scripts/fetch_firmware_url.py --fw-ver 2.2.110
    uv run python scripts/fetch_firmware_url.py --fw-ver 2.2.110 --download
    uv run python scripts/fetch_firmware_url.py --fw-ver 2.2.110 --download secrets/firmware.bin
"""

from __future__ import annotations

import argparse
import hashlib
import json
import locale
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEVICE_FILE = ROOT / "secrets" / "device.md"

UPDATE_URL = "https://hlth.io.mi.com/healthapp/device/latest_ver"
APP_VERSION_CODE = 908348  # Mi Fitness 9.8.348i, the APK analysed in secrets/apk
USER_AGENT = "MiFitness/9.8.348i"

# Key fields of the `LatestVersion` JSON; `fullPackageUrl`/`fullPackageMD5` win over the
# possibly-incremental `url`/`md5`, and `diffUrl` is never used for a full-image download.
SUMMARY_KEYS = (
    "version",
    "url",
    "md5",
    "fullPackageUrl",
    "diffUrl",
    "diffMd5",
    "force",
    "isNeedUpdate",
    "changeLog",
)

DID_RE = re.compile(r"Mi Fitness device id \(did\):\s*(\S+)", re.IGNORECASE)
MODEL_RE = re.compile(r"^-\s*Model:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
CHUNK = 1 << 20


def read_device_facts(path: Path) -> tuple[str | None, str | None]:
    """Return (did, model) from secrets/device.md, or (None, None) if unavailable."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None, None
    did_match = DID_RE.search(text)
    model_match = MODEL_RE.search(text)
    model = None
    if model_match:
        line = model_match.group(1).strip()
        paren = re.search(r"\(([^)]+)\)", line)
        model = paren.group(1) if paren else line.split()[-1]
    return (did_match.group(1) if did_match else None), model


def build_body(did: str, model: str, fw_ver: str, app_level: int, platform: str) -> dict:
    """The `GetLatestVersion` JSON the app sends."""
    return {
        "did": did,
        "model": model,
        "app_level": str(app_level),
        "fw_ver": fw_ver,
        "platform": platform,
    }


def post_json(url: str, body: dict, language: str, timeout: float) -> dict | None:
    """POST *body* and return the decoded JSON, or None after printing the failure."""
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "locale": language,
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        print(f"HTTP {exc.code} from {url}")
        print(detail[:800])
        if exc.code in (401, 403):
            print(
                "\nThe app may add an account token here. Capture its request "
                "(or read the URL from its logs) rather than guessing."
            )
        return None
    except urllib.error.URLError as exc:
        print(f"network error: {exc.reason}")
        return None

    print(f"HTTP {status}, {len(raw)} B")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(raw.decode("utf-8", "replace")[:800])
        return None


def find_version(node: object) -> dict | None:
    """Find the `LatestVersion` object inside an unknown response envelope."""
    if isinstance(node, dict):
        if "version" in node and ("url" in node or "md5" in node):
            return node
        for value in node.values():
            found = find_version(value)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = find_version(value)
            if found:
                return found
    return None


def pick_full_image(info: dict) -> tuple[str | None, str | None]:
    """Return (url, md5) of the full image, preferring the explicit full-package fields."""
    url = info.get("fullPackageUrl") or info.get("url")
    md5 = info.get("md5")
    return url, md5


def download(url: str, destination: Path, timeout: float) -> str:
    """Download *url* to *destination* and return the MD5 of the bytes written."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.md5()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response, destination.open("wb") as fh:
        expected = response.headers.get("Content-Length")
        done = 0
        while chunk := response.read(CHUNK):
            fh.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if expected and done % (16 * CHUNK) == 0:
                print(f"  {done * 100 // int(expected)}% ({done}/{expected})")
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fw-ver", required=True, help="current watch firmware version")
    parser.add_argument("--did", default=None, help="Mi Fitness device id (default: secrets)")
    parser.add_argument("--model", default=None, help="watch model (default: secrets)")
    parser.add_argument("--app-level", type=int, default=APP_VERSION_CODE, help="app versionCode")
    parser.add_argument("--platform", default="prod", help="environment the app sends")
    parser.add_argument("--locale", default=None, help="locale header (default: system)")
    parser.add_argument("--timeout", type=float, default=30.0, help="network timeout, seconds")
    parser.add_argument(
        "--download",
        nargs="?",
        const="",
        default=None,
        metavar="PATH",
        help="download the full image (default: secrets/firmware/<md5>.bin) and verify MD5",
    )
    args = parser.parse_args()

    did, model = read_device_facts(DEVICE_FILE)
    did = args.did or did
    model = args.model or model
    if not did or not model:
        parser.error("did/model missing: pass --did and --model, or fill secrets/device.md")
    language = args.locale or (locale.getlocale()[0] or "en").split("_")[0]

    body = build_body(did, model, args.fw_ver, args.app_level, args.platform)
    print(f"POST {UPDATE_URL}")
    print("body: " + json.dumps(body))

    payload = post_json(UPDATE_URL, body, language, args.timeout)
    if payload is None:
        return 1
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    info = find_version(payload)
    if not info:
        print("\nNo version object with url/md5 found in the response.")
        return 1
    print("\nlatest version:")
    for key in SUMMARY_KEYS:
        if info.get(key) not in (None, ""):
            print(f"  {key}: {info[key]}")

    url, md5 = pick_full_image(info)
    if not url:
        print("\nNo download URL in the response.")
        return 1

    if args.download is None:
        print(f"\nimage URL: {url}")
        return 0

    destination = (
        Path(args.download)
        if args.download
        else ROOT / "secrets" / "firmware" / f"{md5 or 'image'}.bin"
    )
    print(f"\ndownloading {url}\n  -> {destination}")
    try:
        actual = download(url, destination, args.timeout)
    except urllib.error.URLError as exc:
        print(f"download failed: {exc.reason}")
        return 1
    print(f"md5: {actual}")
    if md5 and actual.lower() != md5.lower():
        print(f"MD5 MISMATCH: server said {md5}")
        return 2
    print("MD5 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
