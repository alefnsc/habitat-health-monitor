import hashlib
import hmac

from receiver.signing import HEADER, sign, verify


def test_header_name():
    assert HEADER == "X-Habitat-Signature"


def test_sign_matches_hmac_sha256():
    body = b'{"items":[]}'
    want = "sha256=" + hmac.new(b"k", body, hashlib.sha256).hexdigest()
    assert sign(body, "k") == want


def test_verify_ok_and_tampered():
    body = b'{"items":[1]}'
    good = sign(body, "k")
    assert verify(body, good, "k")
    assert not verify(body + b" ", good, "k")
    assert not verify(body, good, "other")


def test_verify_missing_inputs():
    body = b"{}"
    assert not verify(body, None, "k")
    assert not verify(body, "", "k")
    assert not verify(body, sign(body, "k"), "")
