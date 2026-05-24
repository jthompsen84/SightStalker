"""
sightstalker.persistence.alembic — Alembic configuration helper.

Builds an Alembic ``Config`` that points at the package-contained migration
directory using ``importlib.resources`` so it works from an installed wheel or
sdist (not just a source checkout). The database URL is set on the config but
never printed; any error text routes through ``sanitize_database_url``.
"""

from __future__ import annotations

from importlib import resources

from alembic.config import Config

from sightstalker.persistence.database import sanitize_database_url


def _migrations_path() -> str:
    """Return the filesystem path to the packaged migrations directory."""
    resource = resources.files("sightstalker.persistence") / "migrations"
    # ``as_file`` would give a temp path for zipped packages; migrations are
    # shipped as regular files in both wheel and sdist, so a direct str works.
    return str(resource)


def make_alembic_config(database_url: str) -> Config:
    """Create an Alembic ``Config`` for ``database_url``.

    Resolves packaged migrations via ``importlib.resources``. Does not print
    the URL. Raises with a sanitized URL on failure.
    """
    try:
        script_location = _migrations_path()
        config = Config()
        config.set_main_option("script_location", script_location)
        config.set_main_option("sqlalchemy.url", database_url)
        return config
    except Exception as exc:  # noqa: BLE001 - sanitize and re-raise
        safe = sanitize_database_url(database_url)
        raise RuntimeError(
            f"failed to build alembic config for {safe}: {type(exc).__name__}"
        ) from None
