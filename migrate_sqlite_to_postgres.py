#!/usr/bin/env python3
"""
SQLite -> PostgreSQL migration utility.

Usage:
  python tools/migrate_sqlite_to_postgres.py \
    --sqlite-path instance/chat_history.db \
    --postgres-url "postgresql://user:pass@host:5432/dbname" \
    --truncate-target
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import sqlalchemy as sa


def _normalize_postgres_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if not url:
        return ""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _redact_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return url
        auth = ""
        if parsed.username:
            auth = parsed.username
            if parsed.password is not None:
                auth += ":***"
            auth += "@"
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        masked = parsed._replace(netloc=f"{auth}{host}{port}")
        return masked.geturl()
    except Exception:
        return url


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _parse_csv(value: str) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def _iter_batches(source_conn, table: sa.Table, batch_size: int):
    result = source_conn.execution_options(stream_results=True).execute(sa.select(table))
    batch: list[dict] = []
    for row in result.mappings():
        batch.append(dict(row))
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate data from SQLite to PostgreSQL.")
    parser.add_argument(
        "--sqlite-path",
        default=os.getenv("APP_DATABASE_PATH", "instance/chat_history.db"),
        help="Path to source sqlite .db file",
    )
    parser.add_argument(
        "--postgres-url",
        default=os.getenv("APP_DATABASE_URL", ""),
        help="Target PostgreSQL URL (supports postgresql:// or postgresql+psycopg://)",
    )
    parser.add_argument("--batch-size", type=int, default=1000, help="Rows per INSERT batch")
    parser.add_argument(
        "--truncate-target",
        action="store_true",
        help="Truncate target tables before loading data",
    )
    parser.add_argument(
        "--include-tables",
        default="",
        help="Comma-separated allow-list of table names",
    )
    parser.add_argument(
        "--exclude-tables",
        default="",
        help="Comma-separated deny-list of table names",
    )
    parser.add_argument("--echo-sql", action="store_true", help="Enable SQLAlchemy SQL echo")
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite_path).expanduser().resolve()
    if not sqlite_path.exists():
        print(f"[ERROR] SQLite source not found: {sqlite_path}")
        return 2

    postgres_url = _normalize_postgres_url(args.postgres_url)
    if not postgres_url or not postgres_url.startswith("postgresql"):
        print("[ERROR] --postgres-url is required and must start with postgresql://")
        return 2

    include_tables = _parse_csv(args.include_tables)
    exclude_tables = _parse_csv(args.exclude_tables)

    sqlite_engine = sa.create_engine(f"sqlite:///{sqlite_path}", echo=args.echo_sql)
    pg_engine = sa.create_engine(
        postgres_url,
        echo=args.echo_sql,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )

    source_md = sa.MetaData()
    source_md.reflect(bind=sqlite_engine)
    all_table_names = list(source_md.tables.keys())
    if not all_table_names:
        print("[WARN] No table found in sqlite source.")
        return 0

    selected_names: list[str] = []
    for name in all_table_names:
        if include_tables and name not in include_tables:
            continue
        if exclude_tables and name in exclude_tables:
            continue
        selected_names.append(name)

    if not selected_names:
        print("[WARN] No table selected after include/exclude filtering.")
        return 0

    target_md = sa.MetaData()
    for name in selected_names:
        source_md.tables[name].to_metadata(target_md)
    target_md.create_all(pg_engine)

    if args.truncate_target:
        truncate_names = [name for name in reversed(selected_names)]
        with pg_engine.begin() as conn:
            for name in truncate_names:
                conn.execute(sa.text(f"TRUNCATE TABLE {_quote_ident(name)} RESTART IDENTITY CASCADE"))
        print(f"[INFO] Truncated target tables: {', '.join(truncate_names)}")

    print(f"[INFO] Source sqlite: {sqlite_path}")
    print(f"[INFO] Target postgres: {_redact_url(postgres_url)}")
    print(f"[INFO] Tables: {', '.join(selected_names)}")

    total_copied = 0
    with sqlite_engine.connect() as source_conn:
        for name in selected_names:
            source_table = source_md.tables[name]
            target_table = target_md.tables[name]
            count_stmt = sa.select(sa.func.count()).select_from(source_table)
            source_count = int(source_conn.execute(count_stmt).scalar_one() or 0)
            copied = 0

            if source_count > 0:
                with pg_engine.begin() as target_conn:
                    for batch in _iter_batches(source_conn, source_table, max(1, args.batch_size)):
                        target_conn.execute(sa.insert(target_table), batch)
                        copied += len(batch)

            total_copied += copied
            print(f"[TABLE] {name}: copied {copied}/{source_count}")

    print(f"[DONE] Copied rows total: {total_copied}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

