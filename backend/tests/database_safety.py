"""Reject unsafe targets before a fixture performs any destructive DDL."""

from pathlib import Path

from sqlalchemy.engine import make_url


def database_identity(url: str) -> tuple:
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite":
        return (
            "sqlite",
            str(Path(parsed.database).resolve()) if parsed.database != ":memory:" else ":memory:",
        )
    host = "loopback" if parsed.host in {None, "localhost", "127.0.0.1", "::1"} else parsed.host
    return (parsed.get_backend_name(), host, parsed.port or 5432, parsed.database)


def validate_test_target(test_url: str, application_url: str, allow_external: bool) -> None:
    """Require an explicit opt-in and a separately named disposable external database."""
    if database_identity(test_url) == database_identity(application_url):
        raise ValueError("Refusing destructive tests against the application database")
    target, application = make_url(test_url), make_url(application_url)
    if (
        target.get_backend_name() != "sqlite"
        and target.get_backend_name() == application.get_backend_name()
        and target.database == application.database
    ):
        raise ValueError(
            "Refusing a test database with the application's name; host aliases cannot prove isolation"
        )
    if not allow_external:
        raise ValueError("External test databases require DOCVERIFY_ALLOW_EXTERNAL_TEST_DB=1")
    parsed = make_url(test_url)
    name = (
        Path(parsed.database or "").stem
        if parsed.get_backend_name() == "sqlite"
        else parsed.database or ""
    )
    if not (name.endswith("_test") or "_test_" in name or name.startswith("test_")):
        raise ValueError(
            "External test target must have a dedicated test name (for example docverify_test)"
        )
