import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import redis

# ─── Configurar Logging ─────────────────────────────────────────
os.makedirs(".logs", exist_ok=True)
logger = logging.getLogger(__name__)

# Handler para archivo (rotativo) con UTF-8
try:
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        ".logs/redis.log",
        maxBytes=5_000_000,  # 5 MB
        backupCount=3,
        encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter('%(asctime)s | %(name)s | %(levelname)-8s | %(message)s')
    )
    logger.addHandler(file_handler)
except Exception:
    pass

logger.setLevel(logging.DEBUG)

_client: Optional[redis.Redis] = None


def init_redis(url: str) -> None:
    global _client
    try:
        _client = redis.from_url(url, decode_responses=False)
        _client.ping()
        info = _client.info()
        logger.info(
            "[OK] Conexión a Redis establecida. Versión: %s, Memoria: %s",
            info.get("redis_version", "N/A"),
            info.get("used_memory_human", "N/A")
        )
    except Exception as exc:
        _client = None
        logger.warning("[WARN] Redis no disponible, operando sin caché. Error: %s", exc)


def _get_client() -> Optional[redis.Redis]:
    return _client


def _string_get(r: redis.Redis, key: str) -> Optional[str]:
    val = r.get(key)
    if val is None:
        return None
    return val.decode("utf-8")


def _string_set(
    r: redis.Redis, key: str, value: str, **kwargs
) -> None:
    r.set(key, value.encode("utf-8"), **kwargs)


# ─── Trips Cache ────────────────────────────────────────────────


def get_trips_cache(from_date, to_date) -> Optional[pd.DataFrame]:
    r = _get_client()
    if r is None:
        return None
    key = f"trips:{from_date.isoformat()}:{to_date.isoformat()}"
    try:
        data = _string_get(r, key)
        if data is not None:
            logger.debug(f"[CACHE_HIT] trips para {from_date} a {to_date}")
            import io
            return pd.read_json(io.StringIO(data), orient="split")
        logger.debug(f"[CACHE_MISS] trips para {from_date} a {to_date}")
    except Exception as exc:
        logger.warning("[ERROR] Error leyendo trips cache: %s", exc)
    return None


def set_trips_cache(from_date, to_date, df: pd.DataFrame) -> None:
    r = _get_client()
    if r is None:
        return
    key = f"trips:{from_date.isoformat()}:{to_date.isoformat()}"
    try:
        _string_set(r, key, df.to_json(orient="split"), ex=21600)
        logger.debug(f"[CACHE_SET] trips {from_date} a {to_date} (6h TTL, {len(df)} rows)")
    except Exception as exc:
        logger.warning("[ERROR] Error guardando trips cache: %s", exc)


# ─── Afectación Cache ───────────────────────────────────────────


def get_afectacion_cache(url: str) -> Optional[bytes]:
    r = _get_client()
    if r is None:
        return None
    key = f"afectacion:{hashlib.sha256(url.encode()).hexdigest()}"
    try:
        result = r.get(key)
        if result is not None:
            logger.debug(f"[CACHE_HIT] afectación ({len(result)} bytes)")
            return result
        logger.debug(f"[CACHE_MISS] afectación")
    except Exception as exc:
        logger.warning("[ERROR] Error leyendo afectacion cache: %s", exc)
    return None


def set_afectacion_cache(url: str, data: bytes) -> None:
    r = _get_client()
    if r is None:
        return
    key = f"afectacion:{hashlib.sha256(url.encode()).hexdigest()}"
    try:
        r.set(key, data, ex=86400)
        logger.debug(f"[CACHE_SET] afectación ({len(data)} bytes, 24h TTL)")
    except Exception as exc:
        logger.warning("[ERROR] Error guardando afectacion cache: %s", exc)


# ─── Session Token Cache ────────────────────────────────────────


def get_session_token() -> tuple[Optional[str], Optional[str]]:
    r = _get_client()
    if r is None:
        return None, None
    try:
        data = _string_get(r, "session:api:token")
        if data is None:
            logger.debug("[CACHE_MISS] session token")
            return None, None
        payload = json.loads(data)
        logger.debug("[CACHE_HIT] session token recuperado")
        return payload.get("token"), payload.get("exp")
    except Exception as exc:
        logger.warning("[ERROR] Error leyendo session token: %s", exc)
    return None, None


def set_session_token(token: str, exp_iso: Optional[str]) -> None:
    r = _get_client()
    if r is None:
        return
    ttl = 3600
    if exp_iso:
        try:
            exp_dt = datetime.fromisoformat(exp_iso)
            remaining = int((exp_dt - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds())
            ttl = max(60, remaining)
        except ValueError:
            pass
    try:
        _string_set(
            r,
            "session:api:token",
            json.dumps({"token": token, "exp": exp_iso}),
            ex=ttl,
        )
        logger.debug(f"[CACHE_SET] session token ({ttl}s TTL)")
    except Exception as exc:
        logger.warning("[ERROR] Error guardando session token: %s", exc)


def delete_session_token() -> None:
    r = _get_client()
    if r is None:
        return
    try:
        r.delete("session:api:token")
        logger.debug("[CACHE_DELETE] session token")
    except Exception as exc:
        logger.warning("[ERROR] Error eliminando session token: %s", exc)


# ─── Config ─────────────────────────────────────────────────────


def get_config() -> dict:
    r = _get_client()
    if r is None:
        return {}
    try:
        data = _string_get(r, "config:global")
        if data is None:
            return {}
        payload = json.loads(data)
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        logger.warning("[ERROR] Error leyendo config: %s", exc)
    return {}


def set_config(cfg: dict) -> None:
    r = _get_client()
    if r is None:
        return
    try:
        _string_set(r, "config:global", json.dumps(cfg))
    except Exception as exc:
        logger.warning("[ERROR] Error guardando config: %s", exc)
