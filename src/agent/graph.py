"""LangGraph StateGraph definition for the FinOps agent."""

from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent.nodes.analyze import analyze_node
from agent.nodes.gather import gather_node
from agent.nodes.plan import plan_node
from agent.nodes.recommend import recommend_node
from agent.state import AgentState
from common.config import AgentConfig


def _route_after_analyze(state: AgentState) -> str:
    """Conditional edge: route back to gather when more data is needed.

    Args:
        state: Current graph state with ``needs_more_data`` flag.

    Returns:
        ``"gather"`` when the analyze node requested more data, otherwise
        ``"recommend"`` to proceed to finding generation.
    """
    if state.get("needs_more_data", False):
        return "gather"
    return "recommend"


def build_graph(config: AgentConfig) -> CompiledStateGraph:  # noqa: ARG001
    """Construct and compile the FinOps LangGraph StateGraph.

    Graph topology::

        plan → gather → analyze → (needs_more_data?) → gather (loop)
                                                      → recommend → END

    Args:
        config: Runtime configuration (reserved for future node parameterisation).

    Returns:
        Compiled LangGraph graph ready for ``ainvoke``.
    """
    graph: StateGraph = StateGraph(AgentState)

    graph.add_node("plan", plan_node)
    graph.add_node("gather", gather_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("recommend", recommend_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "gather")
    graph.add_edge("gather", "analyze")
    graph.add_conditional_edges("analyze", _route_after_analyze)
    graph.add_edge("recommend", END)

    return graph.compile()
