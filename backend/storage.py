import json
from pathlib import Path
from typing import Dict, List, Optional

from .models import TableMeta

UPLOAD_DIR = Path("uploaded_dbs")
UPLOAD_DIR.mkdir(exist_ok=True)

METADATA_PATH = UPLOAD_DIR / "metadata.json"

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
