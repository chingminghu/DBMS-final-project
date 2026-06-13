from pathlib import Path
from typing import Dict, List

from .models import TableMeta

UPLOAD_DIR = Path("uploaded_dbs")
UPLOAD_DIR.mkdir(exist_ok=True)

SCHEMA_CACHE: Dict[str, List[TableMeta]] = {}
DATABASE_FILES: Dict[str, Path] = {}
DATABASE_FILENAMES: Dict[str, str] = {}
