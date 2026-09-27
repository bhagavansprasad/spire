"""Agent runner — LangGraph + Gemini + MCP HTTP transport.

Connects to the Spire MCP server (URL from SPIRE_MCP_URL), pulls tools
via langchain-mcp-adapters,
binds them to the configured Gemini model, and runs a single-pass
graph:

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
in the evaluation framework.
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
from spire.config import load_persona, mcp_server_url
from spire.kg.loader import load_kg_context

import logging

logging.getLogger("langchain_google_genai").setLevel(logging.ERROR)


# Model selection — see docs/spire_poc_log.md for the history.
# Earlier phases used gemini-2.0-flash. Phase 08/09 showed 1/5 success on the
# reference prompt regardless of KG state. Diagnostic runs on 2.5-flash were
# worse (tool hallucination). 2.5-pro is the reasoning-tier model;
# under investigation for whether LLM capability was the real bottleneck.
MODEL = "gemini-2.5-pro"

PERSONA_NAME = "default_dev"


def _normalize_content(raw):
    """Coerce LLM message content to plain string.

    gemini-2.0-flash returns final_message.content as a plain str.
    gemini-2.5-pro returns it as a list of {"type": "text", "text": "..."}
    dicts (with optional signature metadata). Callers want a string either
    way; this helper does the right thing for both.
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts = []
        for block in raw:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    # Fallback: stringify whatever it is.
    return str(raw)


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

    async with streamablehttp_client(mcp_server_url()) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            logger.info("mcp_session_initialized", url=mcp_server_url())

            graph = await _build_graph(session, system_prompt, logger)
            logger.info("graph_built")

            result = await graph.ainvoke({"messages": [HumanMessage(content=prompt)]})

            # Log each message in the final state for trace inspection.
            for i, msg in enumerate(result["messages"]):
                content_preview = _normalize_content(msg.content)
                event = {
                    "index": i,
                    "type": msg.__class__.__name__,
                    "content_preview": content_preview[:200] if content_preview else None,
                }
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    event["tool_calls"] = [
                        {"name": tc["name"], "args": tc["args"]} for tc in msg.tool_calls
                    ]
                logger.info("message", **event)

            final_message = result["messages"][-1]
            answer = _normalize_content(final_message.content)
            logger.info("agent_finished", answer_preview=answer[:200])
            return answer
