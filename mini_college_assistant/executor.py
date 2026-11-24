
from tools import (
    query_people,
    query_organizations,
    query_works_for,
    query_knows,
)

TOOL_REGISTRY = {
    "query_people": query_people,
    "query_organizations": query_organizations,
    "query_works_for": query_works_for,
    "query_knows": query_knows,
}


def apply_dynamic_filter(records, filter_condition):
    """
    Apply a dynamic filter extracted by the parser.
    Example: AGE > 30
    """

    field = filter_condition["field"]
    operator = filter_condition["operator"]
    value = filter_condition["value"]

    comparisons = {
        ">": lambda left, right: left > right,
        "<": lambda left, right: left < right,
        ">=": lambda left, right: left >= right,
        "<=": lambda left, right: left <= right,
        "==": lambda left, right: left == right,
        "!=": lambda left, right: left != right,
    }

    if operator not in comparisons:
        raise ValueError(f"Unsupported operator: {operator}")

    filtered_records = []

    for record in records:
        if field not in record:
            raise ValueError(
                f"Filter field {field!r} "
                f"is not available in the query results"
            )

        left_value = record[field]

        # Make text equality comparisons case-insensitive.
        if isinstance(left_value, str) and isinstance(value, str):
            if operator in ("==", "!="):
                left_value = left_value.casefold()
                value_to_compare = value.casefold()
            else:
                value_to_compare = value
        else:
            value_to_compare = value

        try:
            if comparisons[operator](left_value, value_to_compare):
                filtered_records.append(record)
        except TypeError as exc:
            raise ValueError(
                f"Cannot compare {left_value!r} "
                f"with {value_to_compare!r}"
            ) from exc

    return filtered_records


def execute_plan(plan, intent):
    """
    Execute tools, apply dynamic filters,
    and select requested fields.
    """

    results = []

    # STEP 1: Execute the tools selected by the planner.
    for step in plan:

        tool_name = step.get("tool_name")

        if not tool_name:
            continue

        tool = TOOL_REGISTRY.get(tool_name)

        if tool is None:
            raise ValueError(f"Unknown tool: {tool_name}")

        print(f"Executing step {step['step_id']}: {tool_name}")

        records = tool()
        results.extend(records)

    # STEP 2: Apply dynamic filters.
    filter_condition = intent.get("filter")

    if filter_condition is not None:
        results = apply_dynamic_filter(
            results,
            filter_condition
        )

    # STEP 3: Select requested fields.
    requested_fields = intent.get("requested_fields", [])

    if requested_fields:

        for record in results:
            for field in requested_fields:
                if field not in record:
                    raise ValueError(
                        f"Requested field {field!r} "
                        f"is not available in the query results"
                    )

        results = [
            {
                field: record[field]
                for field in requested_fields
            }
            for record in results
        ]

    return results
