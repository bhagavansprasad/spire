"""S1 repro — construct an Intent with an include the KG can't wire off
PurchaseOrder, call generate_plan, show the raw exception. 3.5-flash's
parser won't emit this (it routes PO+supplier to the lifecycle tool), so
we build the Intent directly. Throwaway."""
from spire.planner.planner import generate_plan
from spire.planner.models import Intent
from spire.nl_parser.result import RefusalError

intent = Intent(
    target_entity="PurchaseOrder",
    filters=[{"type": "by_id", "value": "701337"}],
    include=["Supplier"],
)
print("Intent:", intent)
try:
    plan = generate_plan(intent)
    print("PLANNED (no crash):")
    for s in plan:
        print(f"  {s.tool_name} {s.tool_args}")
except RefusalError as e:
    print(f"REFUSED cleanly: {e.refusal.flavor.name} -> {e.refusal.detail}")
except Exception as e:
    print(f"RAW CRASH: {type(e).__name__}: {e}")
