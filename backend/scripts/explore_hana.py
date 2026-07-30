"""Read-only schema discovery utility. It never prints credentials."""

from pprint import pprint

from app.config import get_settings
from app.services.hana_client import HanaClient


def main() -> None:
    client = HanaClient(get_settings())
    print("Connection identity:")
    pprint(client.query("SELECT CURRENT_USER, CURRENT_SCHEMA FROM DUMMY"))
    print("Tables and columns:")
    pprint(client.discover_tables())

    print("\nViews:")
    views = client.query(
        """
        SELECT VIEW_NAME
        FROM SYS.VIEWS
        WHERE SCHEMA_NAME = ?
        ORDER BY VIEW_NAME
        """,
        (get_settings().reference_schema.upper(),),
    )
    pprint([row["view_name"] for row in views])

    view_columns = client.query(
        """
        SELECT VIEW_NAME, COLUMN_NAME
        FROM SYS.VIEW_COLUMNS
        WHERE SCHEMA_NAME = ?
        ORDER BY VIEW_NAME, POSITION
        """,
        (get_settings().reference_schema.upper(),),
    )
    grouped: dict[str, list[str]] = {}
    for row in view_columns:
        grouped.setdefault(row["view_name"], []).append(row["column_name"])
    pprint(grouped)

    for table in ("COUNTRIES", "SANCTIONS_LISTS", "SCREENING_RULES"):
        print(f"\n{table} samples:")
        pprint(client.query(f"SELECT * FROM {get_settings().reference_schema}.{table} LIMIT 3"))

    for view in (
        "RISK_ALERTS",
        "TRANSACTIONS",
        "COMPANIES",
        "COMPANY_RISK_PROFILES",
        "COMPANY_BENEFICIAL_OWNERS",
        "TRANSACTION_BASELINES",
        "COMPLIANCE_CASES",
    ):
        print(f"\n{view} samples:")
        pprint(client.query(f"SELECT * FROM {get_settings().reference_schema}.{view} LIMIT 2"))


if __name__ == "__main__":
    main()
