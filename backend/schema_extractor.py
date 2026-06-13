import sqlite3
from pathlib import Path
from typing import List

from .models import ColumnMeta, ForeignKeyMeta, TableMeta


def connect_sqlite(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def validate_sqlite_file(db_path: Path) -> None:
    try:
        conn = connect_sqlite(db_path)
        conn.execute("SELECT name FROM sqlite_master LIMIT 1;").fetchall()
        conn.close()
    except sqlite3.DatabaseError as exc:
        raise ValueError("Uploaded file is not a valid SQLite database.") from exc


def get_user_tables(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name;
        """
    ).fetchall()
    return [row["name"] for row in rows]


def get_columns(conn: sqlite3.Connection, table_name: str) -> List[ColumnMeta]:
    rows = conn.execute(f'PRAGMA table_info("{table_name}");').fetchall()
    columns: List[ColumnMeta] = []
    for row in rows:
        pk_pos = int(row["pk"])
        columns.append(
            ColumnMeta(
                name=row["name"],
                type=row["type"] or "",
                not_null=bool(row["notnull"]),
                default_value=None if row["dflt_value"] is None else str(row["dflt_value"]),
                primary_key_position=pk_pos,
                is_primary_key=pk_pos > 0,
            )
        )
    return columns


def get_foreign_keys(conn: sqlite3.Connection, table_name: str) -> List[ForeignKeyMeta]:
    rows = conn.execute(f'PRAGMA foreign_key_list("{table_name}");').fetchall()
    foreign_keys: List[ForeignKeyMeta] = []
    for row in rows:
        foreign_keys.append(
            ForeignKeyMeta(
                id=int(row["id"]),
                seq=int(row["seq"]),
                table=row["table"],
                from_column=row["from"],
                to_column=row["to"],
                on_update=row["on_update"],
                on_delete=row["on_delete"],
                match=row["match"],
            )
        )
    return foreign_keys


def get_row_count(conn: sqlite3.Connection, table_name: str) -> int | None:
    try:
        row = conn.execute(f'SELECT COUNT(*) AS cnt FROM "{table_name}";').fetchone()
        return int(row["cnt"])
    except sqlite3.DatabaseError:
        return None


def extract_schema(db_path: Path) -> List[TableMeta]:
    validate_sqlite_file(db_path)
    conn = connect_sqlite(db_path)
    try:
        table_names = get_user_tables(conn)
        tables: List[TableMeta] = []
        for table_name in table_names:
            columns = get_columns(conn, table_name)
            primary_keys = [
                col.name
                for col in sorted(columns, key=lambda c: c.primary_key_position)
                if col.is_primary_key
            ]
            foreign_keys = get_foreign_keys(conn, table_name)
            row_count = get_row_count(conn, table_name)
            tables.append(
                TableMeta(
                    name=table_name,
                    columns=columns,
                    primary_keys=primary_keys,
                    foreign_keys=foreign_keys,
                    row_count=row_count,
                )
            )
        return tables
    finally:
        conn.close()
