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

DB_PATH = "people_organization.db"

MODEL = os.getenv("SPIRE_LLM_MODEL", "gemini-3.5-flash")

MODULES = {
    "People": """
        Questions about people, their names, ages, cities,
        and relationships with other people, including
        who knows whom.
    """,

    "Organizations": """
        Questions about organizations, their names, industries,
        and people working for them.
    """
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
        # 1. Load entities.
        cursor.execute("""
            SELECT entity_id, entity_name, description
            FROM kg_entity
        """)
        entities = cursor.fetchall()

        entity_ids = {
            entity_name: entity_id
            for entity_id, entity_name, description in entities
        }

        
        # 2. Load relationships.
        cursor.execute("""
            SELECT relationship_id,
                relationship_name,
                source_entity_id,
                target_entity_id,
                description
            FROM kg_relationship
        """)
        relationships = cursor.fetchall()

        # 3. Load entity fields.
        cursor.execute("""
            SELECT entity_id, field_name, description
            FROM kg_field
        """)
        fields = cursor.fetchall()

        # 4. Load relationship properties.
        cursor.execute("""
            SELECT relationship_id, field_name, description
            FROM kg_relationship_field
        """)
        relationship_fields = cursor.fetchall()


        # 5. Load available filters.
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

        # 6. Load tool mappings.
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
            "relationship_fields": relationship_fields,
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
    You are the module classifier for a People and Organizations assistant.

    Your task is to identify ALL modules required to answer the user's question.

    Available modules:
    {json.dumps(MODULES, indent=2)}

    Available modules and their responsibilities:

    1. People:
    - Person names, IDs, ages and cities.
    - Relationships between people, such as who knows whom.
    - Finding people based on their details.

    2. Organizations:
    - Organization names and industries.
    - Finding organizations based on their details.

    IMPORTANT MODULE SELECTION RULES:

    1. If the question asks about people only, select People.

    2. If the question asks about organizations only, select Organizations.

    3. If the question asks who works for an organization,
    ALWAYS select BOTH People and Organizations.

    4. If the question asks which organization a person works for,
    ALWAYS select BOTH People and Organizations.

    5. If the question asks about people working in a particular
    industry, select BOTH People and Organizations.

    6. If the question asks who knows whom,
    select People only.

    7. If the question requires information about both people
    and organizations, select BOTH modules.

    8. Do not select a module just because its name appears
    in the question. Select modules based on the information
    needed to answer the question.

    9. Do not invent module names.

    10. If no module is relevant, return an empty list.

    Return only JSON in this format:

    {{
        "modules": ["People", "Organizations"]
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
        "People": "PERSON",
        "Organizations": "ORGANIZATION",
    }

    selected_entities = {
        module_to_entity[module]
        for module in modules
        if module in module_to_entity
    }

    entity_ids = menu["entity_ids"]

    id_to_name = {
        entity_id: entity_name
        for entity_name, entity_id in entity_ids.items()
    }

    selected_ids = {
        entity_ids[name]
        for name in selected_entities
        if name in entity_ids
    }

    # 1. Select entities.
    entities = [
        {
            "name": entity_name,
            "description": description,
        }
        for entity_id, entity_name, description in menu["entities"]
        if entity_name in selected_entities
    ]

    # 2. Select relationships connecting selected entities.
    selected_relationships = [
        {
            "id": relationship_id,
            "name": name,
            "source": id_to_name.get(source_id, source_id),
            "target": id_to_name.get(target_id, target_id),
            "description": description,
        }
        for relationship_id, name, source_id, target_id, description
        in menu["relationships"]
        if source_id in selected_ids
        and target_id in selected_ids
    ]

    # 3. Select entity fields.
    fields = [
        {
            "entity": id_to_name.get(entity_id, entity_id),
            "field": field_name,
            "description": description,
        }
        for entity_id, field_name, description in menu["fields"]
        if entity_id in selected_ids
    ]

    # 4. Select relationship properties.
    relationship_fields = [
        {
            "relationship": relationship["name"],
            "field": field_name,
            "description": description,
        }
        for relationship_id, field_name, description
        in menu["relationship_fields"]
        for relationship in selected_relationships
        if relationship["id"] == relationship_id
    ]

    # 5. Select filters.
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

    # 6. Select tool mappings.
    tools = [
        {
            "entity": id_to_name.get(entity_id, entity_id),
            "tool": tool_name,
            "description": description,
        }
        for entity_id, tool_name, description in menu["tools"]
        if entity_id in selected_ids
    ]

    # 7. Combine KG information.
    context = {
        "entities": entities,
        "relationships": [
            {
                "name": relationship["name"],
                "source": relationship["source"],
                "target": relationship["target"],
                "description": relationship["description"],
            }
            for relationship in selected_relationships
        ],
        "fields": fields,
        "relationship_fields": relationship_fields,
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
            ["People", "Organizations"],
            menu,
        )

    
    
    parser_prompt = f"""
    You are the parser for a People and Organizations assistant.

    Convert the user's question into a structured Intent
    using the provided Knowledge Graph context.

    KG RULES:

    1. Use only entities, fields, relationships, filters,
    and tool mappings provided in the KG context.

    2. Do not invent entities, fields, relationships, or filters.

    3. The entity must be the MAIN entity whose records
    the user wants to retrieve.

    4. Use "PERSON" for questions asking about people.

    5. Use "ORGANIZATION" for questions asking about organizations.

    6. Use related_entity when answering requires information
    from another entity.

    7. Use related_entity = null when the question can be
    answered using only the main entity.

    8. For questions about who knows whom, use:
    entity = "PERSON"
    related_entity = "PERSON"
    when the KNOWS relationship is available.

    9. For questions about people working for organizations, use:
    entity = "PERSON"
    related_entity = "ORGANIZATION"
    when the WORKS_FOR relationship is available.

    10. If the question has a condition on a field (such as age, city,
    or organization name), set filter to a dictionary with exactly
    these keys: "field", "operator" and "value".

    11. "field" must be one of the field names in the KG context.

    12. "operator" must be one of: ">", "<", ">=", "<=", "==", "!=".
        Use "==" for "equals" and "is".

    13. "value" must come from the user's question.
        Use a number (not text) for numeric fields such as AGE.

    14. If the question has no condition, set filter to null.

    EXAMPLES:

    Question: "Show me all people."

    Intent:
    {{
        "entity": "PERSON",
        "related_entity": null,
        "filter": null,
        "requested_fields": ["PERSON_ID", "NAME", "CITY", "AGE"]
    }}

    Question: "Who does Moksha know?"

    Intent:
    {{
        "entity": "PERSON",
        "related_entity": "PERSON",
        "filter": null,
        "requested_fields": ["NAME"]
    }}

    Question: "Which people work for Google?"

    Intent:
    {{
        "entity": "PERSON",
        "related_entity": "ORGANIZATION",
        "filter": null,
        "requested_fields": ["NAME", "ORG_NAME", "ROLE", "SINCE"]
    }}

    Question: "Show me all organizations."

    Intent:
    {{
        "entity": "ORGANIZATION",
        "related_entity": null,
        "filter": null,
        "requested_fields": ["ORG_ID", "ORG_NAME", "INDUSTRY"]
    }}

    IMPORTANT:

    - The examples show the expected output structure.
    - Use only the relationships present in the KG context.
    - Do not invent filters.
    - Return valid JSON only.
    - Return these four keys:
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

    # Validate the dynamic filter.
    selected_filter = intent["filter"]

    if selected_filter is not None:

        if not isinstance(selected_filter, dict):
            raise ValueError(
                "Filter must be a dictionary or None."
            )

        required_filter_keys = {
            "field",
            "operator",
            "value",
        }

        if not required_filter_keys.issubset(selected_filter):
            raise ValueError(
                "Filter must contain field, operator and value."
            )

        allowed_operators = {
            ">", "<", ">=", "<=", "==", "!="
        }

        if selected_filter["operator"] not in allowed_operators:
            raise ValueError("Unsupported filter operator.")

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

    questions = [
    "Which people are above thirty?",
    "People aged 35 or more",
    "Everyone except those aged 32",
    "People who live in pune",
    "Names of people older than 30",
    "People younger than 28",
    "People who are exactly 31",
    "People older than 100",
    "Who works for Google?",
    "peple oldr than 30",
    "People older than 30 in Bangalore",
    "Who is the oldest person?",
    "How many people are older than 30?",
    "Who knows Priya?",
    "What is the weather in Pune?",
    "Delete all people",
    "Show me everyone's salary",
]

    # Load the KG once and show what was loaded
    kg_menu = load_kg_menu()

    print("Loaded KG entities:")
    for entity_id, entity_name, description in kg_menu["entities"]:
        print(f"ID: {entity_id}, Name: {entity_name}")

    for q in questions:
        print("\n" + "=" * 60)
        print("User prompt:")
        print(q)

        try:
            intent = route_and_parse(q, menu=kg_menu)

            print("\nFinal Intent:")
            print(json.dumps(intent, indent=2))

            plan = generate_plan(intent)

            print("\nGenerate plan:")
            print(json.dumps(plan, indent=2))

            # "Executing step ..." is printed by executor.py itself
            results = execute_plan(plan, intent)

            print("\nRetrieved Results:")
            print(f"Rows returned: {len(results)}")
            print(json.dumps(results, indent=2))

        except Exception as e:
            print("\nERROR:", e)