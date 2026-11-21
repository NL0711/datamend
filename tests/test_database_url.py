"""A host's postgres:// string is made usable with the async driver; SQLite and already-correct URLs are left alone."""
from backend.app.config import normalize_database_url as norm


def test_host_string_becomes_an_asyncpg_url_with_ssl():
    assert norm("postgres://u:p@h.example:5432/db?sslmode=require") == "postgresql+asyncpg://u:p@h.example:5432/db?ssl=require"
    assert norm("postgresql://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"


def test_other_urls_are_untouched():
    assert norm("sqlite+aiosqlite:///./datamend.db") == "sqlite+aiosqlite:///./datamend.db"
    assert norm("postgresql+asyncpg://u:p@h/db?ssl=require") == "postgresql+asyncpg://u:p@h/db?ssl=require"
    assert norm("  'postgres://u:p@h/db'  ") == "postgresql+asyncpg://u:p@h/db"
