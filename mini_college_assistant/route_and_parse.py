import json
import os
import sqlite3

from google import genai
from google.genai import types

from planner import generate_plan
from executor import execute_plan

# --------------------------------------------------
# 1. CONFIGURATION
# --------------------------------------------------

DB_PATH = "college.db"

MODEL = os.getenv("SPIRE_LLM_MODEL", "gemini-3.5-flash")

MODULES = {
    "Students": "Questions about student information.",
    "Courses": "Questions about courses and course details.",
    "Payments": "Questions about fees, payments, and pending fees.",
    "Examinations": "Questions about exams, examination marks, results, and pass or fail status.",
}


class ClassificationError(Exception):
    """Raised when the classifier cannot identify a module."""
    pass


# --------------------------------------------------
# 2. LOAD THE KNOWLEDGE GRAPH MENU
# --------------------------------------------------

def load_kg_menu():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Load entities, including their actual database IDs.
        cursor.execute("""
            SELECT entity_id, entity_name, description
            FROM kg_entity
        """)
        entities = cursor.fetchall()

        # Create a mapping from entity names to IDs.
        # Example: {"Student": 1, "Course": 2, "Payment": 3}
        entity_ids = {
            entity_name: entity_id
            for entity_id, entity_name, description in entities
        }

        # Load relationships between entities.
        cursor.execute("""
            SELECT relationship_name,
                   source_entity_id,
                   target_entity_id,
                   description
            FROM kg_relationship
        """)
        relationships = cursor.fetchall()

        # Load fields belonging to each entity.
        cursor.execute("""
            SELECT entity_id, field_name, description
            FROM kg_field
        """)
        fields = cursor.fetchall()

        # Load available filters.
        cursor.execute("""
            SELECT filter_name,
                   entity_id,
                   description,
                   left_field,
                   operator,
                   right_field
            FROM kg_filter
        """)
        filters = cursor.fetchall()

        # Load tool mappings.
        cursor.execute("""
            SELECT entity_id, tool_name, description
            FROM kg_tool_mapping
        """)
        tools = cursor.fetchall()

        return {
            "entities": entities,
            "entity_ids": entity_ids,
            "relationships": relationships,
            "fields": fields,
            "filters": filters,
            "tools": tools,
        }

    finally:
        conn.close()


# --------------------------------------------------
# 3. GET THE LLM CLIENT
# --------------------------------------------------

def get_llm(llm=None):
    """
    Return the supplied Google GenAI client.
    If none is supplied, create a new client.
    """
    if llm is not None:
        return llm

    return genai.Client()


def call_llm_json(llm, prompt):
    """Send a prompt to Gemini and return its JSON response."""

    response = llm.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        ),
    )

    if not response.text:
        raise ValueError("The LLM returned an empty response.")

    return json.loads(response.text)


# --------------------------------------------------
# 4. LLM CALL 1: CLASSIFY MODULES
# --------------------------------------------------

def classify_modules(prompt: str, llm=None) -> list[str]:
    """
    Identify which modules are needed to answer the question.
    """

    client = get_llm(llm)

    classifier_prompt = f"""
You are the module classifier for a college assistant.

Identify which modules are needed to answer the user's question.

Available modules:
{json.dumps(MODULES, indent=2)}

Rules:
1. Select every module needed to answer the question.
2. Select multiple modules when necessary.
3. Select Students for questions asking for student details,
   such as student names, IDs, email addresses, or profiles.
4. Select Payments for fee and payment questions.
5. Select Courses for course questions.
6. Questions about exam marks, examination results, or PASS/FAIL
   status require Examinations.
7. Do not select Students just because the word "students" appears
   in an examination-results question. The Examinations module
   already provides student names along with exam results.
8. Select Students along with Examinations only when the question
   also asks for separate student information not included in
   examination results, such as email addresses.
9. Do not invent module names.
10. If no module is relevant, return an empty list.
11. Return only JSON in the specified format.

{{
    "modules": ["Students", "Payments"]
}}

User question:
{prompt}
"""

    result = call_llm_json(client, classifier_prompt)

    modules = result.get("modules")

    if not isinstance(modules, list):
        raise ValueError(
            "Classifier must return a list of modules."
        )

    if not modules:
        raise ClassificationError(
            "No relevant module found."
        )

    if any(module not in MODULES for module in modules):
        raise ValueError(
            "Classifier returned an unknown module."
        )

    # Remove duplicates while preserving order.
    return list(dict.fromkeys(modules))


# --------------------------------------------------
# 5. ASSEMBLE THE RELEVANT KG CONTEXT
# --------------------------------------------------

def assemble_subset(modules: list[str], menu: dict) -> str:
    """
    Select KG information relevant to the classified modules.
    Return the selected information as a JSON string.
    """

    module_to_entity = {
        "Students": "Student",
        "Courses": "Course",
        "Payments": "Payment",
        "Examinations": "ExamResult",
    }

    # Convert selected modules into KG entity names.
    selected_entities = {
        module_to_entity[module]
        for module in modules
    }

    # Use the actual IDs loaded from kg_entity.
    entity_ids = menu["entity_ids"]

    # Build the reverse mapping: ID -> entity name.
    id_to_name = {
        entity_id: entity_name
        for entity_name, entity_id in entity_ids.items()
    }

    # Get the IDs of the selected entities.
    selected_ids = {
        entity_ids[name]
        for name in selected_entities
        if name in entity_ids
    }

    # Select the relevant entities.
    entities = [
        {
            "name": entity_name,
            "description": description,
        }
        for entity_id, entity_name, description
        in menu["entities"]
        if entity_name in selected_entities
    ]

    # Select relationships connecting selected entities.
    relationships = [
        {
            "name": name,
            "source": id_to_name.get(source_id, source_id),
            "target": id_to_name.get(target_id, target_id),
            "description": description,
        }
        for name, source_id, target_id, description
        in menu["relationships"]
        if source_id in selected_ids
        and target_id in selected_ids
    ]

    # Select fields belonging to selected entities.
    fields = [
        {
            "entity": id_to_name.get(entity_id, entity_id),
            "field": field_name,
            "description": description,
        }
        for entity_id, field_name, description
        in menu["fields"]
        if entity_id in selected_ids
    ]

    # Select filters belonging to selected entities.
    filters = [
        {
            "name": name,
            "entity": id_to_name.get(entity_id, entity_id),
            "description": description,
            "left_field": left_field,
            "operator": operator,
            "right_field": right_field,
        }
        for (
            name,
            entity_id,
            description,
            left_field,
            operator,
            right_field,
        ) in menu["filters"]
        if entity_id in selected_ids
    ]

    # Select tool mappings belonging to selected entities.
    tools = [
        {
            "entity": id_to_name.get(entity_id, entity_id),
            "tool": tool_name,
            "description": description,
        }
        for entity_id, tool_name, description
        in menu["tools"]
        if entity_id in selected_ids
    ]

    # Combine the selected KG information.
    context = {
        "entities": entities,
        "relationships": relationships,
        "fields": fields,
        "filters": filters,
        "tools": tools,
    }

    return json.dumps(context, indent=2)


# --------------------------------------------------
# 6. LLM CALL 2: PARSE THE QUESTION INTO AN INTENT
# --------------------------------------------------

def parse(
    prompt: str,
    llm=None,
    menu=None,
    system_prompt=None,
) -> dict:
    """
    Convert the user's question into a structured Intent.
    """

    if menu is None:
        menu = load_kg_menu()

    client = get_llm(llm)

    # If no selected context is supplied, use the full KG.
    if system_prompt is None:
        system_prompt = assemble_subset(
            ["Students", "Courses", "Payments", "Examinations"],
            menu,
        )

    
    parser_prompt = f"""
    You are the parser for a college assistant.

    Convert the user's question into a structured Intent using the provided KG context.

    KG RULES:
    1. Use only entities, fields, relationships, filters, and tool mappings provided in the KG context.
    2. Do not invent entities, fields, relationships, or filters.
    3. The entity must be the MAIN entity whose records the user wants to retrieve.
    4. If the question asks for students, set entity to "Student".
    5. If answering the question requires information from another entity, set related_entity to that entity.
    6. If the question can be answered using only the main entity, set related_entity to null.
    7. Use a filter only when a known KG filter matches the user's condition.
    8. If no known filter matches the question, set filter to null.
    9. requested_fields must contain valid fields from the KG context that help answer the question.
    10. If the question asks for students and requires checking their payments, use:
        entity = "Student"
        related_entity = "Payment"
        when the KG context contains the relationship connecting Student and Payment.
    11. If the question asks for examination results, use:
    entity = "ExamResult"
    related_entity = null
    when the KG context contains the ExamResult entity.
    12. The ExamResult tool retrieves student names, exam names,
        marks, and calculated PASS/FAIL status using database JOINs.
    13. Do not set related_entity to Student or Exam for an
    examination-results question. The ExamResult tool already
    retrieves the required joined information.
    
    EXAMPLES:

    Question: "Show me the details of all students."
    Intent:
    {{
        "entity": "Student",
        "related_entity": null,
        "filter": null,
        "requested_fields": ["student_id", "name", "email"]
    }}

    Question: "Show me all students who have pending fees."
    Intent:
    {{
        "entity": "Student",
        "related_entity": "Payment",
        "filter": "pending_fees",
        "requested_fields": ["student_id", "name"]
    }}

    Question: "Which students paid their college fees?"
    Intent:
    {{
        "entity": "Student",
        "related_entity": "Payment",
        "filter": null,
        "requested_fields": ["student_id", "name"]
    }}

    Question: "Show me the examination results of all students."
    Intent:
    {{
        "entity": "ExamResult",
        "related_entity": null,
        "filter": null,
        "requested_fields": [
            "student_name",
            "exam_name",
            "marks_obtained",
            "result"
        ]
    }}
    
    IMPORTANT:
    - The examples show the expected output structure.
    - Select a filter only when its meaning matches the question.
    - Do not use "pending_fees" to represent students who have fully paid.
    - Return valid JSON only, with these keys:
    "entity", "related_entity", "filter", "requested_fields".

    KG context:
    {system_prompt}

    User question:
    {prompt}
    """


    intent = call_llm_json(client, parser_prompt)

    # Check that all required keys are present.
    required_keys = {
        "entity",
        "related_entity",
        "filter",
        "requested_fields",
    }

    if not required_keys.issubset(intent):
        raise ValueError(
            "Parser returned an incomplete Intent."
        )

    if not isinstance(intent["requested_fields"], list):
        raise ValueError(
            "requested_fields must be a list."
        )

    # Get the entity names from the KG.
    entity_names = {
        entity_name
        for entity_id, entity_name, description
        in menu["entities"]
    }

    # Validate the main entity.
    entity = intent["entity"]

    if entity is not None and entity not in entity_names:
        raise ValueError(f"Unknown entity: {entity}")

    # Validate the related entity.
    related_entity = intent["related_entity"]

    if (
        related_entity is not None
        and related_entity not in entity_names
    ):
        raise ValueError(
            f"Unknown related entity: {related_entity}"
        )

    # Validate the selected filter.
    filter_names = {
        record[0]
        for record in menu["filters"]
    }

    selected_filter = intent["filter"]

    if (
        selected_filter is not None
        and selected_filter not in filter_names
    ):
        raise ValueError(
            f"Unknown filter: {selected_filter}"
        )

    return intent


# --------------------------------------------------
# 7. ROUTE AND PARSE: CONNECT ALL THE COMPONENTS
# --------------------------------------------------

def route_and_parse(
    prompt: str,
    llm=None,
    menu=None,
) -> dict:
    """
    Run the complete routing and parsing flow:

    1. Load the KG menu.
    2. Classify relevant modules (LLM call 1).
    3. Assemble the relevant KG context.
    4. Parse the question into an Intent (LLM call 2).
    """

    # Load the KG once and reuse it.
    if menu is None:
        menu = load_kg_menu()

    try:
        # LLM CALL 1:
        # Identify the modules needed for the question.
        modules = classify_modules(
            prompt,
            llm=llm,
        )

    except ClassificationError:
        # If no module matches, try parsing with the full KG.
        intent = parse(
            prompt,
            llm=llm,
            menu=menu,
            system_prompt=None,
        )

        intent["modules"] = []
        return intent

    # Prepare the KG context for the selected modules.
    scoped_context = assemble_subset(
        modules,
        menu,
    )

    # LLM CALL 2:
    # Convert the question into a structured Intent.
    intent = parse(
        prompt,
        llm=llm,
        menu=menu,
        system_prompt=scoped_context,
    )

    # Keep the selected modules in the result for inspection.
    intent["modules"] = modules

    return intent


# --------------------------------------------------
# 8. TEST THE COMPLETE FLOW
# --------------------------------------------------

if __name__ == "__main__":

    user_prompt = "Show me the examination results of all students."

    print("User prompt:")
    print(user_prompt)

    # Load and inspect the KG menu.
    kg_menu = load_kg_menu()

    print("\nLoaded KG entities:")
    for entity_id, entity_name, description in kg_menu["entities"]:
        print(f"ID: {entity_id}, Name: {entity_name}")

    # Run routing and parsing.
    intent = route_and_parse(
        user_prompt,
        menu=kg_menu,
    )
    print("\nFinal Intent:")
    print(json.dumps(intent, indent=2))
    
    plan = generate_plan(intent)
    
    print("\nGenerate plan:")
    print(json.dumps(plan, indent=2))
    
    results = execute_plan(plan,intent)

    print("\nRetrieved Results:")
    print(json.dumps(results, indent=2))