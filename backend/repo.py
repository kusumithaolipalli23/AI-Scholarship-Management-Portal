"""
Repository factory. app.py should call `get_repo()` once at startup and use
the returned object for all data access, instead of talking to sqlite3 or
Supabase directly. This is what makes DB_BACKEND=sqlite|supabase a one-line
switch in .env.
"""
import logging

from config import config

logger = logging.getLogger("scholarai.repo")

_repo_instance = None


def get_repo():
    global _repo_instance
    if _repo_instance is not None:
        return _repo_instance

    if config.DB_BACKEND == "supabase":
        from repo_supabase import SupabaseRepo
        logger.info("Using Supabase repository backend")
        _repo_instance = SupabaseRepo()
    else:
        from repo_sqlite import SQLiteRepo
        logger.info("Using SQLite repository backend (default)")
        _repo_instance = SQLiteRepo()

    _repo_instance.init()
    return _repo_instance
