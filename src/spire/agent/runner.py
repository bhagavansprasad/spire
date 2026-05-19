"""Agent runner — LangGraph + Gemini + MCP HTTP transport.

Connects to the Spire MCP server (must already be running on
http://127.0.0.1:3333/mcp/), pulls tools via langchain-mcp-adapters,
binds them to gemini-2.0-flash, and runs a single-pass graph:

    START -> assistant -> tools -> assistant -> END

The `tools_condition` edge sends control back to the assistant after
each tool call; the graph terminates when the assistant produces a
final message with no tool calls.

KG integration (Dynamic Orchestration 04, B-lite):
When run_agent is called with kg_enabled=True (default), the v1
Knowledge Graph metadata is loaded from Oracle via spire.kg.loader
and embedded in the system prompt. The agent's tool list is
unchanged — KG content informs the LLM's planning but is not exposed
as MCP tools.

The kg_enabled=False configuration is used for the Tier 2 ablation
in the evaluation framework (see docs/designs/kg_evaluation_framework.md).
"""

from functools import partial

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from spire.agent.prompts import build_system_prompt
from spire.agent.tracing import make_trace_logger
from spire.config import load_persona
from spire.kg.loader import load_kg_context


MODEL = "gemini-2.0-flash"
MCP_SERVER_URL = "http://127.0.0.1:3333/mcp/"
PERSONA_NAME = "default_dev"


def _assistant(state: MessagesState, llm_with_tools, system_prompt: str):
    sys_msg = SystemMessage(content=system_prompt)
    response = llm_with_tools.invoke([sys_msg] + state["messages"])
    return {"messages": [response]}


async def _build_graph(session: ClientSession, system_prompt: str, logger):
    """Construct the LangGraph agent. Pulls tool list from the MCP server."""
    tools = await load_mcp_tools(session)
    logger.info("tools_loaded", tools=[t.name for t in tools])

    llm = ChatGoogleGenerativeAI(model=MODEL)
    llm_with_tools = llm.bind_tools(tools)

    builder = StateGraph(MessagesState)
    builder.add_node(
        "assistant",
        partial(_assistant, llm_with_tools=llm_with_tools, system_prompt=system_prompt),
    )
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "assistant")
    builder.add_conditional_edges("assistant", tools_condition)
    builder.add_edge("tools", "assistant")
    return builder.compile()


async def run_agent(prompt: str, kg_enabled: bool = True) -> str:
    """Run the agent end-to-end. Returns the final answer text.

    Args:
        prompt: The user prompt.
        kg_enabled: Whether to include KG context in the system prompt.
            Defaults to True (Track B's standard configuration). Pass
            False for the Tier 2 ablation runs.
    """
    logger, trace_path = make_trace_logger()
    logger.info(
        "agent_started",
        prompt=prompt,
        model=MODEL,
        trace_file=str(trace_path),
        kg_enabled=kg_enabled,
    )

    # Load KG context if enabled. This is a one-time load per run_agent call.
    kg_context: str | None = None
    if kg_enabled:
        persona = load_persona(PERSONA_NAME)
        kg_context = await load_kg_context(persona)
        logger.info("kg_context_loaded", chars=len(kg_context))
    else:
        logger.info("kg_context_skipped")

    system_prompt = build_system_prompt(kg_context)
    logger.info("system_prompt_built", chars=len(system_prompt))

    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            logger.info("mcp_session_initialized", url=MCP_SERVER_URL)

            graph = await _build_graph(session, system_prompt, logger)
            logger.info("graph_built")

            result = await graph.ainvoke({"messages": [HumanMessage(content=prompt)]})

            # Log each message in the final state for trace inspection.
            for i, msg in enumerate(result["messages"]):
                event = {
                    "index": i,
                    "type": msg.__class__.__name__,
                    "content_preview": (msg.content[:200] if msg.content else None),
                }
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    event["tool_calls"] = [
                        {"name": tc["name"], "args": tc["args"]} for tc in msg.tool_calls
                    ]
                logger.info("message", **event)

            final_message = result["messages"][-1]
            answer = final_message.content or ""
            logger.info("agent_finished", answer_preview=answer[:200])
            return answer
