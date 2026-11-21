#!/usr/bin/env python3
"""Minimal App Store Connect API client (stdlib + openssl), copied from drewwells' deej (scripts/asc.py) for the
fork's TestFlight builds. Its own internal group ("abs internal"); same tester.

Reads ASC_KEY_ID / ASC_ISSUER_ID / ASC_KEY_PATH from the environment
(`. ~/.config/dance-practice/deploy.env`). Never prints the token.

    asc.py GET /v1/devices
    asc.py POST /v1/certificates body.json
    asc.py next-build dev.wellsstar.abs 415   max(415, highest uploaded build + 1); fails if there's no app record
    asc.py testflight dev.wellsstar.abs 420   wait for build 420 to process, give it to the internal group
    asc.py notes dev.wellsstar.abs 420 notes.txt   set build 420's TestFlight "What to Test" (en-US) from
        notes.txt and print what App Store Connect now holds. Plain text, at most 4000 characters; the
        TestFlight app on the phone shows it as is, so keep lines short: a numbered "What's new" and a
        numbered "To test".
    asc.py bundle-id dev.wellsstar.abs "ABS Fork"   register a bundle id (if new) and print its resource id
    asc.py profile "abs watch dev" IOS_APP_DEVELOPMENT dev.wellsstar.abs.watchkitapp CERT out.mobileprovision [DEVICE...]
        (re)make a profile: same-named ones are deleted first (a capability change invalidates them)
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def der_to_raw(der: bytes) -> bytes:
    # ECDSA-Sig-Value ::= SEQUENCE { r INTEGER, s INTEGER } -> r || s, 32 bytes each.
    assert der[0] == 0x30
    i = 2 if der[1] < 0x80 else 3
    out = b""
    for _ in range(2):
        assert der[i] == 0x02
        n = der[i + 1]
        v = der[i + 2 : i + 2 + n].lstrip(b"\x00")
        out += v.rjust(32, b"\x00")
        i += 2 + n
    return out


def token() -> str:
    header = {"alg": "ES256", "kid": os.environ["ASC_KEY_ID"], "typ": "JWT"}
    now = int(time.time())
    claims = {"iss": os.environ["ASC_ISSUER_ID"], "iat": now, "exp": now + 600, "aud": "appstoreconnect-v1"}
    signing_input = f"{b64(json.dumps(header).encode())}.{b64(json.dumps(claims).encode())}"
    der = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", os.path.expanduser(os.environ["ASC_KEY_PATH"])],
        input=signing_input.encode(), capture_output=True, check=True,
    ).stdout
    return f"{signing_input}.{b64(der_to_raw(der))}"


def call(method: str, path: str, body=None, retry: bool = None):
    """One API call; exits on an error. App Store Connect sometimes answers 500 (or 401) to a good
    request for a few minutes (betaBuildLocalizations, 2026-10-16), so GET and PATCH, and any call
    made with retry=True, try again a few times."""
    if retry is None:
        retry = method in ("GET", "PATCH")
    for attempt in range(5 if retry else 1):
        req = urllib.request.Request(
            "https://api.appstoreconnect.apple.com" + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as r:
                data = r.read()
                return json.loads(data) if data else {}
        except urllib.error.HTTPError as e:
            err = f"{e.code}: {e.read().decode()}"
            if not retry or attempt == 4 or (e.code < 500 and e.code != 401):
                sys.exit(err)
            print(f"{method} {path.split('?')[0]}: {e.code}, retrying", file=sys.stderr)
            time.sleep(20)


TESTERS = ["drew.wells00@gmail.com"]
GROUP = "abs internal"


def app_id(bundle_id: str) -> str:
    apps = call("GET", f"/v1/apps?filter[bundleId]={bundle_id}")["data"]
    if not apps:
        sys.exit(f"no App Store Connect app for {bundle_id}: create it at appstoreconnect.apple.com > Apps > +")
    return apps[0]["id"]


def next_build(bundle_id: str, floor: int) -> int:
    """The commit count, unless App Store Connect already has that build number or a higher one."""
    builds = call("GET", f"/v1/builds?filter[app]={app_id(bundle_id)}&sort=-uploadedDate&limit=200")["data"]
    return max([floor] + [int(b["attributes"]["version"]) + 1 for b in builds if b["attributes"]["version"].isdigit()])


def testflight(bundle_id: str, build: str):
    """Wait for an uploaded build to finish processing, then make it available to the internal group."""
    app = app_id(bundle_id)
    deadline = time.time() + 3600
    while True:
        found = call("GET", f"/v1/builds?filter[app]={app}&filter[version]={build}&filter[preReleaseVersion.platform]=IOS")["data"]
        state = found[0]["attributes"]["processingState"] if found else "NOT_SEEN_YET"
        print(f"build {build}: {state}", file=sys.stderr)
        if state == "VALID":
            break
        if state in ("FAILED", "INVALID"):
            sys.exit(f"build {build} processing {state}")
        if time.time() > deadline:
            sys.exit(f"build {build} still {state} after an hour")
        time.sleep(30)
    b = found[0]
    if b["attributes"].get("usesNonExemptEncryption") is None:
        call("PATCH", f"/v1/builds/{b['id']}",
             {"data": {"type": "builds", "id": b["id"], "attributes": {"usesNonExemptEncryption": False}}})
    groups = [g for g in call("GET", f"/v1/betaGroups?filter[app]={app}")["data"]
              if g["attributes"]["name"] == GROUP and g["attributes"]["isInternalGroup"]]
    if groups:
        group = groups[0]["id"]
    else:
        group = call("POST", "/v1/betaGroups", {"data": {"type": "betaGroups",
            "attributes": {"name": GROUP, "isInternalGroup": True, "hasAccessToAllBuilds": True},
            "relationships": {"app": {"data": {"type": "apps", "id": app}}}}})["data"]["id"]
    have = {t["attributes"]["email"] for t in call("GET", f"/v1/betaGroups/{group}/betaTesters?limit=200")["data"]}
    for email in TESTERS:
        if email not in have:
            call("POST", "/v1/betaTesters", {"data": {"type": "betaTesters", "attributes": {"email": email},
                "relationships": {"betaGroups": {"data": [{"type": "betaGroups", "id": group}]}}}})
    # An internal group with access to all builds gets it by itself.
    if not call("GET", f"/v1/betaGroups/{group}")["data"]["attributes"].get("hasAccessToAllBuilds"):
        call("POST", f"/v1/betaGroups/{group}/relationships/builds", {"data": [{"type": "builds", "id": b["id"]}]})
    print(f"build {build} ({b['id']}) is in TestFlight group '{GROUP}' ({group})")


def notes(bundle_id: str, build: str, path: str, locale: str = "en-US"):
    """Set a build's TestFlight "What to Test" text (betaBuildLocalizations.whatsNew) and read it back."""
    text = open(path, encoding="utf-8").read().strip()
    if not text:
        sys.exit(f"{path} is empty")
    if len(text) > 4000:
        sys.exit(f"{path} is {len(text)} characters; TestFlight allows 4000")
    found = call("GET", f"/v1/builds?filter[app]={app_id(bundle_id)}&filter[version]={build}"
                        f"&filter[preReleaseVersion.platform]=IOS")["data"]
    if not found:
        sys.exit(f"no build {build} for {bundle_id}")
    bid = found[0]["id"]

    def mine():
        return [l for l in call("GET", f"/v1/builds/{bid}/betaBuildLocalizations?limit=50")["data"]
                if l["attributes"]["locale"] == locale]

    have = mine()
    if have:
        call("PATCH", f"/v1/betaBuildLocalizations/{have[0]['id']}", {"data": {
            "type": "betaBuildLocalizations", "id": have[0]["id"], "attributes": {"whatsNew": text}}})
    else:
        call("POST", "/v1/betaBuildLocalizations", {"data": {"type": "betaBuildLocalizations",
            "attributes": {"locale": locale, "whatsNew": text},
            "relationships": {"build": {"data": {"type": "builds", "id": bid}}}}}, retry=True)
        # (If a 500 hid a create that went through, the retry fails 409: run it again to PATCH.)
    back = mine()
    got = back[0]["attributes"]["whatsNew"] if back else None
    print(f"build {build} ({bid}) {locale} What to Test:\n{got}")
    if got != text:
        sys.exit("read-back differs from the file")


def profile(name: str, kind: str, identifier: str, cert: str, out: str, devices: list):
    """Make profile `name` for bundle id `identifier` with certificate `cert` (and `devices`), after
    deleting any profile of that name, and write it to `out`."""
    bids = call("GET", f"/v1/bundleIds?filter[identifier]={identifier}")["data"]
    bid = next((b["id"] for b in bids if b["attributes"]["identifier"] == identifier), None)
    if not bid:
        sys.exit(f"no bundle id {identifier}")
    for p in call("GET", "/v1/profiles?limit=200&fields[profiles]=name")["data"]:
        if p["attributes"]["name"] == name:
            call("DELETE", f"/v1/profiles/{p['id']}")
            print(f"deleted old profile {p['id']}", file=sys.stderr)
    rel = {"bundleId": {"data": {"type": "bundleIds", "id": bid}},
           "certificates": {"data": [{"type": "certificates", "id": cert}]}}
    if devices:
        rel["devices"] = {"data": [{"type": "devices", "id": d} for d in devices]}
    made = call("POST", "/v1/profiles", {"data": {"type": "profiles",
        "attributes": {"name": name, "profileType": kind}, "relationships": rel}})["data"]
    with open(os.path.expanduser(out), "wb") as f:
        f.write(base64.b64decode(made["attributes"]["profileContent"]))
    print(f"profile {made['id']} '{name}' {made['attributes']['profileState']} -> {out}")


def bundle_id(identifier: str, name: str, platform: str = "IOS") -> str:
    """The resource id of bundle id `identifier`, registered first if it isn't."""
    bids = call("GET", f"/v1/bundleIds?filter[identifier]={identifier}")["data"]
    have = next((b["id"] for b in bids if b["attributes"]["identifier"] == identifier), None)
    if have:
        return have
    return call("POST", "/v1/bundleIds", {"data": {"type": "bundleIds",
        "attributes": {"identifier": identifier, "name": name, "platform": platform}}})["data"]["id"]


if __name__ == "__main__":
    if sys.argv[1] == "bundle-id":
        print(bundle_id(sys.argv[2], sys.argv[3]))
        sys.exit(0)
    if sys.argv[1] == "profile":
        profile(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[7:])
        sys.exit(0)
    if sys.argv[1] == "testflight":
        testflight(sys.argv[2], sys.argv[3])
        sys.exit(0)
    if sys.argv[1] == "notes":
        notes(sys.argv[2], sys.argv[3], sys.argv[4])
        sys.exit(0)
    if sys.argv[1] == "next-build":
        print(next_build(sys.argv[2], int(sys.argv[3])))
        sys.exit(0)
    method, path = sys.argv[1], sys.argv[2]
    body = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else None
    json.dump(call(method, path, body), sys.stdout, indent=1)
