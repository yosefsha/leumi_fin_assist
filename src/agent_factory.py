"""The composition root: build the research agent from `Settings`.

This is the one place concrete adapters (the Filing index, Tavily, Anthropic)
are chosen and injected; `src/main.py` calls `build_agent` and stays thin.
"""

from agent import ResearchAgent
from tools.calculator import CalculateTool
from tools.get_passage import GetPassageTool
from tools.registry import ToolRegistry
from tools.search_filing import SearchFilingTool
from tools.tavily_search import WebSearchTool
from utils.agent_observer import AgentObserver
from utils.anthropic_chat_model import AnthropicChatModel
from utils.citation_format import CitationFormatter
from utils.cited_answer import CitationResolver
from utils.config import Settings
from utils.cross_reference_resolver import CrossReferenceResolver
from utils.filing_index import FilingIndex
from utils.filing_index_factory import open_filing_index
from utils.tavily_web_search_client import TavilyWebSearchClient
from utils.tool_result_citer import ToolResultCiter
from utils.web_search import WebSearchClient


def build_agent(
    settings: Settings, force_rebuild: bool = False, observer: AgentObserver | None = None
) -> ResearchAgent:
    """Open (or build) the Filing index and wire the agent to Anthropic and Tavily.

    `force_rebuild` rebuilds the index (the CLI's `--rebuild-index`); `observer`
    receives the plan and each tool call as they happen.
    """
    index = open_filing_index(settings, force_rebuild=force_rebuild)
    return ResearchAgent(
        model=AnthropicChatModel(settings.anthropic_api_key, settings.anthropic_model),
        tools=build_tool_registry(index, TavilyWebSearchClient(settings.tavily_api_key)),
        citer=ToolResultCiter(CitationFormatter(settings.filing_fiscal_year)),
        resolver=CitationResolver(CitationFormatter(settings.filing_fiscal_year)),
        fiscal_year=settings.filing_fiscal_year,
        observer=observer,
    )


def build_tool_registry(index: FilingIndex, web_client: WebSearchClient) -> ToolRegistry:
    """Register the agent's four tools over `index` and `web_client`."""
    registry = ToolRegistry()
    registry.register(SearchFilingTool(index))
    registry.register(GetPassageTool(CrossReferenceResolver(index.passages)))
    registry.register(WebSearchTool(web_client))
    registry.register(CalculateTool())
    return registry
