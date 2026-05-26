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


def main() -> None:
    # Connection string matches what rebuild_kg.sh uses,
    # split into oracledb's expected form.
    connection = oracledb.connect(
        user="spire",
        password="jnjnuh",
        dsn="localhost:1521/FREEPDB1",
    )

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