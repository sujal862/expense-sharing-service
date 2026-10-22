from sqlalchemy.engine import make_url


def validate_test_url(test_url: str, development_url: str) -> str:
    test = make_url(test_url)
    development = make_url(development_url)
    if (
        test.drivername != "mysql+asyncmy"
        or test.database != "expense_sharing_test"
        or test.username != "expense_test"
        or test.database == development.database
    ):
        raise ValueError(
            "Integration tests require mysql+asyncmy, database expense_sharing_test, "
            "user expense_test, and a database different from development"
        )
    return test_url
