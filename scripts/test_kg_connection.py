"""
2a — Verify Python can connect to the KG and run one query.

Tests Decision 1 of Phase 2: that Python (via the `oracledb` driver)
can reach Oracle 26ai running in the docker container and read from
the KG tables.

This is a single-query smoke test. If it passes, we know:
  - The Python driver works in this venv
  - The container port mapping works from the host
  - Credentials work from outside the container
  - The KG tables are readable from a Python connection
"""

import oracledb

from spire.planner.planner import _oracle_credentials


def main() -> None:
    # Credentials come from the single resolver (env -> persona -> fallback)
    # so this smoke test uses the same source as the rest of the app.
    user, password, dsn = _oracle_credentials()
    connection = oracledb.connect(user=user, password=password, dsn=dsn)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT endpoint_path, canonical_id_field, display_name_field
                FROM kg_entity
                WHERE entity_name = :name
                """,
                name="Supplier",
            )
            row = cursor.fetchone()

            if row is None:
                print("FAIL: no row returned for Supplier")
                return

            endpoint_path, canonical_id_field, display_name_field = row
            print("PASS — Python can read the KG.")
            print(f"  endpoint_path:      {endpoint_path}")
            print(f"  canonical_id_field: {canonical_id_field}")
            print(f"  display_name_field: {display_name_field}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()