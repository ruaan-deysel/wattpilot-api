"""Authentication helpers for the Wattpilot WebSocket protocol.

Supports PBKDF2 (default) and bcrypt (Wattpilot Flex devices).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import random
from typing import Any

import bcrypt as _bcrypt

from wattpilot_api.models import AuthHashType

# bcrypt.js custom base64 alphabet
_BASE64_CODE = list("./ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")


def hash_password(password: str, serial: str, hash_type: AuthHashType) -> bytes:
    """Hash *password* with the device *serial* using the given algorithm.

    Returns the raw bytes used as the shared secret for subsequent auth steps.
    """
    if hash_type == AuthHashType.PBKDF2:
        return _hash_pbkdf2(password, serial)
    if hash_type == AuthHashType.BCRYPT:
        return _hash_bcrypt(password, serial)
    msg = f"Unknown hash type: {hash_type}"
    raise ValueError(msg)


def _hash_pbkdf2(password: str, serial: str) -> bytes:
    raw = hashlib.pbkdf2_hmac(
        "sha512",
        password.encode(),
        serial.encode() if serial else b"",
        100000,
        256,
    )
    return base64.b64encode(raw)[:32]


def _hash_bcrypt(password: str, serial: str, iterations: int = 8) -> bytes:
    password_sha256 = hashlib.sha256(password.encode("utf-8")).hexdigest()
    serial_b64 = _bcryptjs_encode_base64_string(serial, 16)

    salt_parts: list[str] = ["$2a$"]
    if iterations < 10:
        salt_parts.append("0")
    salt_parts.append(str(iterations))
    salt_parts.append("$")
    salt_parts.append(serial_b64)
    salt = "".join(salt_parts)

    pw_hash = _bcrypt.hashpw(password_sha256.encode("utf-8"), salt.encode("utf-8"))
    return pw_hash[len(salt) :].rstrip()


def _bcryptjs_base64_encode(b: bytes, length: int) -> str:
    """Port of bcrypt.js ``encodeBase64`` for compatibility with the Wattpilot firmware."""
    if length <= 0 or length > len(b):
        msg = f"Illegal len: {length}"
        raise ValueError(msg)

    off = 0
    rs: list[str] = []
    while off < length:
        c1 = b[off] & 0xFF
        off += 1
        rs.append(_BASE64_CODE[(c1 >> 2) & 0x3F])
        c1 = (c1 & 0x03) << 4
        if off >= length:
            rs.append(_BASE64_CODE[c1 & 0x3F])
            break

        c2 = b[off] & 0xFF
        off += 1
        c1 |= (c2 >> 4) & 0x0F
        rs.append(_BASE64_CODE[c1 & 0x3F])
        c1 = (c2 & 0x0F) << 2
        if off >= length:
            rs.append(_BASE64_CODE[c1 & 0x3F])
            break

        c2 = b[off] & 0xFF
        off += 1
        c1 |= (c2 >> 6) & 0x03
        rs.append(_BASE64_CODE[c1 & 0x3F])
        rs.append(_BASE64_CODE[c2 & 0x3F])

    return "".join(rs)


def _bcryptjs_encode_base64_string(s: str, length: int) -> str:
    """Encode a numeric-only serial string for bcrypt salt generation."""
    if s.isdigit():
        vals = [ord(ch) - ord("0") for ch in s]
        b = bytes([0] * (length - len(vals)) + vals)
    else:
        msg = f"Serial must be digits only, got: {s}"
        raise ValueError(msg)
    return _bcryptjs_base64_encode(b, length)


def compute_auth_response(
    token1: str,
    token2: str,
    token3: str,
    hashed_password: bytes,
) -> str:
    """Compute the SHA-256 auth hash sent during the ``auth`` handshake step."""
    hash1 = hashlib.sha256(token1.encode() + hashed_password).hexdigest()
    return hashlib.sha256((token3 + token2 + hash1).encode()).hexdigest()


def generate_token() -> str:
    """Generate a random 32-character hex token (token3)."""
    ran = random.randrange(10**80)
    return f"{ran:064x}"[:32]


def sign_secured_message(message: dict[str, Any], hashed_password: bytes) -> dict[str, Any]:
    """Wrap *message* in a ``securedMsg`` envelope with HMAC-SHA256 signature."""
    request_id = message["requestId"]
    payload = json.dumps(message)
    h = hmac.new(
        bytearray(hashed_password),
        bytearray(payload.encode()),
        hashlib.sha256,
    )
    return {
        "type": "securedMsg",
        "data": payload,
        "requestId": f"{request_id}sm",
        "hmac": h.hexdigest(),
    }
