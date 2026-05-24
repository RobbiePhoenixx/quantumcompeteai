"""Tests for resilient media download in services/r2_storage.py.

Kie's temp media host intermittently fails TLS with [SSL: BAD_SIGNATURE]. The
bytes are fine — only cert validation flakes — so the download must retry once
with verify=False instead of giving up (which left items on expiring URLs).
"""
from unittest.mock import patch, MagicMock

import requests

import services.r2_storage as r2


def test_download_retries_without_verification_on_ssl_error():
    calls = []

    def fake_get(url, timeout=None, verify=True):
        calls.append(verify)
        if verify is True:
            raise requests.exceptions.SSLError("[SSL: BAD_SIGNATURE] bad signature")
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.content = b"\x89PNG fake bytes"
        resp.headers = {"Content-Type": "image/png"}
        return resp

    with patch("services.r2_storage.requests.get", side_effect=fake_get):
        data, ctype = r2._download_media("https://tempfile.aiquickdraw.com/x.png")

    # First attempt verifies (and fails), second retries with verify=False.
    assert calls == [True, False]
    assert data == b"\x89PNG fake bytes"
    assert ctype == "image/png"


def test_download_succeeds_normally_without_retry():
    calls = []

    def fake_get(url, timeout=None, verify=True):
        calls.append(verify)
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.content = b"ok"
        resp.headers = {"Content-Type": "image/jpeg"}
        return resp

    with patch("services.r2_storage.requests.get", side_effect=fake_get):
        data, ctype = r2._download_media("https://example.com/i.jpg")

    assert calls == [True]   # no insecure retry needed
    assert data == b"ok"
