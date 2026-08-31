"""Compatibility module; operational state is now stored in PostgreSQL."""

from .db import *  # noqa: F401,F403

init_state = init_db
