"""SQLite schema definition and DDL statements for the mappings store."""

from __future__ import annotations

SCHEMA_VERSION = 2

CREATE_TABLE_MAPPINGS = """
CREATE TABLE IF NOT EXISTS mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    devicetypeid INTEGER,
    eid TEXT,
    event_category TEXT,
    qid INTEGER,
    event_name TEXT,
    description TEXT,
    severity INTEGER,
    low_level_category TEXT,
    high_level_category TEXT
);
"""

CREATE_INDEX_QID = "CREATE INDEX IF NOT EXISTS idx_mappings_qid ON mappings(qid);"
CREATE_INDEX_EID = "CREATE INDEX IF NOT EXISTS idx_mappings_eid ON mappings(eid);"
CREATE_INDEX_DEVICE = (
    "CREATE INDEX IF NOT EXISTS idx_mappings_device ON mappings(devicetypeid);"
)
CREATE_INDEX_CATEGORY = (
    "CREATE INDEX IF NOT EXISTS idx_mappings_category ON mappings(event_category);"
)
CREATE_INDEX_LOW_LEVEL_CATEGORY = (
    "CREATE INDEX IF NOT EXISTS idx_mappings_llc ON mappings(low_level_category);"
)
CREATE_INDEX_HIGH_LEVEL_CATEGORY = (
    "CREATE INDEX IF NOT EXISTS idx_mappings_hlc ON mappings(high_level_category);"
)

ALL_DDL_STATEMENTS = (
    CREATE_TABLE_MAPPINGS,
    CREATE_INDEX_QID,
    CREATE_INDEX_EID,
    CREATE_INDEX_DEVICE,
    CREATE_INDEX_CATEGORY,
)

# Columns added after the original v1 schema. Applied via ALTER TABLE for
# databases created before this column existed; already present in
# CREATE_TABLE_MAPPINGS for brand-new databases, so this is a no-op there.
_MIGRATED_COLUMNS = (
    ("severity", "INTEGER"),
    ("low_level_category", "TEXT"),
    ("high_level_category", "TEXT"),
)

_POST_MIGRATION_INDEXES = (
    CREATE_INDEX_LOW_LEVEL_CATEGORY,
    CREATE_INDEX_HIGH_LEVEL_CATEGORY,
)


def initialize_schema(connection) -> None:
    """Create the mappings table and its indexes if they do not exist.

    Also migrates older databases (created before ``severity``/
    ``low_level_category``/``high_level_category`` existed) by adding the
    missing columns in place, without touching existing data.
    """
    cursor = connection.cursor()
    for statement in ALL_DDL_STATEMENTS:
        cursor.execute(statement)

    existing_columns = {row[1] for row in cursor.execute("PRAGMA table_info(mappings);")}
    for column_name, column_type in _MIGRATED_COLUMNS:
        if column_name not in existing_columns:
            cursor.execute(f"ALTER TABLE mappings ADD COLUMN {column_name} {column_type};")

    for statement in _POST_MIGRATION_INDEXES:
        cursor.execute(statement)

    connection.commit()
