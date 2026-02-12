"""Tests for authentication functions."""

import json

import pytest

from wattpilot_api.auth import (
    _bcryptjs_base64_encode,
    _bcryptjs_encode_base64_string,
    _hash_bcrypt,
    _hash_pbkdf2,
    _prehash_for_bcrypt_limit,
    compute_auth_response,
    generate_token,
    hash_password,
    sign_secured_message,
)
from wattpilot_api.models import AuthHashType


class TestHashPassword:
    def test_pbkdf2(self) -> None:
        result = hash_password("password", "12345678", AuthHashType.PBKDF2)
        assert isinstance(result, bytes)
        assert len(result) == 32

    def test_pbkdf2_deterministic(self) -> None:
        r1 = hash_password("password", "12345678", AuthHashType.PBKDF2)
        r2 = hash_password("password", "12345678", AuthHashType.PBKDF2)
        assert r1 == r2

    def test_pbkdf2_different_passwords(self) -> None:
        r1 = hash_password("password1", "12345678", AuthHashType.PBKDF2)
        r2 = hash_password("password2", "12345678", AuthHashType.PBKDF2)
        assert r1 != r2

    def test_pbkdf2_different_serials(self) -> None:
        r1 = hash_password("password", "11111111", AuthHashType.PBKDF2)
        r2 = hash_password("password", "22222222", AuthHashType.PBKDF2)
        assert r1 != r2

    def test_bcrypt(self) -> None:
        result = hash_password("password", "12345678", AuthHashType.BCRYPT)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_bcrypt_deterministic(self) -> None:
        r1 = hash_password("password", "12345678", AuthHashType.BCRYPT)
        r2 = hash_password("password", "12345678", AuthHashType.BCRYPT)
        assert r1 == r2

    def test_unknown_hash_type(self) -> None:
        with pytest.raises(ValueError, match="Unknown hash type"):
            hash_password("pw", "serial", "unknown")  # type: ignore[arg-type]


class TestHashPbkdf2:
    def test_returns_bytes(self) -> None:
        result = _hash_pbkdf2("test", "serial")
        assert isinstance(result, bytes)
        assert len(result) == 32

    def test_empty_serial(self) -> None:
        result = _hash_pbkdf2("test", "")
        assert isinstance(result, bytes)
        assert len(result) == 32


class TestPrehashForBcryptLimit:
    def test_returns_sha256_hex(self) -> None:
        result = _prehash_for_bcrypt_limit(b"password")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest is 64 chars

    def test_deterministic(self) -> None:
        r1 = _prehash_for_bcrypt_limit(b"test")
        r2 = _prehash_for_bcrypt_limit(b"test")
        assert r1 == r2

    def test_different_inputs(self) -> None:
        r1 = _prehash_for_bcrypt_limit(b"password1")
        r2 = _prehash_for_bcrypt_limit(b"password2")
        assert r1 != r2


class TestHashBcrypt:
    def test_returns_bytes(self) -> None:
        result = _hash_bcrypt("password", "12345678")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_custom_iterations(self) -> None:
        result = _hash_bcrypt("password", "12345678", iterations=4)
        assert isinstance(result, bytes)

    def test_non_digit_serial_raises(self) -> None:
        with pytest.raises(ValueError, match="digits only"):
            _hash_bcrypt("password", "abc12345")


class TestBcryptjsBase64Encode:
    def test_basic(self) -> None:
        data = bytes([1, 2, 3, 4])
        result = _bcryptjs_base64_encode(data, 4)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_zero_length_raises(self) -> None:
        with pytest.raises(ValueError, match="Illegal len"):
            _bcryptjs_base64_encode(b"\x00", 0)

    def test_length_exceeds_data_raises(self) -> None:
        with pytest.raises(ValueError, match="Illegal len"):
            _bcryptjs_base64_encode(b"\x00", 2)

    def test_single_byte(self) -> None:
        result = _bcryptjs_base64_encode(b"\xff", 1)
        assert isinstance(result, str)
        assert len(result) == 2  # 1 byte -> 2 base64 chars

    def test_two_bytes(self) -> None:
        result = _bcryptjs_base64_encode(b"\xff\x00", 2)
        assert isinstance(result, str)
        assert len(result) == 3  # 2 bytes -> 3 base64 chars

    def test_three_bytes(self) -> None:
        result = _bcryptjs_base64_encode(b"\xff\x00\xff", 3)
        assert isinstance(result, str)
        assert len(result) == 4  # 3 bytes -> 4 base64 chars


class TestBcryptjsEncodeBase64String:
    def test_digit_serial(self) -> None:
        result = _bcryptjs_encode_base64_string("12345678", 16)
        assert isinstance(result, str)

    def test_non_digit_raises(self) -> None:
        with pytest.raises(ValueError, match="digits only"):
            _bcryptjs_encode_base64_string("abc", 16)


class TestComputeAuthResponse:
    def test_returns_hex_string(self) -> None:
        result = compute_auth_response("a" * 32, "b" * 32, "c" * 32, b"hashedpw12345678")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex

    def test_deterministic(self) -> None:
        r1 = compute_auth_response("t1", "t2", "t3", b"pw")
        r2 = compute_auth_response("t1", "t2", "t3", b"pw")
        assert r1 == r2

    def test_different_tokens(self) -> None:
        r1 = compute_auth_response("t1", "t2", "t3", b"pw")
        r2 = compute_auth_response("t1", "t2", "t4", b"pw")
        assert r1 != r2


class TestGenerateToken:
    def test_returns_32_hex(self) -> None:
        token = generate_token()
        assert isinstance(token, str)
        assert len(token) == 32
        int(token, 16)  # Should be valid hex

    def test_unique(self) -> None:
        tokens = {generate_token() for _ in range(100)}
        assert len(tokens) == 100  # All should be unique


class TestSignSecuredMessage:
    def test_wraps_message(self) -> None:
        message = {"type": "setValue", "requestId": 1, "key": "amp", "value": 16}
        result = sign_secured_message(message, b"hashedpw12345678")
        assert result["type"] == "securedMsg"
        assert result["requestId"] == "1sm"
        assert "hmac" in result
        assert "data" in result

    def test_data_is_json(self) -> None:
        message = {"type": "setValue", "requestId": 42, "key": "lmo", "value": 3}
        result = sign_secured_message(message, b"pw")
        inner = json.loads(result["data"])
        assert inner["type"] == "setValue"
        assert inner["key"] == "lmo"

    def test_hmac_is_hex(self) -> None:
        message = {"type": "setValue", "requestId": 1, "key": "amp", "value": 6}
        result = sign_secured_message(message, b"pw")
        assert len(result["hmac"]) == 64
        int(result["hmac"], 16)  # Valid hex

    def test_hmac_varies_with_password(self) -> None:
        message = {"type": "setValue", "requestId": 1, "key": "amp", "value": 6}
        r1 = sign_secured_message(message, b"pw1")
        r2 = sign_secured_message(message, b"pw2")
        assert r1["hmac"] != r2["hmac"]
