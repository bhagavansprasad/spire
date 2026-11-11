from tools import query_students, query_courses, query_payments, query_exam_results


TOOL_REGISTRY = {
    "query_students": query_students,
    "query_courses": query_courses,
    "query_payments": query_payments,
    "query_exam_results": query_exam_results,
}


def apply_filter(records, filter_definition):
    """
    Apply a filter using the rule provided by the Knowledge Graph.
    """
    left_field = filter_definition["left_field"]
    operator = filter_definition["operator"]
    right_field = filter_definition["right_field"]

    # Allow only explicitly supported comparison operators.
    comparisons = {
        ">": lambda left, right: left > right,
        "<": lambda left, right: left < right,
        ">=": lambda left, right: left >= right,
        "<=": lambda left, right: left <= right,
        "==": lambda left, right: left == right,
        "!=": lambda left, right: left != right,
    }

    if operator not in comparisons:
        raise ValueError(f"Unsupported filter operator: {operator}")

    filtered_records = []

    for record in records:
        if left_field not in record or right_field not in record:
            raise ValueError(
                f"Filter fields {left_field!r} and {right_field!r} "
                f"must exist in the record"
            )

        left_value = record[left_field]
        right_value = record[right_field]

        if comparisons[operator](left_value, right_value):
            filtered_records.append(record)

    return filtered_records



def match_related_records(
    main_records,
    related_records,
    source_field,
    target_field,
):
    """
    Match records using the connection fields provided by the KG.
    """
    related_values = {
        record[target_field]
        for record in related_records
    }

    return [
        record
        for record in main_records
        if record[source_field] in related_values
    ]
    
def execute_plan(plan, intent):
    """
    Execute the retrieval, filtering, relationship matching,
    and field-selection steps in the Plan.
    """
    results = {}

    # 1. Execute the tool-retrieval steps.
    for step in plan:
        tool_name = step.get("tool_name")

        if not tool_name:
            continue

        tool = TOOL_REGISTRY.get(tool_name)

        if tool is None:
            raise ValueError(f"Unknown tool: {tool_name}")

        print(f"Executing step {step['step_id']}: {tool_name}")
        results[tool_name] = tool()

    # 2. Find the main and related records.
    entity = intent["entity"]
    related_entity = intent.get("related_entity")

    main_tool = next(
        step["tool_name"]
        for step in plan
        if step.get("tool_name")
        and step["purpose"] == f"Retrieve {entity} records"
    )

    main_records = results[main_tool]

  
    related_records = []
    relationship = None

    if related_entity:
        related_step = next(
            step
            for step in plan
            if step.get("tool_name")
            and step["purpose"]
            == f"Retrieve related {related_entity} records"
        )

        related_tool = related_step["tool_name"]
        relationship = related_step["relationship"]

        related_records = results[related_tool]


    # 3. Process the filter step using the KG-defined rule.
    for step in plan:
        if step.get("action") != "apply_filter":
            continue

        filter_definition = step["filter_definition"]

        # In this example, the KG says the filter belongs to Payment.
        # We apply it to the related records.
        related_records = apply_filter(
            related_records,
            filter_definition,
        )

        if related_entity:
            main_records = match_related_records(
                main_records,
                related_records,
                source_field=relationship["source_field"],
                target_field=relationship["target_field"],
            )
        else:
            main_records = related_records

    # 4. Select the fields requested by the user.
    for step in plan:
        if step.get("action") != "select_fields":
            continue

        fields = step["fields"]

        for field in fields:
            if main_records and field not in main_records[0]:
                raise ValueError(
                    f"Requested field {field!r} "
                    f"is not available in the main records"
                )

        main_records = [
            {
                field: record[field]
                for field in fields
            }
            for record in main_records
        ]

    return main_records