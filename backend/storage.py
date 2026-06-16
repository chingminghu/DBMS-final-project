import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import TableMeta

UPLOAD_DIR = Path("uploaded_dbs")
UPLOAD_DIR.mkdir(exist_ok=True)

METADATA_PATH = UPLOAD_DIR / "metadata.json"
PREQUERY_CACHE_PATH = UPLOAD_DIR / "prequery_cache.json"

SCHEMA_CACHE: Dict[str, List[TableMeta]] = {}
DATABASE_FILES: Dict[str, Path] = {}
DATABASE_FILENAMES: Dict[str, str] = {}


def _read_metadata() -> Dict[str, dict]:
    if not METADATA_PATH.exists():
        return {}

    try:
        with METADATA_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, dict):
            return data
    except Exception:
        # A broken metadata file should not prevent the API from starting.
        return {}

    return {}


def _write_metadata(metadata: Dict[str, dict]) -> None:
    with METADATA_PATH.open("w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)


def register_database_file(database_id: str, path: Path, filename: str) -> None:
    DATABASE_FILES[database_id] = path
    DATABASE_FILENAMES[database_id] = filename

    metadata = _read_metadata()
    metadata[database_id] = {
        "database_id": database_id,
        "filename": filename,
        "stored_filename": path.name,
    }
    _write_metadata(metadata)


def load_registered_databases() -> None:
    """Load saved database metadata from disk into in-memory registries."""
    metadata = _read_metadata()
    changed = False

    for database_id, item in list(metadata.items()):
        stored_filename = item.get("stored_filename")
        filename = item.get("filename") or stored_filename or database_id

        if not stored_filename:
            metadata.pop(database_id, None)
            changed = True
            continue

        path = UPLOAD_DIR / stored_filename
        if not path.exists():
            metadata.pop(database_id, None)
            changed = True
            continue

        DATABASE_FILES[database_id] = path
        DATABASE_FILENAMES[database_id] = filename

    if changed:
        _write_metadata(metadata)


def list_registered_database_ids() -> List[str]:
    load_registered_databases()
    return sorted(DATABASE_FILES.keys(), key=lambda database_id: DATABASE_FILENAMES.get(database_id, database_id).lower())


def get_database_path(database_id: str) -> Optional[Path]:
    load_registered_databases()
    return DATABASE_FILES.get(database_id)


def _read_prequery_cache() -> Dict[str, dict]:
    if not PREQUERY_CACHE_PATH.exists():
        return {}

    try:
        with PREQUERY_CACHE_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, dict):
            return data
    except Exception:
        # A broken cache should not prevent databases from loading.
        return {}

    return {}


def _write_prequery_cache(cache: Dict[str, dict]) -> None:
    with PREQUERY_CACHE_PATH.open("w", encoding="utf-8") as file:
        json.dump(cache, file, ensure_ascii=False, indent=2)


def _prequery_db_fingerprint(path: Path) -> Dict[str, Any]:
    try:
        stat = path.stat()
        return {
            "stored_filename": path.name,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    except OSError:
        return {"stored_filename": path.name, "size": None, "mtime_ns": None}


def make_prequery_cache_key(database_id: str, params: Dict[str, Any], path: Path) -> str:
    payload = {
        "database_id": database_id,
        "params": params,
        "db": _prequery_db_fingerprint(path),
        "cache_version": 1,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def get_prequery_cache_result(database_id: str, params: Dict[str, Any], path: Path) -> Optional[Dict[str, Any]]:
    cache_key = make_prequery_cache_key(database_id, params, path)
    cache = _read_prequery_cache()
    item = cache.get(cache_key)

    if not isinstance(item, dict):
        return None
    if item.get("database_id") != database_id:
        return None
    if item.get("params") != params:
        return None
    if item.get("db") != _prequery_db_fingerprint(path):
        return None

    result = item.get("result")
    if not isinstance(result, dict):
        return None

    result = dict(result)
    result["cache_hit"] = True
    result["cache_key"] = cache_key
    result["cached_at"] = item.get("cached_at")
    return result


def save_prequery_cache_result(database_id: str, params: Dict[str, Any], path: Path, result: Dict[str, Any]) -> Dict[str, Any]:
    cache_key = make_prequery_cache_key(database_id, params, path)
    cached_at = datetime.now(timezone.utc).isoformat()

    result_to_store = dict(result)
    result_to_store["cache_hit"] = False
    result_to_store["cache_key"] = cache_key
    result_to_store["cached_at"] = cached_at

    cache = _read_prequery_cache()
    cache[cache_key] = {
        "database_id": database_id,
        "params": params,
        "db": _prequery_db_fingerprint(path),
        "cached_at": cached_at,
        "result": result_to_store,
    }
    _write_prequery_cache(cache)
    return result_to_store
