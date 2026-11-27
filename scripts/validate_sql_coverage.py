#!/usr/bin/env python3
"""Check SQL overlay coverage against tool signatures and KG vocabulary."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spire.kg.sql_overlay import OVERLAY  # noqa: E402
from spire.graph.pipeline import _FIELD_ALIASES  # noqa: E402

# Columns that EXIST and are never NULL-but-empty, so a "column exists"
# check passes while the predicate built on them can never match. Every
# entry is here because it was measured, not suspected (see the F-060 /
# F-062 / F-063 / F-080b records in docs/fixes/FIX_PLAN.md).
STUB_COLUMNS: dict[str, str] = {
    "ENABLED_FLAG": "'Y' on all 334 POZ_SUPPLIERS rows (F-080b)",
    "PO_LINES_ALL.AMOUNT": "NULL on 315,857 of 315,970 rows (F-060)",
    "PO_LINE_LOCATIONS_ALL.AMOUNT": "NULL on 310,807 of 310,947 rows (F-062)",
    "ESTIMATED_TAX_AMOUNT": "NULL on all 310,952 schedule rows (F-063)",
}


def _tool_signatures() -> dict[str, set[str]]:
    source = (ROOT / "src/spire/mcp_server/server.py").read_text()
    tree = ast.parse(source)
    signatures: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        is_tool = any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "tool"
            for decorator in node.decorator_list
        )
        if is_tool:
            signatures[node.name] = {
                arg.arg for arg in (*node.args.args, *node.args.kwonlyargs)
            }
    return signatures


def _tool_payload_fields() -> dict[str, set[str]]:
    source = (ROOT / "src/spire/mcp_server/server.py").read_text()
    tree = ast.parse(source)
    imported_modules: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        prefix = "spire.mcp_server.tools."
        if node.module.startswith(prefix):
            module = node.module.removeprefix(prefix)
            for alias in node.names:
                imported_modules[alias.asname or alias.name] = module

    fields: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if not any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "tool"
            for decorator in node.decorator_list
        ):
            continue
        module = next(
            (
                imported_modules[call.func.id]
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id in imported_modules
            ),
            None,
        )
        if module is None:
            continue
        module_path = ROOT / f"src/spire/mcp_server/tools/{module}.py"
        module_tree = ast.parse(module_path.read_text())
        payload_fields = next(
            (
                ast.literal_eval(statement.value)
                for statement in module_tree.body
                if isinstance(statement, ast.Assign)
                and any(
                    isinstance(target, ast.Name)
                    and target.id == "_PROJECTED_FIELDS"
                    for target in statement.targets
                )
            ),
            None,
        )
        if isinstance(payload_fields, list):
            fields[node.name] = {
                field for field in payload_fields if isinstance(field, str)
            }
    return fields


def _kg_field_mappings() -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    schema = (ROOT / "scripts/sql/kg_schema.sql").read_text()
    intent_fields = {
        (entity, field_name)
        for entity, field_name in re.findall(
            r"INSERT INTO kg_entity_field VALUES \('([^']+)', '([^']+)'",
            schema,
        )
    }
    sql_fields = {
        (entity, field_name)
        for entity, field_name, _table, _column in re.findall(
            r"INSERT INTO kg_sql_column \(entity_name, field_name, "
            r"physical_table, column_name, data_type, data_length, "
            r"is_default_projection\) VALUES \('([^']+)', '([^']+)', "
            r"'([^']+)', '([^']+)'",
            schema,
        )
    }
    sql_fields |= {
        (entity, field_name)
        for entity, field_name in re.findall(
            r"INSERT INTO kg_derived_projection "
            r"\(entity_name, field_name, expression, is_default_projection\) "
            r"VALUES \('([^']+)', '([^']+)'",
            schema,
        )
    }
    return intent_fields, sql_fields


def validate() -> list[str]:
    errors: list[str] = []
    signatures = _tool_signatures()
    sql_tools = set(OVERLAY.tool_to_entity) | set(OVERLAY.aggregations)
    categorized_args = set(OVERLAY.sql_disabled_args)

    for tool_name, arg_name in OVERLAY.filters:
        spec = OVERLAY.filters[(tool_name, arg_name)]
        if spec.tool_name != tool_name or spec.arg_name != arg_name:
            errors.append(
                f"FilterSpec key mismatch for {tool_name}.{arg_name}"
            )
        if tool_name not in signatures:
            errors.append(f"FilterSpec references unregistered tool {tool_name}")
        elif arg_name not in signatures[tool_name]:
            errors.append(
                f"FilterSpec references missing parameter {tool_name}.{arg_name}"
            )
        if "contains" in arg_name or (
            arg_name == "supplier_name"
            and tool_name in {"search_invoices", "search_purchase_orders"}
        ):
            if spec.match_mode != "contains" or "LIKE" not in spec.predicate_template:
                errors.append(
                    f"Substring argument {tool_name}.{arg_name} lacks "
                    "contains semantics"
                )
    # F-080b generalised: a predicate on a KNOWN-STUB column returns a
    # confident wrong answer (a zero for "inactive suppliers") while
    # looking perfectly valid, so it cannot be caught by shape checks.
    # The old rule named ENABLED_FLAG on search_suppliers.status only,
    # which meant the next spec could reuse any other stub silently.
    # Each entry carries the measurement that makes it a stub, so nobody
    # has to re-derive why it is on the list.
    for (tool_name, arg_name), spec in sorted(OVERLAY.filters.items()):
        for column, evidence in STUB_COLUMNS.items():
            if column in spec.predicate_template:
                errors.append(
                    f"{tool_name}.{arg_name} filters on the stub column "
                    f"{column} ({evidence})"
                )

    for tool_name in sorted(sql_tools):
        if tool_name not in signatures:
            errors.append(f"SQL overlay references unregistered tool {tool_name}")
            continue
        args = signatures[tool_name]
        covered = {
            arg for tool, arg in OVERLAY.filters if tool == tool_name
        }
        covered |= OVERLAY.sql_control_args
        covered |= {
            arg for tool, arg in categorized_args if tool == tool_name
        }
        if tool_name == "search_suppliers":
            covered.add("include_addresses")
        aggregation = OVERLAY.aggregations.get(tool_name)
        if aggregation is not None:
            if aggregation.top_n_arg:
                covered.add(aggregation.top_n_arg)
            covered |= aggregation.skip_args
        for arg_name in sorted(args - covered):
            errors.append(f"Uncovered tool argument {tool_name}.{arg_name}")
        for tool, arg_name in categorized_args:
            if tool == tool_name and arg_name not in args:
                errors.append(
                    f"Stale SQL-disabled argument {tool_name}.{arg_name}"
                )

    for tool_name in sorted(set(signatures) - sql_tools - OVERLAY.not_expressible):
        errors.append(f"Tool has no SQL dispatch classification: {tool_name}")

    intent_fields, sql_fields = _kg_field_mappings()
    for entity, field_name in sorted(sql_fields - intent_fields):
        errors.append(
            f"SQL field {entity}.{field_name} is absent from intent.fields vocabulary"
        )
    for spec in OVERLAY.filters.values():
        entity_name = OVERLAY.tool_to_entity.get(spec.tool_name)
        if entity_name and not any(
            entity == entity_name for entity, _ in intent_fields
        ):
            errors.append(
                f"Intent field vocabulary has no entries for {entity_name}"
            )
    payload_fields = _tool_payload_fields()
    for tool_name, payload in payload_fields.items():
        entity_name = OVERLAY.tool_to_entity.get(tool_name)
        if entity_name is None:
            continue
        # F-081: a display-name field is satisfied when the projection can
        # actually fill it — either the payload carries the field itself,
        # or `_FIELD_ALIASES` names a payload key that does. Before the
        # alias map existed this check flagged SupplierName/BuyerName on
        # every PO tool; now it flags only genuinely unfillable columns.
        for field_name in sorted(
            field
            for entity, field in intent_fields
            if entity == entity_name
            and field.endswith("Name")
            and field not in payload
            and _FIELD_ALIASES.get(field) not in payload
            and field[:-4] in payload
        ):
            errors.append(
                f"Intent field {entity_name}.{field_name} has no payload alias "
                f"for {tool_name}.{field_name[:-4]}"
            )

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("SQL coverage validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("SQL coverage validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
