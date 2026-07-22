"""Run alembic migrations to head and exit.

Entrypoint for the Fly release command (see deploy/fly/backend.fly.toml): the
hosted app skips in-process migrations (EPMW_STARTUP_MIGRATIONS=false) so the
web machine can open its listening socket immediately instead of migrating
inside the health-check window.

Usage: python -m scripts.migrate
"""

from __future__ import annotations

from app.db.init import run_migrations
from app.logging import configure_logging, get_logger


def main() -> None:
    configure_logging("INFO", json_output=True)
    log = get_logger(__name__)
    log.info("migrate_start")
    run_migrations()
    log.info("migrate_done")


if __name__ == "__main__":
    main()
