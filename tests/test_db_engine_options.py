"""Engine arguments per database URL. No database is contacted."""
from backend.app.db.database import engine_options


def test_sqlite_gets_file_settings_and_no_pool_arguments():
    o = engine_options("sqlite+aiosqlite:///./x.db")
    assert o["connect_args"]["check_same_thread"] is False and "pool_size" not in o


def test_postgres_gets_a_small_pool_and_no_statement_cache():
    o = engine_options("postgresql+asyncpg://u:p@pooler.example.com:6543/postgres?ssl=require")
    assert o["pool_size"] == 3 and o["max_overflow"] == 2
    assert o["connect_args"] == {"statement_cache_size": 0}      # the pooler's transaction mode cannot serve prepared statements


def test_pool_size_is_configurable():
    o = engine_options("postgresql+asyncpg://u:p@h/db", pool_size=1, max_overflow=0)
    assert (o["pool_size"], o["max_overflow"]) == (1, 0)
