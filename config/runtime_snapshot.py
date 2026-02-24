# -*- coding: utf-8 -*-
"""Runtime configuration snapshot helpers for API presentation."""

from __future__ import annotations

from typing import Any

from . import base_config as runtime_cfg
from . import db_config


def _mask_secret(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    if len(value) <= 8:
        return f"{value[:1]}***{value[-1:]}"
    return f"{value[:2]}***{value[-2:]} (len={len(value)})"


def _masked_secret_field(raw: str) -> dict[str, Any]:
    return {
        "configured": bool(raw.strip()),
        "masked": _mask_secret(raw),
    }


def _is_configured_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def _resolve_config_value(key: str) -> Any:
    if hasattr(runtime_cfg, key):
        return getattr(runtime_cfg, key)
    if hasattr(db_config, key):
        return getattr(db_config, key)
    return ""


def _build_layered_config_snapshot() -> dict[str, Any]:
    layer_order = list(getattr(runtime_cfg, "CONFIG_LAYER_ORDER", ("minimal", "core", "advanced")))
    default_layer = str(getattr(runtime_cfg, "CONFIG_LAYER_DEFAULT", "minimal")).strip().lower() or "minimal"
    sensitive_keys = set(getattr(runtime_cfg, "CONFIG_SENSITIVE_KEYS", set()))

    get_metadata = getattr(runtime_cfg, "get_config_field_metadata", None)
    get_layer_keys = getattr(runtime_cfg, "get_config_layer_env_keys", None)
    explicit_layer_map = getattr(runtime_cfg, "CONFIG_LAYER_ENV_KEYS", {})

    layers: dict[str, list[dict[str, Any]]] = {}
    for layer in layer_order:
        keys: list[str] = []
        if callable(get_layer_keys):
            try:
                keys = list(get_layer_keys(layer, cumulative=False))
            except Exception:
                keys = []
        if not keys and isinstance(explicit_layer_map, dict):
            keys = list(explicit_layer_map.get(layer, []))

        entries: list[dict[str, Any]] = []
        for key in keys:
            meta: dict[str, Any] = {}
            if callable(get_metadata):
                try:
                    maybe_meta = get_metadata(key)
                    if isinstance(maybe_meta, dict):
                        meta = maybe_meta
                except Exception:
                    meta = {}

            raw_value = _resolve_config_value(key)
            sensitive = bool(meta.get("sensitive", key in sensitive_keys))
            display_value: Any = _mask_secret(str(raw_value)) if sensitive else raw_value
            entries.append(
                {
                    "key": key,
                    "label": str(meta.get("label", key)),
                    "description": str(meta.get("description", "")),
                    "layer": str(meta.get("layer", layer)),
                    "configured": _is_configured_value(raw_value),
                    "sensitive": sensitive,
                    "value": display_value,
                }
            )

        layers[layer] = entries

    return {
        "default_layer": default_layer,
        "layers": layers,
    }


def build_public_runtime_config() -> dict[str, Any]:
    """Build a sanitized runtime config snapshot for API responses."""
    return {
        "grouped": _build_layered_config_snapshot(),
        "runtime": {
            "platform": runtime_cfg.PLATFORM,
            "crawler_type": runtime_cfg.CRAWLER_TYPE,
            "login_type": runtime_cfg.LOGIN_TYPE,
            "headless": runtime_cfg.HEADLESS,
            "keywords": runtime_cfg.KEYWORDS,
        },
        "crawler": {
            "start_page": runtime_cfg.START_PAGE,
            "max_notes_count": runtime_cfg.CRAWLER_MAX_NOTES_COUNT,
            "max_concurrency": runtime_cfg.MAX_CONCURRENCY_NUM,
            "max_sleep_sec": runtime_cfg.CRAWLER_MAX_SLEEP_SEC,
            "enable_comments": runtime_cfg.ENABLE_GET_COMMENTS,
            "enable_sub_comments": runtime_cfg.ENABLE_GET_SUB_COMMENTS,
            "enable_media": runtime_cfg.ENABLE_GET_MEIDAS,
            "enable_incremental_crawl": runtime_cfg.ENABLE_INCREMENTAL_CRAWL,
            "resume_from_checkpoint": runtime_cfg.RESUME_FROM_CHECKPOINT,
            "checkpoint_path": runtime_cfg.CRAWLER_CHECKPOINT_PATH,
        },
        "energy": {
            "enabled": runtime_cfg.ENABLE_ENERGY_BROWSER,
            "service_address": runtime_cfg.ENERGY_SERVICE_ADDRESS,
            "headless": runtime_cfg.ENERGY_HEADLESS,
            "browser_id_prefix": runtime_cfg.ENERGY_BROWSER_ID_PREFIX,
            "browser_id": runtime_cfg.ENERGY_BROWSER_ID,
            "xhs_enabled": runtime_cfg.XHS_ENABLE_ENERGY,
            "twitter_enabled": runtime_cfg.TWITTER_ENABLE_ENERGY,
        },
        "auth": {
            "xhs_cookie": _masked_secret_field(runtime_cfg.COOKIES),
            "twitter_auth_token": _masked_secret_field(runtime_cfg.TWITTER_AUTH_TOKEN),
            "twitter_ct0": _masked_secret_field(runtime_cfg.TWITTER_CT0),
            "twitter_cookie": _masked_secret_field(runtime_cfg.TWITTER_COOKIE),
            "cookiecloud": {
                "enabled": runtime_cfg.COOKIECLOUD_ENABLED,
                "force_sync": runtime_cfg.COOKIECLOUD_FORCE_SYNC,
                "server": runtime_cfg.COOKIECLOUD_SERVER,
                "uuid": _masked_secret_field(runtime_cfg.COOKIECLOUD_UUID),
                "password": _masked_secret_field(runtime_cfg.COOKIECLOUD_PASSWORD),
                "timeout_sec": runtime_cfg.COOKIECLOUD_TIMEOUT_SEC,
            },
            "auth_watchdog": {
                "enabled": runtime_cfg.AUTH_WATCHDOG_ENABLED,
                "max_retries": runtime_cfg.AUTH_WATCHDOG_MAX_RETRIES,
                "retry_interval_sec": runtime_cfg.AUTH_WATCHDOG_RETRY_INTERVAL_SEC,
                "force_cookiecloud_sync": runtime_cfg.AUTH_WATCHDOG_FORCE_COOKIECLOUD_SYNC,
                "max_runtime_recoveries": runtime_cfg.AUTH_WATCHDOG_MAX_RUNTIME_RECOVERIES,
            },
        },
        "storage": {
            "save_data_option": runtime_cfg.SAVE_DATA_OPTION,
            "save_data_path": runtime_cfg.SAVE_DATA_PATH,
            "mysql": {
                "host": db_config.MYSQL_DB_HOST,
                "port": db_config.MYSQL_DB_PORT,
                "user": db_config.MYSQL_DB_USER,
                "database": db_config.MYSQL_DB_NAME,
                "password": _masked_secret_field(str(db_config.MYSQL_DB_PWD)),
            },
            "mongodb": {
                "host": db_config.MONGODB_HOST,
                "port": db_config.MONGODB_PORT,
                "user": db_config.MONGODB_USER,
                "database": db_config.MONGODB_DB_NAME,
                "password": _masked_secret_field(str(db_config.MONGODB_PWD)),
            },
            "postgres": {
                "host": db_config.POSTGRES_DB_HOST,
                "port": db_config.POSTGRES_DB_PORT,
                "user": db_config.POSTGRES_DB_USER,
                "database": db_config.POSTGRES_DB_NAME,
                "password": _masked_secret_field(str(db_config.POSTGRES_DB_PWD)),
            },
        },
        "safety": {
            "hard_max_notes_count": runtime_cfg.CRAWLER_HARD_MAX_NOTES_COUNT,
            "hard_max_concurrency": runtime_cfg.CRAWLER_HARD_MAX_CONCURRENCY,
            "min_sleep_sec": runtime_cfg.CRAWLER_MIN_SLEEP_SEC,
            "sleep_jitter_sec": runtime_cfg.CRAWLER_SLEEP_JITTER_SEC,
            "retry_base_delay_sec": runtime_cfg.CRAWLER_RETRY_BASE_DELAY_SEC,
            "retry_max_delay_sec": runtime_cfg.CRAWLER_RETRY_MAX_DELAY_SEC,
        },
    }


API_CONFIG_RESPONSE_EXAMPLE = {
    "grouped": {
        "default_layer": "minimal",
        "layers": {
            "minimal": [
                {
                    "key": "PLATFORM",
                    "label": "Platform",
                    "description": "目标平台（xhs/x）",
                    "layer": "minimal",
                    "configured": True,
                    "sensitive": False,
                    "value": "xhs",
                }
            ],
            "core": [],
            "advanced": [],
        },
    },
    "runtime": {
        "platform": "xhs",
        "crawler_type": "search",
        "login_type": "cookie",
        "headless": False,
        "keywords": "新能源",
    },
    "energy": {
        "enabled": True,
        "service_address": "localhost:50051",
        "headless": True,
        "browser_id_prefix": "energycrawler",
        "browser_id": "energycrawler_xhs",
        "xhs_enabled": True,
        "twitter_enabled": True,
    },
    "auth": {
        "xhs_cookie": {"configured": True, "masked": "a1***en (len=18)"},
        "twitter_auth_token": {"configured": False, "masked": ""},
        "twitter_ct0": {"configured": False, "masked": ""},
        "twitter_cookie": {"configured": False, "masked": ""},
        "cookiecloud": {
            "enabled": False,
            "force_sync": False,
            "server": "",
            "uuid": {"configured": False, "masked": ""},
            "password": {"configured": False, "masked": ""},
            "timeout_sec": 10.0,
        },
        "auth_watchdog": {
            "enabled": True,
            "max_retries": 1,
            "retry_interval_sec": 2.0,
            "force_cookiecloud_sync": True,
            "max_runtime_recoveries": 1,
        },
    },
}
