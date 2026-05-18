"""Agent runner — LangGraph + Gemini + MCP HTTP transport.

Connects to the Spire MCP server (must already be running on
http://127.0.0.1:3333/mcp/), pulls tools via langchain-mcp-adapters,
binds them to gemini-2.0-flash, and runs a single-pass graph:

    START -> assistant -> tools -> assistant -> END

The `tools_condition` edge sends control back to the assistant after
each tool call; the graph terminates when the assistant produces a
final message with no tool calls.
"""

from functools import partial

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from spire.agent.tracing import make_trace_logger, truncate_tool_result


MODEL = "gemini-2.0-flash"
MCP_SERVER_URL = "http://127.0.0.1:3333/mcp/"

SYSTEM_PROMPT = (
    "You are a helpful assistant for Oracle Fusion Cloud consultants. "
    "You have access to tools that query the Fusion REST API. "
    "When the user asks about suppliers, invoices, purchase orders, or "
    "related data, use the available tools to find real records. "
    "Summarize results clearly and concisely. If a tool returns no records, "
    "say so plainly rather than guessing."
)


def _assistant(state: MessagesState, llm_with_tools):
    sys_msg = SystemMessage(content=SYSTEM_PROMPT)
    response = llm_with_tools.invoke([sys_msg] + state["messages"])
    return {"messages": [response]}


async def _build_graph(session: ClientSession, logger):
    """Construct the LangGraph agent. Pulls tool list from the MCP server."""
    tools = await load_mcp_tools(session)
    logger.info("tools_loaded", tools=[t.name for t in tools])

    llm = ChatGoogleGenerativeAI(model=MODEL)
    llm_with_tools = llm.bind_tools(tools)

    builder = StateGraph(MessagesState)
    builder.add_node("assistant", partial(_assistant, llm_with_tools=llm_with_tools))
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "assistant")
    builder.add_conditional_edges("assistant", tools_condition)
    builder.add_edge("tools", "assistant")
    return builder.compile()


async def run_agent(prompt: str) -> str:
    """Run the agent end-to-end. Returns the final answer text."""
    logger, trace_path = make_trace_logger()
    logger.info("agent_started", prompt=prompt, model=MODEL, trace_file=str(trace_path))

    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            logger.info("mcp_session_initialized", url=MCP_SERVER_URL)

            graph = await _build_graph(session, logger)
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
