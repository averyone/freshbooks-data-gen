#!/usr/bin/env python3
"""
Walk through the FreshBooks OAuth 2.0 flow and capture a bearer token.

What this does
--------------
1. Asks for (or reads from env) your FreshBooks Client ID and Client Secret.
2. Opens your browser to the FreshBooks authorize URL.
3. Spins up a tiny local HTTP server on http://localhost:8765/callback.
4. Catches the redirect, exchanges the authorization code for a bearer token.
5. Writes credentials to ../.env (gitignored).

What you do first (one time, in your browser)
---------------------------------------------
1. Go to https://my.freshbooks.com/#/developer
2. Click "Create an App"
   - Name: anything (e.g. "freshbooks-data-gen")
   - Description: anything
   - Redirect URI: https://localhost:8765/callback     <-- exactly this
3. Save. FreshBooks shows you a Client ID and Client Secret.
4. Run this script and paste those in.

The HTTPS-on-localhost wrinkle
------------------------------
FreshBooks requires HTTPS in the redirect URI it stores, but your local
server is plain HTTP. After you click Authorize, your browser will land
on https://localhost:8765/callback?code=... and fail to load.

When that happens: edit the URL bar — change "https://" to "http://" —
and hit Enter. Your local server is listening there and will catch the
code. The script then exchanges the code for a token automatically.

Usage
-----
    python3 scripts/get_token.py

Or non-interactively:

    FRESHBOOKS_CLIENT_ID=... FRESHBOOKS_CLIENT_SECRET=... \
        python3 scripts/get_token.py
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import socketserver
import sys
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

PORT = 8765
HTTP_REDIRECT_URI = f"http://localhost:{PORT}/callback"
HTTPS_REDIRECT_URI = f"https://localhost:{PORT}/callback"  # the one you register

TOKEN_URL = "https://api.freshbooks.com/auth/oauth/token"
AUTHORIZE_URL = "https://auth.freshbooks.com/oauth/authorize/"

captured_code: str | None = None


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global captured_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            captured_code = params["code"][0]
            self._respond(200, "<h1>Got it.</h1><p>You can close this tab and return to your terminal.</p>")
        elif "error" in params:
            self._respond(400, f"<h1>FreshBooks returned an error</h1><pre>{params}</pre>")
        else:
            self._respond(400, "<h1>No code parameter.</h1>")

    def _respond(self, status, body_html):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body_html.encode("utf-8"))

    def log_message(self, *args, **kwargs):
        pass  # silence access log


def prompt(prompt_text, env_var):
    val = os.environ.get(env_var)
    if val:
        return val
    val = input(f"{prompt_text}: ").strip()
    if not val:
        sys.exit(f"ERROR: {prompt_text} is required.")
    return val


def exchange_code_for_token(client_id, client_secret, code):
    body = json.dumps({
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": HTTPS_REDIRECT_URI,
    }).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Api-Version": "alpha",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        sys.exit(f"\nToken exchange failed (HTTP {e.code}):\n{body}")


def write_env_file(env_path, **values):
    lines = [f"{k}={v}\n" for k, v in values.items() if v]
    env_path.write_text("".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--client-id", help="FreshBooks Client ID (also reads FRESHBOOKS_CLIENT_ID)")
    parser.add_argument("--client-secret", help="FreshBooks Client Secret (also reads FRESHBOOKS_CLIENT_SECRET)")
    parser.add_argument("--no-browser", action="store_true", help="Print the URL instead of opening a browser tab")
    args = parser.parse_args()

    client_id = args.client_id or prompt("Client ID", "FRESHBOOKS_CLIENT_ID")
    client_secret = args.client_secret or prompt("Client Secret", "FRESHBOOKS_CLIENT_SECRET")

    auth_url = (
        f"{AUTHORIZE_URL}?response_type=code"
        f"&redirect_uri={urllib.parse.quote(HTTPS_REDIRECT_URI, safe='')}"
        f"&client_id={urllib.parse.quote(client_id, safe='')}"
    )

    print(f"\nLocal listener will start on {HTTP_REDIRECT_URI}")
    print("\nAfter you click 'Authorize' in FreshBooks:")
    print(f"  1. Your browser lands on {HTTPS_REDIRECT_URI}?code=... and fails to load.")
    print(f"  2. In the URL bar, change 'https://' to 'http://' and press Enter.")
    print(f"  3. This script catches the code and finishes automatically.\n")
    print("Authorize URL:")
    print(f"  {auth_url}\n")

    if not args.no_browser:
        webbrowser.open(auth_url)

    print(f"Waiting for redirect on port {PORT}... (Ctrl-C to abort)")

    with socketserver.TCPServer(("localhost", PORT), CallbackHandler) as httpd:
        while captured_code is None:
            httpd.handle_request()

    print(f"\nGot authorization code (prefix: {captured_code[:12]}...)")
    print("Exchanging for access token...")
    token_response = exchange_code_for_token(client_id, client_secret, captured_code)

    access_token = token_response.get("access_token")
    refresh_token = token_response.get("refresh_token", "")
    expires_in = token_response.get("expires_in", 0)

    if not access_token:
        sys.exit(f"No access_token in response:\n{json.dumps(token_response, indent=2)}")

    print("\n  Access token captured.")
    print(f"  Expires in: {expires_in} seconds ({expires_in // 3600} hours)")
    print(f"  Token (first 24 chars): {access_token[:24]}...")

    env_path = (Path(__file__).resolve().parent / ".." / ".env").resolve()
    write_env_file(
        env_path,
        FRESHBOOKS_TOKEN=access_token,
        FRESHBOOKS_REFRESH_TOKEN=refresh_token,
        FRESHBOOKS_CLIENT_ID=client_id,
        FRESHBOOKS_CLIENT_SECRET=client_secret,
    )
    print(f"\n  Wrote credentials to {env_path}")

    print("\nNext step:")
    print(f"  set -a; source .env; set +a")
    print(f"  python3 scripts/push.py --dry-run --limit 1")


if __name__ == "__main__":
    main()
