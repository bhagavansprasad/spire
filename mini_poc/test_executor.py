from pprint import pprint
from planner import generate_plan
from executor import execute_plan

intent = {
    "entity": "ExamResult",
    "requested_fields": [
        "student_name",
        "exam_name",
        "marks_obtained",
        "result"
    ],
    "modules": ["Examinations"]
}

plan = generate_plan(intent)

print("\nGenerated Plan:")
pprint(plan)

results = execute_plan(plan, intent)

print("\nExecution Results:")
pprint(results)