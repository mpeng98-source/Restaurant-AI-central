"""Signed, short-lived, run-bound evidence and permit validation.

Offline cryptographic envelope only. Key material must remain in a protected
control-plane environment, never in the Codex workspace.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import re
import time

PROJECT = re.compile(r"^proj_[A-Za-z0-9_-]{1,128}$")
SHA = re.compile(r"^[a-f0-9]{40}$")
MAX_AGE = 300


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sign(payload: dict, key: bytes) -> dict:
    if len(key) < 32:
        raise ValueError("weak signing key")
    frozen = json.loads(canonical(payload))
    return {"payload": frozen, "signature": hmac.new(key, canonical(frozen), hashlib.sha256).hexdigest()}


def verify(envelope: dict, key: bytes, *, kind: str, now: int,
           run_id: int, issue_number: int, head_sha: str, project_id: str) -> dict:
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValueError("invalid envelope")
    payload, sig = envelope["payload"], envelope.get("signature")
    if not isinstance(sig, str) or not re.fullmatch("[a-f0-9]{64}", sig):
        raise ValueError("invalid signature")
    expected = hmac.new(key, canonical(payload), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("signature mismatch")
    if (payload.get("kind") != kind or payload.get("run_id") != run_id
            or payload.get("issue_number") != issue_number
            or payload.get("head_sha") != head_sha or payload.get("project_id") != project_id):
        raise ValueError("binding mismatch")
    if not PROJECT.fullmatch(project_id) or not SHA.fullmatch(head_sha):
        raise ValueError("invalid binding")
    issued, expires = payload.get("issued_at"), payload.get("expires_at")
    if not isinstance(issued, int) or not isinstance(expires, int):
        raise ValueError("invalid time")
    if issued > now or now >= expires or expires-issued > MAX_AGE:
        raise ValueError("expired or excessive validity")
    nonce = payload.get("nonce")
    if not isinstance(nonce, str) or not re.fullmatch(r"[a-f0-9]{32,64}", nonce):
        raise ValueError("invalid nonce")
    return payload
