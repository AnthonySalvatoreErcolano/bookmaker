"""Lulu Print API (optional). Without credentials every function returns None and bookmaker uses
its own geometry, flagged as unverified where it is not taken from Lulu's guide or template.

Credentials, either:
  environment variables LULU_CLIENT_KEY and LULU_CLIENT_SECRET (and LULU_SANDBOX=1 for the sandbox), or
  a file ~/.bookmaker/lulu.json: {"client_key": "...", "client_secret": "...", "sandbox": false}

Endpoints used (check against https://api.lulu.com/docs/ when the key is first set up):
  POST {base}/auth/realms/glasstree/protocol/openid-connect/token   (client credentials)
  POST {base}/cover-dimensions/   {"pod_package_id", "interior_page_count", "unit": "inch"}
  POST {base}/validate-interior/ and /validate-cover/                (file checks, by URL)

The pod_package_id is trim code + colour + quality + binding + paper + PPI + finish + linen + foil,
e.g. 0600X0900BWSTDPB060UW444MXX (6×9, black and white, standard, perfect bound, 60# white, matte).
"""

import json
import os
import time
import urllib.request
from pathlib import Path

from . import pages as pg

_TOKEN = {}


def credentials():
    key, secret = os.environ.get("LULU_CLIENT_KEY"), os.environ.get("LULU_CLIENT_SECRET")
    sandbox = os.environ.get("LULU_SANDBOX") == "1"
    f = Path.home() / ".bookmaker" / "lulu.json"
    if not (key and secret) and f.exists():
        d = json.loads(f.read_text())
        key, secret, sandbox = d.get("client_key"), d.get("client_secret"), d.get("sandbox", False)
    if not (key and secret):
        return None
    return key, secret, ("https://api.sandbox.lulu.com" if sandbox else "https://api.lulu.com")


def pod_package_id(trim_name, binding, colour="BW", quality="STD", paper="060UW444", finish="M"):
    _, _, _, code = pg.trim(trim_name)
    bcode = pg.BINDINGS[binding]["code"]
    linen = "N" if binding == "dust-jacket" else "X"          # unverified: linen code for jackets
    return f"{code}{colour}{quality}{bcode}{paper}{finish}{linen}X"


def _token(creds):
    key, secret, base = creds
    if _TOKEN.get("exp", 0) > time.time() + 30:
        return _TOKEN["value"]
    import base64
    req = urllib.request.Request(f"{base}/auth/realms/glasstree/protocol/openid-connect/token",
                                 data=b"grant_type=client_credentials",
                                 headers={"Authorization": "Basic " + base64.b64encode(f"{key}:{secret}".encode()).decode(),
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    _TOKEN.update(value=d["access_token"], exp=time.time() + d.get("expires_in", 300))
    return _TOKEN["value"]


def _post(path, payload):
    creds = credentials()
    if not creds:
        return None
    req = urllib.request.Request(f"{creds[2]}{path}", data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {_token(creds)}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def cover_dimensions(trim_name, binding, pages, **product):
    """{'width': in, 'height': in} from Lulu, or None without credentials or on any error."""
    try:
        d = _post("/cover-dimensions/", {"pod_package_id": pod_package_id(trim_name, binding, **product),
                                         "interior_page_count": pages, "unit": "inch"})
    except Exception as e:                 # never stop a build because the API is unreachable
        print(f"     (Lulu API not used: {e})")
        return None
    if not d:
        return None
    return {"width": float(d["width"]), "height": float(d["height"])}


def validate(kind, url, trim_name, binding, pages=None):
    """Ask Lulu to validate a file already uploaded somewhere public (kind: interior or cover)."""
    payload = {"source_url": url, "pod_package_id": pod_package_id(trim_name, binding)}
    if kind == "cover":
        payload["interior_page_count"] = pages
    return _post(f"/validate-{kind}/", payload)
