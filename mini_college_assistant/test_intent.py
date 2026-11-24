
from pprint import pprint
from route_and_parse import route_and_parse

test_questions = [
    # Basic entity questions
    "Show all people.",
    "List all organizations.",

    # Relationship questions
    "Who works for Infosys?",
    "Who does Arjun know?",

    # Filter questions
    "Find people older than 30.",
    "Show organizations in the Cloud industry.",

    # More detailed question
    "Show the names and roles of people working for Infosys.",
]

for question in test_questions:
    print("\n" + "=" * 70)
    print("QUESTION:", question)
    print("=" * 70)

    try:
        intent = route_and_parse(question)
        pprint(intent)

    except Exception as e:
        print("ERROR:", e)
