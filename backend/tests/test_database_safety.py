import pytest

from .database_safety import validate_test_target


def test_application_target_refused_even_with_opt_in():
    with pytest.raises(ValueError, match="application database"):
        validate_test_target(
            "postgresql://other:other@127.0.0.1/docverify_test",
            "postgresql+psycopg://app:app@localhost/docverify_test",
            True,
        )


def test_external_requires_dedicated_target_and_opt_in():
    with pytest.raises(ValueError, match="opt-in|require"):
        validate_test_target(
            "postgresql://localhost/docverify_test", "postgresql://localhost/docverify", False
        )
    with pytest.raises(ValueError, match="dedicated"):
        validate_test_target(
            "postgresql://localhost/production", "postgresql://localhost/docverify", True
        )
    validate_test_target(
        "postgresql://localhost/docverify_test", "postgresql://localhost/docverify", True
    )


def test_sqlite_same_path_refused(tmp_path):
    path = tmp_path / "app_test.db"
    with pytest.raises(ValueError, match="application database"):
        validate_test_target(f"sqlite:///{path}", f"sqlite:///{path.parent}/./{path.name}", True)


def test_host_alias_cannot_bypass_application_database_guard():
    with pytest.raises(ValueError, match="application"):
        validate_test_target(
            "postgresql://localhost/docverify_test", "postgresql://db/docverify_test", True
        )
