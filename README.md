# SchemaLens Step 1：SQLite Schema Extraction API

這是第一步 MVP：使用者上傳 SQLite `.db` / `.sqlite` / `.sqlite3` 檔案後，FastAPI 後端會擷取：

- tables
- columns
- primary keys
- foreign keys
- row count

目前還沒有前端與 graph visualization，這一步先確認「資料庫 schema 可以被正確讀出來」。

---

## 1. 安裝環境

```bash
cd sqlite_schema_lens_step1
python -m venv .venv
```

### Windows PowerShell

```bash
.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
source .venv/bin/activate
```

接著安裝套件：

```bash
pip install -r requirements.txt
```

---

## 2. 啟動後端

```bash
uvicorn backend.main:app --reload
```

啟動後打開：

```text
http://127.0.0.1:8000/docs
```

你會看到 Swagger UI，可以直接測試 `/api/databases/upload`。

---

## 3. API

### Health check

```http
GET /
```

### Upload SQLite database

```http
POST /api/databases/upload
```

Form-data:

```text
file: your_database.db
```

回傳範例：

```json
{
  "database_id": "db_xxxxx",
  "filename": "chinook.db",
  "table_count": 11,
  "foreign_key_count": 12,
  "tables": [
    {
      "name": "Album",
      "columns": [
        {
          "name": "AlbumId",
          "type": "INTEGER",
          "not_null": true,
          "default_value": null,
          "primary_key_position": 1,
          "is_primary_key": true
        }
      ],
      "primary_keys": ["AlbumId"],
      "foreign_keys": [],
      "row_count": 347
    }
  ]
}
```

---

## 4. 下一步

Step 2 會把目前的 schema metadata 轉成 graph JSON：

- node = table
- edge = foreign key
- node attributes = columns, primary keys, row count
- edge attributes = from_column, to_table, to_column
```
