from spire.graph.pipeline import parse_node

print("BEFORE parse_node", flush=True)

state = {
    "prompt": "Show me supplier name 1",
    "menu": None,
}

result = parse_node(state)

print("AFTER parse_node", flush=True)
print(result, flush=True)