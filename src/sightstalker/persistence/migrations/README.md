# SightStalker persistence migrations

Package-contained Alembic migrations for the SightStalker metadata database.

These migrations are shipped inside the installed package so they can be run
from a wheel or sdist without a source checkout. Build the Alembic config with:

```python
from sightstalker.persistence import make_alembic_config

config = make_alembic_config("sqlite+aiosqlite:///sightstalker.db")
```

The migration environment (`env.py`) is async-aware and supports
`sqlite+aiosqlite` URLs via `async_engine_from_config` + `connection.run_sync`.

The baseline revision `0001_persistence_1_initial` creates the `profiles`,
`sessions`, `runs`, `browser_contexts`, `artifacts`, and `health_records`
tables. All runtime foreign keys use restrictive (`RESTRICT`) delete behavior;
there is no cascade delete of run/session/artifact history.
