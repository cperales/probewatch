#!/usr/bin/env python3
"""Ask Xiaomi's update service for the watch firmware URL (read-only).

This reproduces the request Mi Fitness 9.8.348i sends for a native/Bluetooth watch:
``POST https://hlth.io.mi.com/healthapp/device/latest_ver`` with the ``GetLatestVersion``
JSON (``did``, ``model``, ``platform="android"``, ``app_level``, ``fw_ver``,
``channel="prod"``) and a ``locale`` header. It prints the JSON the server returns and can
download the full image, verifying the server's MD5. Nothing is written to the watch.

Auth: the endpoint requires the Mi Fitness account cookies for the ``miothealth`` service.
``AccountModule.provideCookie()`` builds ``cUserId=<...>; serviceToken=<...>`` and
``VerifyToken`` (login policy 2 = necessary) refuses to send without them. Put that pair in
``secrets/miot_health_cookie.txt`` (git-ignored) or pass ``--cookie``. Without a logged-in
account the server answers ``HTTP 401 {"code":2,"message":"auth err"}``.

Cheaper alternative: let Mi Fitness download an update on the phone. ``getFirmwareFile()``
writes it to ``/sdcard/Android/data/com.xiaomi.wearable/files/Download/<model>/<md5>``, so
``adb pull`` gets the image with no cookie involved.

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
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEVICE_FILE = ROOT / "secrets" / "device.md"
DEFAULT_COOKIE_FILE = ROOT / "secrets" / "miot_health_cookie.txt"

UPDATE_URL = "https://hlth.io.mi.com/healthapp/device/latest_ver"
APP_VERSION_CODE = 908348  # Mi Fitness 9.8.348i, the APK analysed in secrets/apk
USER_AGENT = "MiFitness/9.8.348i"
SID = "miothealth"

AUTH_HELP = f"""\
The health API needs the Mi Fitness account cookie for service '{SID}':
    cUserId=<...>; serviceToken=<...>
The app builds exactly that pair in AccountModule.provideCookie() and refuses to send a
request without it (VerifyToken, login policy 2). There is no way to derive it from the
device id.

Put the pair in {DEFAULT_COOKIE_FILE.relative_to(ROOT)} (git-ignored), one per line or as
'k=v; k=v', or pass --cookie / --c-user-id + --service-token. With the cookie the script
sends the app's request unchanged.

No cookie yet? Let Mi Fitness download the update on the phone instead: the image lands in
    /sdcard/Android/data/com.xiaomi.wearable/files/Download/<model>/<md5>
and 'adb pull' copies it out without touching the API.
"""

# Key fields of the `LatestVersion` JSON; `fullPackageUrl` wins over the possibly
# incremental `url`, and `diffUrl` is never used for a full-image download.
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


def build_body(
    did: str, model: str, fw_ver: str, app_level: int, platform: str, channel: str
) -> dict:
    """The `GetLatestVersion` JSON the app sends (`platform=android`, `channel=prod`)."""
    return {
        "did": did,
        "model": model,
        "platform": platform,
        "app_level": str(app_level),
        "fw_ver": fw_ver,
        "channel": channel,
    }


def read_cookie_file(path: Path) -> str | None:
    """Read `k=v; k=v` (one line or one per line) and normalise to one Cookie value."""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    if text.lower().startswith("cookie:"):
        text = text.split(":", 1)[1].strip()
    parts = [part.strip() for part in text.replace("\n", ";").split(";") if part.strip()]
    return "; ".join(parts) if parts else None


def load_cookie(args: argparse.Namespace) -> str | None:
    """Resolve the account cookie from flags, file, or environment, in that order."""
    if args.cookie:
        return read_cookie_file_text(args.cookie)
    if args.service_token or args.c_user_id:
        if not (args.service_token and args.c_user_id):
            raise SystemExit("--service-token and --c-user-id must be given together")
        return f"cUserId={args.c_user_id}; serviceToken={args.service_token}"
    path = Path(args.cookie_file) if args.cookie_file else DEFAULT_COOKIE_FILE
    cookie = read_cookie_file(path)
    if cookie:
        return cookie
    env = os.environ.get("MIOT_HEALTH_COOKIE")
    return env.strip() if env else None


def read_cookie_file_text(text: str) -> str:
    """Accept a literal cookie string; strip a leading `Cookie:` if present."""
    if text.lower().startswith("cookie:"):
        text = text.split(":", 1)[1].strip()
    return text


def with_locale(cookie: str, language: str) -> str:
    """The app appends `locale=` to the token cookie (ParameterInterceptor)."""
    if "locale=" in cookie:
        return cookie
    return f"{cookie}; locale={language}"


def post_json(
    url: str, body: dict, language: str, cookie: str | None, timeout: float
) -> dict | None:
    """POST *body* and return the decoded JSON, or None after printing the failure."""
    data = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "locale": language,
        "User-Agent": USER_AGENT,
    }
    if cookie:
        headers["Cookie"] = cookie
    request = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        print(f"HTTP {exc.code} from {url}")
        print(detail[:800])
        if exc.code in (401, 403):
            print("\n" + AUTH_HELP)
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
    """Return (url, md5) of the full image, preferring the explicit full-package URL."""
    return info.get("fullPackageUrl") or info.get("url"), info.get("md5")


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


def print_curl(body: dict, language: str) -> None:
    """Print a copy-paste curl using $MIOT_HEALTH_COOKIE, never the secret itself."""
    payload = json.dumps(body)
    print("\ncurl equivalent:")
    print(
        f"curl -sS '{UPDATE_URL}' "
        f"-H 'Content-Type: application/json' -H 'locale: {language}' "
        f"-H \"Cookie: $MIOT_HEALTH_COOKIE\" --data '{payload}'"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fw-ver", required=True, help="current watch firmware version")
    parser.add_argument("--did", default=None, help="Mi Fitness device id (default: secrets)")
    parser.add_argument("--model", default=None, help="watch model (default: secrets)")
    parser.add_argument("--app-level", type=int, default=APP_VERSION_CODE, help="app versionCode")
    parser.add_argument("--platform", default="android", help="platform the app sends")
    parser.add_argument("--channel", default="prod", help="update channel (the app uses prod)")
    parser.add_argument("--locale", default=None, help="locale header (default: system)")
    parser.add_argument(
        "--cookie", default=None, help="account cookie: 'cUserId=...; serviceToken=...'"
    )
    parser.add_argument(
        "--cookie-file",
        default=None,
        help=f"file with the cookie (default: {DEFAULT_COOKIE_FILE.relative_to(ROOT)})",
    )
    parser.add_argument("--c-user-id", default=None, help="account cUserId (with --service-token)")
    parser.add_argument("--service-token", default=None, help="miothealth serviceToken")
    parser.add_argument("--timeout", type=float, default=30.0, help="network timeout, seconds")
    parser.add_argument(
        "--print-curl", action="store_true", help="print the equivalent curl and exit"
    )
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

    body = build_body(did, model, args.fw_ver, args.app_level, args.platform, args.channel)
    if args.print_curl:
        print_curl(body, language)
        return 0

    cookie = load_cookie(args)
    if cookie:
        cookie = with_locale(cookie, language)
    else:
        print("warning: no account cookie configured; the server will answer 401.")
        print(AUTH_HELP)

    print(f"POST {UPDATE_URL}")
    print("body: " + json.dumps(body))

    payload = post_json(UPDATE_URL, body, language, cookie, args.timeout)
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
