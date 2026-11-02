from pprint import pprint
from planner import generate_plan


intent = {
    "entity": "Student",
    "related_entity": "Payment",
    "filter": "pending_fees",
    "requested_fields": ["student_id", "name"],
    "modules": ["Students", "Payments"],
}

plan = generate_plan(intent)

print("\nGenerated Plan:")
pprint(plan)