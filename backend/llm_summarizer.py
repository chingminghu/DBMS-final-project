import json
import os
import re
import urllib.request
from dotenv import load_dotenv
from typing import List

load_dotenv()

from .models import ClusterSummaryResponse, GraphEdge, TableMeta


SUMMARY_CACHE: dict[str, ClusterSummaryResponse] = {}


def _debug_log(event_type: str, message: str, payload=None):
    print(f"\n[SchemaLens LLM][{event_type}] {message}")
    if payload is not None:
        print(f"[SchemaLens LLM][payload] {payload}")


def _fallback_summary(
    database_id: str,
    cluster_id: str,
    tables: List[TableMeta],
) -> ClusterSummaryResponse:
    table_names = [table.name for table in tables]
    joined = " ".join(table_names).lower()

    keyword_rules = [
        (["order", "payment", "shipment", "customer"], "Order and Customer Management", "This module is mainly related to customers, orders, payments, and shipments."),
        (["product", "category", "supplier", "stock", "inventory"], "Product and Inventory Management", "This module is mainly related to products, categories, suppliers, and inventory records."),
        (["student", "teacher", "course", "enrollment", "attendance", "department"], "Teaching and Enrollment Management", "This module is mainly related to departments, teachers, students, courses, enrollments, and attendance."),
        (["ticket", "reply", "review", "support", "feedback"], "Support and Feedback Management", "This module is mainly related to support tickets, replies, and product reviews."),
        (["user", "profile", "login", "account", "session"], "User Account Management", "This module is mainly related to user accounts, profiles, and login records."),
        (["log", "audit", "event"], "System Log Management", "This module is mainly related to logs, audits, and event tracking."),
    ]

    module_name = "Schema Cluster"
    description = "This module contains multiple related tables and likely represents one functional area."

    for keywords, name, desc in keyword_rules:
        if any(keyword in joined for keyword in keywords):
            module_name = name
            description = desc
            break

    key_tables = table_names[:3]

    _debug_log(
        "fallback_summary",
        f"Using fallback summary for cluster={cluster_id}",
        {"tables": table_names, "module_name": module_name},
    )

    return ClusterSummaryResponse(
        database_id=database_id,
        cluster_id=cluster_id,
        module_name_zh=module_name,
        description_zh=description,
        key_tables=key_tables,
        reason_zh=f"This cluster contains {len(table_names)} table(s). The key table(s) are: {', '.join(key_tables)}.",
        source="fallback",
    )


def _build_prompt(tables: List[TableMeta], edges: List[GraphEdge]) -> str:
    table_lines = []
    for table in tables:
        columns = ", ".join([f"{col.name}:{col.type or 'UNKNOWN'}" for col in table.columns])
        pk = ", ".join(table.primary_keys) if table.primary_keys else "None"
        table_lines.append(f"- {table.name}({columns}); PK: {pk}")

    edge_lines = []
    for edge in edges:
        edge_lines.append(f"- {edge.label}")

    return f"""
You are a database schema analysis assistant. Based on the following SQLite schema subgraph, infer the functional module name and purpose of this group of tables.

Return valid JSON only. Do not use markdown. Do not add extra commentary.

Tables:
{chr(10).join(table_lines)}

Relationships:
{chr(10).join(edge_lines) if edge_lines else "- No foreign key relationships inside this cluster."}

Return JSON in this format:
{{
  "module_name_zh": "A concise English module name, ideally within 2 to 6 words",
  "description_zh": "One or two English sentences describing the purpose of the module",
  "key_tables": ["1 to 3 most important tables"],
  "reason_zh": "Explain in English why these tables belong to the same module"
}}
""".strip()


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in LLM response.")
    return json.loads(match.group(0))


def _call_openai(prompt: str) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    model = os.getenv("SCHEMALENS_LLM_MODEL", "gpt-4o-mini")
    _debug_log("llm_prompt", f"Calling OpenAI model={model}", {"prompt": prompt})

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You summarize database schema clusters. Always return valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))

    content = body["choices"][0]["message"]["content"]
    _debug_log("llm_raw_response", "Received raw LLM output", {"content": content})
    return _extract_json(content)


def summarize_cluster(
    database_id: str,
    cluster_id: str,
    tables: List[TableMeta],
    edges: List[GraphEdge],
) -> ClusterSummaryResponse:
    cache_key = f"{database_id}:{cluster_id}"
    if cache_key in SUMMARY_CACHE:
        _debug_log("summary_cache_hit", f"Using cached summary for {cache_key}")
        return SUMMARY_CACHE[cache_key]

    fallback = _fallback_summary(database_id, cluster_id, tables)

    _debug_log(
        "summary_start",
        f"Start summarizing cluster={cluster_id}",
        {"database_id": database_id, "tables": [table.name for table in tables], "edge_count": len(edges)},
    )

    try:
        prompt = _build_prompt(tables, edges)
        data = _call_openai(prompt)

        result = ClusterSummaryResponse(
            database_id=database_id,
            cluster_id=cluster_id,
            module_name_zh=str(data.get("module_name_zh") or fallback.module_name_zh),
            description_zh=str(data.get("description_zh") or fallback.description_zh),
            key_tables=list(data.get("key_tables") or fallback.key_tables)[:3],
            reason_zh=str(data.get("reason_zh") or fallback.reason_zh),
            source="llm",
        )
        _debug_log(
            "summary_success",
            f"LLM summary generated for cluster={cluster_id}",
            result.model_dump(),
        )
    except Exception as exc:
        _debug_log(
            "summary_error",
            f"LLM summary failed for cluster={cluster_id}; using fallback",
            {"error": str(exc)},
        )
        result = fallback

    SUMMARY_CACHE[cache_key] = result
    return result
