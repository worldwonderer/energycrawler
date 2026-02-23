# -*- coding: utf-8 -*-
"""CookieCloud login-state sync helpers."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import requests

import config
from tools import utils

try:  # pragma: no cover - optional dependency
    from PyCookieCloud import PyCookieCloud as _PyCookieCloud
except Exception:  # pragma: no cover - optional dependency
    _PyCookieCloud = None


@dataclass
class CookieCloudSyncResult:
    platform: str
    enabled: bool = False
    attempted: bool = False
    applied: bool = False
    skipped: bool = False
    cookie_header: str = ""
    cookie_count: int = 0
    source: str = ""
    message: str = ""


def _normalize_platform(platform: str) -> str:
    normalized = (platform or "").strip().lower()
    if normalized == "twitter":
        return "x"
    return normalized


def _normalize_server_url(server: str) -> str:
    normalized = (server or "").strip()
    if not normalized:
        return ""
    if "://" not in normalized:
        normalized = f"http://{normalized}"
    return normalized


def _cookiecloud_key(uuid: str, password: str) -> bytes:
    md5 = hashlib.md5()
    md5.update(f"{uuid}-{password}".encode("utf-8"))
    return md5.hexdigest()[:16].encode("utf-8")


def _bytes_to_key(data: bytes, salt: bytes, output: int = 48) -> bytes:
    if len(salt) != 8:
        raise ValueError("invalid CookieCloud salt length")
    data_with_salt = data + salt
    key = hashlib.md5(data_with_salt).digest()
    final_key = key
    while len(final_key) < output:
        key = hashlib.md5(key + data_with_salt).digest()
        final_key += key
    return final_key[:output]


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise ValueError("invalid CookieCloud payload: empty")
    pad_len = int(data[-1])
    if pad_len <= 0 or pad_len > 16:
        raise ValueError("invalid CookieCloud payload padding")
    if data[-pad_len:] != bytes([pad_len]) * pad_len:
        raise ValueError("invalid CookieCloud payload padding")
    return data[:-pad_len]


def _decrypt_cookiecloud_payload(encrypted: str, uuid: str, password: str) -> Any:
    encrypted_bytes = base64.b64decode(encrypted)
    if encrypted_bytes[:8] != b"Salted__":
        raise ValueError("invalid CookieCloud payload prefix")

    salt = encrypted_bytes[8:16]
    ciphertext = encrypted_bytes[16:]
    key_iv = _bytes_to_key(_cookiecloud_key(uuid, password), salt, output=48)
    key = key_iv[:32]
    iv = key_iv[32:]

    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    plaintext = _pkcs7_unpad(plaintext)

    payload = json.loads(plaintext.decode("utf-8"))
    if isinstance(payload, dict) and "cookie_data" in payload:
        return payload["cookie_data"]
    return payload


def _fetch_cookie_data_via_requests(
    server: str,
    uuid: str,
    password: str,
    timeout_sec: float,
) -> tuple[Any, str]:
    normalized_server = _normalize_server_url(server)
    parsed = urlparse(normalized_server)
    api_root = parsed.path if parsed.path else "/"
    endpoint_path = str(PurePosixPath(api_root, "get", uuid))
    request_url = urljoin(normalized_server, endpoint_path)

    response = requests.get(request_url, timeout=max(timeout_sec, 1.0))
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("CookieCloud response is not a JSON object")

    if isinstance(payload.get("cookie_data"), (dict, list)):
        return payload["cookie_data"], "cookiecloud-plain"

    encrypted = payload.get("encrypted")
    if not isinstance(encrypted, str) or not encrypted.strip():
        raise ValueError("CookieCloud response missing encrypted field")

    decrypted = _decrypt_cookiecloud_payload(encrypted.strip(), uuid=uuid, password=password)
    if not isinstance(decrypted, (dict, list)):
        raise ValueError("CookieCloud decrypted payload has unexpected format")
    return decrypted, "cookiecloud-requests"


def _fetch_cookie_data(
    server: str,
    uuid: str,
    password: str,
    timeout_sec: float,
) -> tuple[Any, str]:
    if _PyCookieCloud is not None:  # pragma: no cover - optional dependency path
        try:
            client = _PyCookieCloud(_normalize_server_url(server), uuid, password)
            decrypted = client.get_decrypted_data()
            if isinstance(decrypted, (dict, list)):
                return decrypted, "pycookiecloud"
        except Exception:
            pass

    return _fetch_cookie_data_via_requests(server, uuid, password, timeout_sec)


def _iter_cookie_entries(cookie_data: Any) -> Iterable[tuple[str, str, str]]:
    if isinstance(cookie_data, dict):
        for host_key, value in cookie_data.items():
            if isinstance(value, list):
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    domain = str(
                        item.get("domain")
                        or item.get("host")
                        or item.get("hostname")
                        or host_key
                        or ""
                    ).strip()
                    name = str(item.get("name") or "").strip()
                    cookie_value = str(item.get("value") or "")
                    if name:
                        yield domain, name, cookie_value
            elif isinstance(value, dict):
                nested = value.get("cookies")
                if isinstance(nested, list):
                    for item in nested:
                        if not isinstance(item, dict):
                            continue
                        domain = str(
                            item.get("domain")
                            or item.get("host")
                            or item.get("hostname")
                            or host_key
                            or ""
                        ).strip()
                        name = str(item.get("name") or "").strip()
                        cookie_value = str(item.get("value") or "")
                        if name:
                            yield domain, name, cookie_value

    elif isinstance(cookie_data, list):
        for item in cookie_data:
            if not isinstance(item, dict):
                continue
            domain = str(item.get("domain") or item.get("host") or item.get("hostname") or "").strip()
            name = str(item.get("name") or "").strip()
            cookie_value = str(item.get("value") or "")
            if name:
                yield domain, name, cookie_value


def _domain_matches(domain: str, candidates: tuple[str, ...]) -> bool:
    normalized = (domain or "").strip().lower().lstrip(".")
    if not normalized:
        return False
    return any(normalized == target or normalized.endswith(f".{target}") for target in candidates)


def _build_cookie_header_for_platform(cookie_data: Any, platform: str) -> tuple[str, int]:
    if platform == "x":
        target_domains = ("x.com", "twitter.com")
    elif platform == "xhs":
        target_domains = ("xiaohongshu.com",)
    else:
        return "", 0

    cookie_map: dict[str, str] = {}
    for domain, name, value in _iter_cookie_entries(cookie_data):
        if _domain_matches(domain, target_domains):
            cookie_map[name] = value

    header = "; ".join(f"{name}={value}" for name, value in cookie_map.items())
    return header, len(cookie_map)


def _runtime_has_cookie_for_platform(platform: str) -> bool:
    if platform == "xhs":
        return bool((getattr(config, "COOKIES", "") or "").strip())

    if platform == "x":
        cookie_header = (getattr(config, "TWITTER_COOKIE", "") or "").strip()
        auth_token = (getattr(config, "TWITTER_AUTH_TOKEN", "") or "").strip()
        ct0 = (getattr(config, "TWITTER_CT0", "") or "").strip()
        return bool(cookie_header or (auth_token and ct0))

    return False


def _apply_cookie_header(platform: str, cookie_header: str) -> None:
    if platform == "xhs":
        config.COOKIES = cookie_header
        return

    if platform == "x":
        config.TWITTER_COOKIE = cookie_header
        cookie_map = utils.convert_str_cookie_to_dict(cookie_header)
        config.TWITTER_AUTH_TOKEN = cookie_map.get("auth_token", "").strip()
        config.TWITTER_CT0 = cookie_map.get("ct0", "").strip()


def sync_cookiecloud_login_state(
    platform: str,
    explicit_cookie_header: str = "",
    force_sync: bool | None = None,
) -> CookieCloudSyncResult:
    normalized_platform = _normalize_platform(platform)
    result = CookieCloudSyncResult(platform=normalized_platform)

    if normalized_platform not in {"xhs", "x"}:
        result.skipped = True
        result.message = f"CookieCloud sync skipped: unsupported platform '{platform}'"
        return result

    result.enabled = bool(getattr(config, "COOKIECLOUD_ENABLED", False))
    if not result.enabled:
        result.skipped = True
        result.message = "CookieCloud sync skipped: disabled"
        return result

    if (explicit_cookie_header or "").strip():
        result.skipped = True
        result.message = "CookieCloud sync skipped: explicit cookies provided by caller"
        return result

    if force_sync is None:
        force_sync = bool(getattr(config, "COOKIECLOUD_FORCE_SYNC", False))
    else:
        force_sync = bool(force_sync)
    if not force_sync and _runtime_has_cookie_for_platform(normalized_platform):
        result.skipped = True
        result.message = "CookieCloud sync skipped: local cookies already present"
        return result

    server = (getattr(config, "COOKIECLOUD_SERVER", "") or "").strip()
    uuid = (getattr(config, "COOKIECLOUD_UUID", "") or "").strip()
    password = (getattr(config, "COOKIECLOUD_PASSWORD", "") or "").strip()
    timeout_sec = float(getattr(config, "COOKIECLOUD_TIMEOUT_SEC", 10.0) or 10.0)

    missing = []
    if not server:
        missing.append("COOKIECLOUD_SERVER")
    if not uuid:
        missing.append("COOKIECLOUD_UUID")
    if not password:
        missing.append("COOKIECLOUD_PASSWORD")
    if missing:
        result.message = f"CookieCloud sync skipped: missing {', '.join(missing)}"
        return result

    result.attempted = True
    try:
        cookie_data, source = _fetch_cookie_data(
            server=server,
            uuid=uuid,
            password=password,
            timeout_sec=timeout_sec,
        )
    except Exception as exc:
        result.message = f"CookieCloud sync failed: {exc}"
        utils.log_event(
            "auth.cookiecloud.sync.failed",
            level="warning",
            platform=normalized_platform,
            reason=str(exc),
        )
        return result

    cookie_header, cookie_count = _build_cookie_header_for_platform(cookie_data, normalized_platform)
    if not cookie_header:
        result.source = source
        result.message = f"CookieCloud sync found no cookies for platform '{normalized_platform}'"
        utils.log_event(
            "auth.cookiecloud.sync.empty",
            level="warning",
            platform=normalized_platform,
            source=source,
        )
        return result

    _apply_cookie_header(normalized_platform, cookie_header)

    result.applied = True
    result.cookie_header = cookie_header
    result.cookie_count = cookie_count
    result.source = source
    result.message = (
        f"CookieCloud sync applied for {normalized_platform} "
        f"({cookie_count} cookies, source={source})"
    )
    utils.log_event(
        "auth.cookiecloud.sync.applied",
        platform=normalized_platform,
        cookie_count=cookie_count,
        source=source,
    )
    return result
