#!/usr/bin/env python3
"""
Peewee Migration System — DB-agnostic, single-file, CLI-driven.

Works with any database backend supported by Peewee (SQLite, PostgreSQL, MySQL)
via the Proxy already configured in systems.db.

Usage:
    python migrations.py init          — Create the migrations tracking table
    python migrations.py make [name]   — Auto-detect schema changes and generate a migration
    python migrations.py migrate       — Apply all pending migrations
    python migrations.py rollback [n]  — Rollback the last n migrations (default 1)
    python migrations.py status        — Show applied / pending migrations
    python migrations.py history       — Full migration history
    python migrations.py reset         — Reset DB to current ORM state (⚠ destroys data)

As last point, im not very proud, buut, this was made with Claude (Opus 4.6) help and I must say... It's a beautiful work...

---

Documentation for anyone:

# Dev changes a model in systems/orm.py, then:
python migrations.py make "added avatar field to user"
python migrations.py migrate
git add migrations/ && git commit -m "migration: added avatar field to user"

# Another dev pulls, then:
python migrations.py migrate   # applies any new migration files
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import textwrap
from collections import OrderedDict
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Bootstrap: make sure the DB proxy is loaded before anything touches peewee
# ---------------------------------------------------------------------------
from systems.db import db, proxy_load
proxy_load()

from peewee import (
    Model, CharField, TextField, DateTimeField, IntegerField, BooleanField,
    AutoField, SQL, CompositeKey, ForeignKeyField, UUIDField, IPField,
    ManyToManyField, FloatField, BigIntegerField, SmallIntegerField,
    DecimalField, BlobField, BitField, BigBitField, TimestampField,
    DateField, TimeField, fn,
)
from playhouse.migrate import (
    SchemaMigrator, migrate as pw_migrate,
    SqliteMigrator, PostgresqlMigrator,
)

# Try MySQL migrator — only available if mysql driver installed
try:
    from playhouse.migrate import MySQLMigrator
except ImportError:
    MySQLMigrator = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
UTC = dt.timezone.utc

# ---------------------------------------------------------------------------
# Migration tracking model (lives in the same DB)
# ---------------------------------------------------------------------------
class MigrationRecord(Model):
    """Tracks which migrations have been applied."""
    id          = AutoField()
    name        = CharField(unique=True)
    applied_at  = DateTimeField(default=lambda: dt.datetime.now(UTC))
    snapshot    = TextField(default="{}")  # JSON snapshot *after* this migration
    operations  = TextField(default="[]") # JSON list of operations

    class Meta:
        database = db
        table_name = "_migrations"


# ---------------------------------------------------------------------------
# Helpers: get the right migrator for the active backend
# ---------------------------------------------------------------------------
def _get_migrator() -> SchemaMigrator:
    """Return a SchemaMigrator matching the active database backend."""
    db_class_name = type(db.obj).__name__.lower() if db.obj else ""
    if "sqlite" in db_class_name:
        return SqliteMigrator(db)
    elif "postgres" in db_class_name:
        return PostgresqlMigrator(db)
    elif "mysql" in db_class_name:
        if MySQLMigrator is None:
            raise RuntimeError("MySQL migrator not available — install a MySQL driver.")
        return MySQLMigrator(db)
    else:
        # Fallback: try Postgres-style (most generic SQL)
        print(f"[!] Unknown DB backend '{db_class_name}', falling back to PostgresqlMigrator.")
        return PostgresqlMigrator(db)


# ---------------------------------------------------------------------------
# Helpers: discover all ORM models from systems.orm
# ---------------------------------------------------------------------------
def _discover_models() -> list[type[Model]]:
    """Import systems.orm and return all concrete Model subclasses (excluding BaseModel itself)."""
    import systems.orm as orm_module

    base = getattr(orm_module, "BaseModel", Model)
    models: list[type[Model]] = []

    for attr_name in dir(orm_module):
        obj = getattr(orm_module, attr_name)
        if (
            isinstance(obj, type)
            and issubclass(obj, Model)
            and obj is not base
            and obj is not Model
            and hasattr(obj, "_meta")
            and obj._meta.database is db
        ):
            models.append(obj)

    # Exclude our own tracking table
    models = [m for m in models if m._meta.table_name != "_migrations"]
    return models


# ---------------------------------------------------------------------------
# Schema introspection — build a serialisable "snapshot" of the ORM state
# ---------------------------------------------------------------------------

# Maps peewee field classes to short string names for JSON serialisation
_FIELD_TYPE_MAP: dict[type, str] = {
    AutoField: "auto", IntegerField: "int", BigIntegerField: "bigint",
    SmallIntegerField: "smallint", FloatField: "float", DecimalField: "decimal",
    CharField: "char", TextField: "text", BlobField: "blob",
    BooleanField: "bool", DateTimeField: "datetime", DateField: "date",
    TimeField: "time", TimestampField: "timestamp",
    UUIDField: "uuid", IPField: "ip", ForeignKeyField: "fk",
    BitField: "bit", BigBitField: "bigbit",
}

def _field_type_name(field) -> str:
    for cls in type(field).__mro__:
        if cls in _FIELD_TYPE_MAP:
            return _FIELD_TYPE_MAP[cls]
    return type(field).__name__.lower()


def _serialize_field(field) -> dict[str, Any]:
    """Produce a JSON-safe dict describing a single field."""
    info: dict[str, Any] = {
        "type": _field_type_name(field),
        "null": field.null,
        "primary_key": field.primary_key,
        "unique": field.unique,
        "index": field.index if hasattr(field, 'index') else False,
    }
    if isinstance(field, CharField) and field.max_length:
        info["max_length"] = field.max_length
    if field.default is not None and not callable(field.default):
        info["default"] = field.default
    if isinstance(field, ForeignKeyField):
        info["rel_model"] = field.rel_model._meta.table_name
        info["rel_field"] = field.rel_field.name if field.rel_field else "id"
        info["on_delete"] = getattr(field, "on_delete", None)
        info["on_update"] = getattr(field, "on_update", None)
    return info


def _snapshot_model(model: type[Model]) -> dict[str, Any]:
    """Return a serialisable snapshot for one model/table."""
    fields: dict[str, dict] = {}
    for name, field in model._meta.fields.items():
        # Use the real DB column name (e.g. group_id, not group)
        col_name = field.column_name
        fields[col_name] = _serialize_field(field)

    # Build a mapping from field name -> column name for index/PK resolution
    _name_to_col = {name: field.column_name for name, field in model._meta.fields.items()}

    indexes = []
    if hasattr(model._meta, "indexes") and model._meta.indexes:
        for idx in model._meta.indexes:
            columns, unique = idx if isinstance(idx, tuple) else (idx, False)
            # Resolve field names to actual column names
            resolved = [_name_to_col.get(c, c) for c in columns]
            indexes.append({"columns": resolved, "unique": unique})

    composite_key = None
    if isinstance(model._meta.primary_key, CompositeKey):
        pk_names = list(model._meta.primary_key.field_names)
        composite_key = [_name_to_col.get(n, n) for n in pk_names]

    return {
        "table_name": model._meta.table_name,
        "fields": fields,
        "indexes": indexes,
        "composite_key": composite_key,
    }


def _take_snapshot() -> dict[str, dict]:
    """Full snapshot: {table_name: model_snapshot}."""
    models = _discover_models()
    snap: dict[str, dict] = {}
    for m in models:
        tbl = m._meta.table_name
        snap[tbl] = _snapshot_model(m)
    return snap


# ---------------------------------------------------------------------------
# Diff engine — compare two snapshots and produce a list of operations
# ---------------------------------------------------------------------------

def _diff_snapshots(old_snap: dict, new_snap: dict) -> list[dict]:
    """
    Compare old vs new snapshot and return a list of operation dicts:
        {"op": "create_table", "table": ...}
        {"op": "drop_table",   "table": ...}
        {"op": "add_column",   "table": ..., "column": ..., "field": ...}
        {"op": "drop_column",  "table": ..., "column": ...}
        {"op": "alter_column", "table": ..., "column": ..., "old": ..., "new": ...}
        {"op": "add_index",    "table": ..., "columns": ..., "unique": ...}
        {"op": "drop_index",   "table": ..., "columns": ..., "unique": ...}
    """
    ops: list[dict] = []

    old_tables = set(old_snap.keys())
    new_tables = set(new_snap.keys())

    # New tables
    for tbl in sorted(new_tables - old_tables):
        ops.append({"op": "create_table", "table": tbl, "fields": new_snap[tbl]["fields"],
                     "indexes": new_snap[tbl].get("indexes", []),
                     "composite_key": new_snap[tbl].get("composite_key")})

    # Dropped tables
    for tbl in sorted(old_tables - new_tables):
        ops.append({"op": "drop_table", "table": tbl, "fields": old_snap[tbl]["fields"]})

    # Modified tables
    for tbl in sorted(old_tables & new_tables):
        old_fields = old_snap[tbl].get("fields", {})
        new_fields = new_snap[tbl].get("fields", {})

        for col in sorted(set(new_fields) - set(old_fields)):
            ops.append({"op": "add_column", "table": tbl, "column": col, "field": new_fields[col]})

        for col in sorted(set(old_fields) - set(new_fields)):
            ops.append({"op": "drop_column", "table": tbl, "column": col, "field": old_fields[col]})

        for col in sorted(set(old_fields) & set(new_fields)):
            old_f = old_fields[col]
            new_f = new_fields[col]
            # Compare relevant attributes
            changes = {k: new_f[k] for k in new_f if old_f.get(k) != new_f.get(k)}
            if changes:
                ops.append({"op": "alter_column", "table": tbl, "column": col,
                             "old": old_f, "new": new_f, "changes": changes})

        # Index diff
        old_idx = {tuple(i["columns"]): i for i in old_snap[tbl].get("indexes", [])}
        new_idx = {tuple(i["columns"]): i for i in new_snap[tbl].get("indexes", [])}

        for key in set(new_idx) - set(old_idx):
            ops.append({"op": "add_index", "table": tbl, **new_idx[key]})

        for key in set(old_idx) - set(new_idx):
            ops.append({"op": "drop_index", "table": tbl, **old_idx[key]})

    return ops


# ---------------------------------------------------------------------------
# Reconstruct peewee field from serialised info (for executing migrations)
# ---------------------------------------------------------------------------

_REVERSE_FIELD_MAP: dict[str, type] = {
    "auto": AutoField, "int": IntegerField, "bigint": BigIntegerField,
    "smallint": SmallIntegerField, "float": FloatField, "decimal": DecimalField,
    "char": CharField, "text": TextField, "blob": BlobField,
    "bool": BooleanField, "datetime": DateTimeField, "date": DateField,
    "time": TimeField, "timestamp": TimestampField, "uuid": UUIDField,
    "ip": IPField, "bit": BitField, "bigbit": BigBitField,
}


def _reconstruct_field(info: dict):
    """Create a peewee Field instance from a serialised dict."""
    type_name = info["type"]

    if type_name == "fk":
        # For FK columns we use a bare IntegerField (or UUIDField) — the actual FK
        # constraint was already created with the table; adding/dropping the column
        # only needs the storage type.
        rel_field_type = info.get("rel_field", "id")
        # Most FK point to UUIDField PKs in this project
        field_cls = UUIDField if "uuid" in rel_field_type.lower() else IntegerField
        field = field_cls(null=info.get("null", False))
        field.column_name = info.get("column_name")
        return field

    field_cls = _REVERSE_FIELD_MAP.get(type_name, TextField)
    kwargs: dict[str, Any] = {"null": info.get("null", False)}
    if type_name == "char":
        kwargs["max_length"] = info.get("max_length", 255)
    if "default" in info and info["default"] is not None:
        kwargs["default"] = info["default"]
    return field_cls(**kwargs)


# ---------------------------------------------------------------------------
# Execute migration operations via playhouse.migrate
# ---------------------------------------------------------------------------

def _execute_operations(ops: list[dict], *, reverse: bool = False):
    """Apply (or reverse) a list of operation dicts."""
    migrator = _get_migrator()

    if reverse:
        ops = list(reversed(ops))

    for op_info in ops:
        op = op_info["op"]

        # When reversing, invert the operation
        if reverse:
            if op == "create_table":
                op = "drop_table"
            elif op == "drop_table":
                op = "create_table"
            elif op == "add_column":
                op = "drop_column"
            elif op == "drop_column":
                op = "add_column"
            elif op == "add_index":
                op = "drop_index"
            elif op == "drop_index":
                op = "add_index"
            # alter_column: swap old/new
            elif op == "alter_column":
                op_info = {**op_info, "old": op_info["new"], "new": op_info["old"]}

        table = op_info.get("table", "")

        try:
            if op == "create_table":
                _exec_create_table(op_info)
            elif op == "drop_table":
                _exec_drop_table(table)
            elif op == "add_column":
                field = _reconstruct_field(op_info.get("field", {}))
                pw_migrate(migrator.add_column(table, op_info["column"], field))
                print(f"    + column '{table}.{op_info['column']}'")
            elif op == "drop_column":
                pw_migrate(migrator.drop_column(table, op_info["column"]))
                print(f"    - column '{table}.{op_info['column']}'")
            elif op == "alter_column":
                _exec_alter_column(migrator, table, op_info)
            elif op == "add_index":
                cols = op_info.get("columns", [])
                unique = op_info.get("unique", False)
                pw_migrate(migrator.add_index(table, cols, unique=unique))
                print(f"    + index on '{table}' {cols} unique={unique}")
            elif op == "drop_index":
                cols = op_info.get("columns", [])
                idx_name = f"{table}_{'_'.join(cols)}"
                pw_migrate(migrator.drop_index(table, idx_name))
                print(f"    - index on '{table}' {cols}")
            else:
                print(f"    ? unknown operation '{op}', skipping.")
        except Exception as e:
            print(f"    [!] Error executing {op} on '{table}': {e}")
            raise


def _exec_create_table(op_info: dict):
    """Create a table from field definitions using raw SQL via peewee."""
    table = op_info["table"]
    fields = op_info.get("fields", {})
    composite_key = op_info.get("composite_key")

    col_defs = []
    for col_name, col_info in fields.items():
        col_defs.append(_col_definition_sql(col_name, col_info))

    if composite_key:
        quoted_pk = ', '.join(f'"{ c}"' for c in composite_key)
        col_defs.append(f"PRIMARY KEY ({quoted_pk})")

    sql = f"CREATE TABLE IF NOT EXISTS \"{table}\" (\n  " + ",\n  ".join(col_defs) + "\n);"
    db.execute_sql(sql)
    print(f"    ++ table '{table}'")

    # Indexes
    for idx in op_info.get("indexes", []):
        cols = idx.get("columns", [])
        unique = idx.get("unique", False)
        u = "UNIQUE " if unique else ""
        idx_name = f"idx_{table}_{'_'.join(cols)}"
        quoted_cols = ', '.join(f'"{ c}"' for c in cols)
        idx_sql = f"CREATE {u}INDEX IF NOT EXISTS \"{idx_name}\" ON \"{table}\" ({quoted_cols});"
        db.execute_sql(idx_sql)


def _exec_drop_table(table: str):
    db_name = type(db.obj).__name__.lower() if db.obj else "sqlite"
    cascade = " CASCADE" if "postgres" in db_name else ""
    db.execute_sql(f'DROP TABLE IF EXISTS "{table}"{cascade};')
    print(f"    -- table '{table}'")


def _col_definition_sql(col_name: str, col_info: dict) -> str:
    """Return a column definition SQL fragment."""
    type_name = col_info.get("type", "text")
    sql_type = _type_to_sql(type_name, col_info)
    parts = [f'"{col_name}" {sql_type}']

    if col_info.get("primary_key") and not col_info.get("type") == "auto":
        parts.append("PRIMARY KEY")
    if col_info.get("type") == "auto":
        # Use DB-native auto-increment
        db_name = type(db.obj).__name__.lower() if db.obj else "sqlite"
        if "sqlite" in db_name:
            parts = [f'"{col_name}" INTEGER PRIMARY KEY AUTOINCREMENT']
        else:
            parts = [f'"{col_name}" SERIAL PRIMARY KEY']
        return " ".join(parts)
    if not col_info.get("null", False):
        parts.append("NOT NULL")
    if col_info.get("unique"):
        parts.append("UNIQUE")
    if col_info.get("default") is not None:
        default = col_info["default"]
        if isinstance(default, str):
            parts.append(f"DEFAULT '{default}'")
        elif isinstance(default, bool):
            parts.append(f"DEFAULT {'TRUE' if default else 'FALSE'}")
        else:
            parts.append(f"DEFAULT {default}")
    if type_name == "fk":
        rel_model = col_info.get("rel_model", "")
        rel_field = col_info.get("rel_field", "id")
        if rel_model:
            parts.append(f'REFERENCES "{rel_model}" ("{rel_field}")')
            on_delete = col_info.get("on_delete")
            on_update = col_info.get("on_update")
            if on_delete:
                parts.append(f"ON DELETE {on_delete}")
            if on_update:
                parts.append(f"ON UPDATE {on_update}")
    return " ".join(parts)


def _type_to_sql(type_name: str, col_info: dict) -> str:
    """Map our short type names to SQL type strings."""
    db_name = type(db.obj).__name__.lower() if db.obj else "sqlite"
    is_pg = "postgres" in db_name

    mapping = {
        "auto": "SERIAL" if is_pg else "INTEGER",
        "int": "INTEGER",
        "bigint": "BIGINT",
        "smallint": "SMALLINT",
        "float": "REAL",
        "decimal": "DECIMAL",
        "char": f"VARCHAR({col_info.get('max_length', 255)})",
        "text": "TEXT",
        "blob": "BYTEA" if is_pg else "BLOB",
        "bool": "BOOLEAN",
        "datetime": "TIMESTAMP" if is_pg else "DATETIME",
        "date": "DATE",
        "time": "TIME",
        "timestamp": "TIMESTAMP" if is_pg else "DATETIME",
        "uuid": "UUID" if is_pg else "VARCHAR(40)",
        "ip": "INET" if is_pg else "VARCHAR(45)",
        "fk": "UUID" if is_pg else "VARCHAR(40)",  # FK storage for UUID PKs
        "bit": "INTEGER",
        "bigbit": "BYTEA" if is_pg else "BLOB",
    }
    return mapping.get(type_name, "TEXT")


def _exec_alter_column(migrator, table: str, op_info: dict):
    """Handle column alterations (null, type, default, rename)."""
    col = op_info["column"]
    changes = op_info.get("changes", {})

    if "null" in changes:
        if changes["null"]:
            pw_migrate(migrator.drop_not_null(table, col))
            print(f"    ~ '{table}.{col}' → nullable")
        else:
            pw_migrate(migrator.add_not_null(table, col))
            print(f"    ~ '{table}.{col}' → NOT NULL")

    if "type" in changes or "max_length" in changes:
        new_field = _reconstruct_field(op_info["new"])
        pw_migrate(migrator.alter_column_type(table, col, new_field))
        print(f"    ~ '{table}.{col}' type changed")

    if "default" in changes:
        new_default = changes.get("default")
        if new_default is not None:
            pw_migrate(migrator.alter_add_default(table, col, new_default))
        print(f"    ~ '{table}.{col}' default changed")

    if "unique" in changes:
        if changes["unique"]:
            pw_migrate(migrator.add_unique(table, col))
        print(f"    ~ '{table}.{col}' unique={changes['unique']}")

    if "index" in changes:
        if changes["index"]:
            pw_migrate(migrator.add_index(table, [col], unique=False))
        else:
            idx_name = f"{table}_{col}"
            try:
                pw_migrate(migrator.drop_index(table, idx_name))
            except Exception:
                pass
        print(f"    ~ '{table}.{col}' index={changes['index']}")


# ---------------------------------------------------------------------------
# Migration file management
# ---------------------------------------------------------------------------

def _ensure_migrations_dir():
    MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)
    init_file = MIGRATIONS_DIR / "__init__.py"
    if not init_file.exists():
        init_file.write_text("")


def _next_migration_number() -> int:
    existing = sorted(MIGRATIONS_DIR.glob("*.json"))
    if not existing:
        return 1
    # Extract leading digits from filename
    nums = []
    for p in existing:
        m = re.match(r"^(\d+)", p.stem)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _load_last_snapshot() -> dict:
    """Load the most recent snapshot.

    Checks both the DB (applied migrations) *and* existing migration files
    on disk so that running ``make`` twice without ``migrate`` in between
    does not generate duplicate operations.
    """
    # 1. Try the latest migration *file* on disk (covers unapplied ones)
    _ensure_migrations_dir()
    all_files = sorted(MIGRATIONS_DIR.glob("*.json"))
    if all_files:
        try:
            data = _load_migration_file(all_files[-1])
            snap = data.get("snapshot")
            if snap:
                return snap
        except Exception:
            pass

    # 2. Fallback: latest applied record in the DB
    try:
        last = (MigrationRecord
                .select()
                .order_by(MigrationRecord.id.desc())
                .limit(1)
                .get())
        return json.loads(last.snapshot)
    except MigrationRecord.DoesNotExist:
        return {}
    except Exception:
        return {}


def _save_migration_file(name: str, ops: list[dict], snapshot: dict) -> Path:
    _ensure_migrations_dir()
    num = _next_migration_number()
    filename = f"{num:04d}_{_slug(name)}.json"
    path = MIGRATIONS_DIR / filename
    data = {
        "name": f"{num:04d}_{_slug(name)}",
        "created_at": dt.datetime.now(UTC).isoformat(),
        "operations": ops,
        "snapshot": snapshot,
    }
    path.write_text(json.dumps(data, indent=2, default=str))
    return path


def _load_migration_file(path: Path) -> dict:
    return json.loads(path.read_text())


def _get_pending_migrations() -> list[Path]:
    """Return migration files not yet applied, in order."""
    _ensure_migrations_dir()
    applied = set()
    try:
        for rec in MigrationRecord.select(MigrationRecord.name):
            applied.add(rec.name)
    except Exception:
        pass

    all_files = sorted(MIGRATIONS_DIR.glob("*.json"))
    pending = []
    for f in all_files:
        data = _load_migration_file(f)
        if data.get("name") not in applied:
            pending.append(f)
    return pending


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

def cmd_init():
    """Create the _migrations tracking table."""
    db.create_tables([MigrationRecord], safe=True)
    _ensure_migrations_dir()
    print("[✓] Migration system initialised.")
    print(f"    Tracking table: _migrations")
    print(f"    Migrations dir: {MIGRATIONS_DIR}")


def cmd_make(name: str | None = None):
    """Generate a new migration by diffing the ORM against the last snapshot."""
    # Make sure tracking table exists
    db.create_tables([MigrationRecord], safe=True)

    old_snap = _load_last_snapshot()
    new_snap = _take_snapshot()
    ops = _diff_snapshots(old_snap, new_snap)

    if not ops:
        print("[·] No schema changes detected — nothing to migrate.")
        return

    if not name:
        # Generate a descriptive name
        creates = [o["table"] for o in ops if o["op"] == "create_table"]
        drops   = [o["table"] for o in ops if o["op"] == "drop_table"]
        alters  = list({o["table"] for o in ops if o["op"] in ("add_column", "drop_column", "alter_column")})
        parts = []
        if creates:
            parts.append("create_" + "_".join(creates[:3]))
        if drops:
            parts.append("drop_" + "_".join(drops[:3]))
        if alters:
            parts.append("alter_" + "_".join(alters[:3]))
        name = "_and_".join(parts) if parts else "auto"

    path = _save_migration_file(name, ops, new_snap)
    print(f"[✓] Migration created: {path.name}")
    print(f"    Operations ({len(ops)}):")
    for o in ops:
        _print_op_summary(o)


def cmd_migrate():
    """Apply all pending migrations in order."""
    db.create_tables([MigrationRecord], safe=True)

    pending = _get_pending_migrations()
    if not pending:
        print("[·] All migrations are already applied.")
        return

    print(f"[→] Applying {len(pending)} migration(s)...")
    for mf in pending:
        data = _load_migration_file(mf)
        mig_name = data["name"]
        ops = data.get("operations", [])
        snapshot = data.get("snapshot", {})

        print(f"\n  ▸ {mig_name} ({len(ops)} ops)")
        try:
            with db.atomic():
                _execute_operations(ops, reverse=False)
                MigrationRecord.create(
                    name=mig_name,
                    snapshot=json.dumps(snapshot, default=str),
                    operations=json.dumps(ops, default=str),
                )
            print(f"  ✓ {mig_name} applied.")
        except Exception as e:
            print(f"  ✗ {mig_name} FAILED: {e}")
            print("    Aborting remaining migrations.")
            return

    print(f"\n[✓] All {len(pending)} migration(s) applied successfully.")


def cmd_rollback(count: int = 1):
    """Rollback the last `count` applied migrations."""
    db.create_tables([MigrationRecord], safe=True)

    applied = list(
        MigrationRecord
        .select()
        .order_by(MigrationRecord.id.desc())
        .limit(count)
    )

    if not applied:
        print("[·] No migrations to rollback.")
        return

    print(f"[←] Rolling back {len(applied)} migration(s)...")
    for rec in applied:
        ops = json.loads(rec.operations)
        print(f"\n  ▸ {rec.name} ({len(ops)} ops)")
        try:
            with db.atomic():
                _execute_operations(ops, reverse=True)
                rec.delete_instance()
            print(f"  ✓ {rec.name} rolled back.")
        except Exception as e:
            print(f"  ✗ {rec.name} rollback FAILED: {e}")
            print("    Aborting remaining rollbacks.")
            return

    print(f"\n[✓] Rollback complete.")


def cmd_status():
    """Show applied and pending migrations."""
    db.create_tables([MigrationRecord], safe=True)
    _ensure_migrations_dir()

    applied_names = set()
    try:
        for rec in MigrationRecord.select(MigrationRecord.name, MigrationRecord.applied_at).order_by(MigrationRecord.id):
            applied_names.add(rec.name)
    except Exception:
        pass

    all_files = sorted(MIGRATIONS_DIR.glob("*.json"))

    print(f"{'Migration':<50} {'Status':<15}")
    print("─" * 65)

    if not all_files and not applied_names:
        print("  (no migrations found)")
        return

    for f in all_files:
        data = _load_migration_file(f)
        name = data.get("name", f.stem)
        if name in applied_names:
            print(f"  {name:<48} ✓ applied")
        else:
            print(f"  {name:<48} ○ pending")

    # Show applied migrations that no longer have files (orphaned)
    file_names = {_load_migration_file(f).get("name") for f in all_files}
    orphaned = applied_names - file_names
    for name in sorted(orphaned):
        print(f"  {name:<48} ⚠ orphaned (no file)")


def cmd_history():
    """Show full migration history from the DB."""
    db.create_tables([MigrationRecord], safe=True)

    records = list(
        MigrationRecord
        .select()
        .order_by(MigrationRecord.id)
    )
    if not records:
        print("[·] No migration history.")
        return

    print(f"{'#':<5} {'Migration':<45} {'Applied At':<25}")
    print("─" * 75)
    for rec in records:
        if rec.applied_at:
            applied = rec.applied_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(rec.applied_at, 'strftime') else str(rec.applied_at)[:19]
        else:
            applied = "?"
        print(f"  {rec.id:<3} {rec.name:<45} {applied}")


def cmd_reset():
    """Reset: drop everything, recreate from ORM. ⚠ DESTROYS DATA."""
    confirm = input("⚠  This will DROP all tables and recreate them. Type 'yes' to confirm: ")
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        return

    models = _discover_models()

    # Drop in reverse dependency order
    for m in reversed(models):
        try:
            db_name = type(db.obj).__name__.lower() if db.obj else "sqlite"
            cascade = " CASCADE" if "postgres" in db_name else ""
            db.execute_sql(f'DROP TABLE IF EXISTS "{m._meta.table_name}"{cascade};')
            print(f"  -- dropped '{m._meta.table_name}'")
        except Exception as e:
            print(f"  [!] Could not drop '{m._meta.table_name}': {e}")

    try:
        db_name = type(db.obj).__name__.lower() if db.obj else "sqlite"
        cascade = " CASCADE" if "postgres" in db_name else ""
        db.execute_sql(f'DROP TABLE IF EXISTS "_migrations"{cascade};')
    except Exception:
        pass

    # Recreate
    db.create_tables(models, safe=True)
    db.create_tables([MigrationRecord], safe=True)

    # Snapshot current state as migration 0
    snap = _take_snapshot()
    MigrationRecord.create(
        name="0000_initial_reset",
        snapshot=json.dumps(snap, default=str),
        operations=json.dumps([], default=str),
    )

    print("[✓] Database reset to current ORM state. Snapshot saved as 0000_initial_reset.")


def cmd_snapshot():
    """Print the current ORM snapshot (for debugging)."""
    snap = _take_snapshot()
    print(json.dumps(snap, indent=2, default=str))


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------

def _print_op_summary(op: dict):
    t = op.get("op", "?")
    tbl = op.get("table", "")
    col = op.get("column", "")
    if t == "create_table":
        cols = list(op.get("fields", {}).keys())
        print(f"    ++ CREATE TABLE '{tbl}' ({len(cols)} columns)")
    elif t == "drop_table":
        print(f"    -- DROP TABLE '{tbl}'")
    elif t == "add_column":
        ftype = op.get("field", {}).get("type", "?")
        print(f"    +  ADD COLUMN '{tbl}.{col}' ({ftype})")
    elif t == "drop_column":
        print(f"    -  DROP COLUMN '{tbl}.{col}'")
    elif t == "alter_column":
        changes = op.get("changes", {})
        print(f"    ~  ALTER COLUMN '{tbl}.{col}' → {changes}")
    elif t == "add_index":
        cols = op.get("columns", [])
        print(f"    +  ADD INDEX on '{tbl}' ({cols})")
    elif t == "drop_index":
        cols = op.get("columns", [])
        print(f"    -  DROP INDEX on '{tbl}' ({cols})")
    else:
        print(f"    ?  {t} on '{tbl}'")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="migrations.py",
        description="Peewee DB-agnostic migration system for systems.orm",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python migrations.py init                  Initialise migration tracking
              python migrations.py make                  Auto-detect changes and create migration
              python migrations.py make "add bio field"  Create migration with a custom name
              python migrations.py migrate               Apply all pending migrations
              python migrations.py rollback              Rollback the last migration
              python migrations.py rollback 3            Rollback the last 3 migrations
              python migrations.py status                Show applied / pending migrations
              python migrations.py history               Full migration history
              python migrations.py snapshot              Print current ORM snapshot (debug)
              python migrations.py reset                 ⚠ Nuke and recreate everything
        """),
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create the migrations tracking table and directory")
    p_make = sub.add_parser("make", help="Detect schema changes and generate a migration file")
    p_make.add_argument("name", nargs="?", default=None, help="Optional migration name")

    sub.add_parser("migrate", help="Apply all pending migrations")

    p_rb = sub.add_parser("rollback", help="Rollback the last N migrations")
    p_rb.add_argument("count", nargs="?", type=int, default=1, help="Number of migrations to rollback (default: 1)")

    sub.add_parser("status", help="Show applied and pending migrations")
    sub.add_parser("history", help="Show full migration history")
    sub.add_parser("snapshot", help="Print current ORM snapshot as JSON")
    sub.add_parser("reset", help="⚠ Drop all tables and recreate from ORM")

    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "make": lambda: cmd_make(args.name),
        "migrate": cmd_migrate,
        "rollback": lambda: cmd_rollback(args.count),
        "status": cmd_status,
        "history": cmd_history,
        "snapshot": cmd_snapshot,
        "reset": cmd_reset,
    }

    fn = commands.get(args.command)
    if fn:
        fn()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()