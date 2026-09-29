"""Explicit initialization and compatibility migrations for the account database."""

import config as le_config
from db import db as le_db


def initialize_database(app):
    with app.app_context():
        import sqlalchemy

        if str(le_config.DATABASE_URL or "").startswith("sqlite"):
            from sqlalchemy import event

            @event.listens_for(le_db.engine, "connect")
            def _set_sqlite_pragmas(dbapi_connection, _connection_record):
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA busy_timeout=5000")
                finally:
                    cursor.close()

        le_db.create_all()
        # Migrate: add Gemini token usage columns if missing
        for column_name in (
            "llm_tokens_used",
            "llm_prompt_tokens_used",
            "llm_output_tokens_used",
        ):
            try:
                le_db.session.execute(
                    sqlalchemy.text(f"SELECT {column_name} FROM api_usage LIMIT 1")
                )
            except Exception:
                le_db.session.rollback()
                try:
                    le_db.session.execute(
                        sqlalchemy.text(
                            f"ALTER TABLE api_usage ADD COLUMN {column_name} INTEGER DEFAULT 0"
                        )
                    )
                    le_db.session.commit()
                except Exception:
                    le_db.session.rollback()
        try:
            le_db.session.execute(
                sqlalchemy.text("SELECT password_length FROM users LIMIT 1")
            )
        except Exception:
            le_db.session.rollback()
            try:
                le_db.session.execute(
                    sqlalchemy.text(
                        "ALTER TABLE users ADD COLUMN password_length INTEGER DEFAULT 8"
                    )
                )
                le_db.session.commit()
            except Exception:
                le_db.session.rollback()
        try:
            le_db.session.execute(
                sqlalchemy.text("SELECT email_verified_at FROM users LIMIT 1")
            )
        except Exception:
            le_db.session.rollback()
            try:
                le_db.session.execute(
                    sqlalchemy.text(
                        "ALTER TABLE users ADD COLUMN email_verified_at DATETIME"
                    )
                )
                le_db.session.execute(
                    sqlalchemy.text(
                        "UPDATE users SET email_verified_at = CURRENT_TIMESTAMP WHERE email_verified_at IS NULL"
                    )
                )
                le_db.session.commit()
            except Exception:
                le_db.session.rollback()
        try:
            le_db.session.execute(
                sqlalchemy.text(
                    "SELECT cancel_at_period_end FROM subscriptions LIMIT 1"
                )
            )
        except Exception:
            le_db.session.rollback()
            try:
                le_db.session.execute(
                    sqlalchemy.text(
                        "ALTER TABLE subscriptions ADD COLUMN cancel_at_period_end BOOLEAN DEFAULT 0"
                    )
                )
                le_db.session.commit()
            except Exception:
                le_db.session.rollback()
        # Migrate entry_decomps to surface-form-only keying. Decomps are keyed by
        # (language, surface_form); rows with NULL surface_form were written under
        # the base entry's row_id and are contaminated (inflected-form decomps
        # bleeding onto stem lookups), so we delete them — they regenerate on demand.
        try:
            le_db.session.execute(
                sqlalchemy.text("SELECT surface_form FROM entry_decomps LIMIT 1")
            )
        except Exception:
            le_db.session.rollback()
            try:
                le_db.session.execute(
                    sqlalchemy.text(
                        "ALTER TABLE entry_decomps ADD COLUMN surface_form TEXT DEFAULT NULL"
                    )
                )
                le_db.session.commit()
            except Exception:
                le_db.session.rollback()
        try:
            le_db.session.execute(
                sqlalchemy.text(
                    "DELETE FROM entry_decomps WHERE surface_form IS NULL OR surface_form = ''"
                )
            )
            le_db.session.execute(
                sqlalchemy.text(
                    "DROP INDEX IF EXISTS uq_entry_decomp_lang_alias_row_surface"
                )
            )
            le_db.session.execute(
                sqlalchemy.text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_entry_decomp_lang_surface "
                    "ON entry_decomps(language, surface_form)"
                )
            )
            le_db.session.commit()
        except Exception:
            le_db.session.rollback()
        try:
            import gemini_dict

            gemini_dict.migrate_legacy_custom_entries()
            gemini_dict.ensure_custom_form_index()
        except Exception as exc:
            print(
                f"[WARN] Custom-entry SQLite migration failed: {type(exc).__name__}: {exc}"
            )
        try:

            def _table_exists(name: str) -> bool:
                return (
                    le_db.session.execute(
                        sqlalchemy.text(
                            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"
                        ),
                        {"name": name},
                    ).first()
                    is not None
                )

            def _column_exists(table: str, column: str) -> bool:
                if not _table_exists(table):
                    return False
                rows = (
                    le_db.session.execute(
                        sqlalchemy.text(f"PRAGMA table_info({table})")
                    )
                    .mappings()
                    .all()
                )
                return any(row.get("name") == column for row in rows)

            for table, required_column, sql in (
                (
                    "custom_dict_entries",
                    "owner_user_id",
                    "UPDATE custom_dict_entries SET owner_user_id = NULL WHERE owner_user_id IS NOT NULL",
                ),
                (
                    "entry_notes",
                    "user_id",
                    "UPDATE entry_notes SET user_id = NULL WHERE user_id IS NOT NULL",
                ),
                (
                    "entry_decomps",
                    "user_id",
                    "UPDATE entry_decomps SET user_id = NULL WHERE user_id IS NOT NULL",
                ),
                (
                    "custom_entry_deletion_votes",
                    None,
                    "DELETE FROM custom_entry_deletion_votes",
                ),
                ("gemini_deletion_votes", None, "DELETE FROM gemini_deletion_votes"),
                ("gemini_entry_owners", None, "DELETE FROM gemini_entry_owners"),
                ("synthetic_annotations", None, "DELETE FROM synthetic_annotations"),
                ("user_annotations", None, "DELETE FROM user_annotations"),
            ):
                if _table_exists(table) and (
                    not required_column or _column_exists(table, required_column)
                ):
                    le_db.session.execute(sqlalchemy.text(sql))
            le_db.session.commit()
        except Exception as exc:
            le_db.session.rollback()
            print(
                f"[WARN] Account-content attribution cleanup failed: {type(exc).__name__}: {exc}"
            )
