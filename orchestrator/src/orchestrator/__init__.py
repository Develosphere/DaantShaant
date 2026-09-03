"""DantShaant Orchestrator — composes model services for agent/MCP layer."""

# Guard against langchain 1.x missing 'debug' attribute expected by langchain-core
try:
    import langchain  # type: ignore[import]
    if not hasattr(langchain, "debug"):
        langchain.debug = False
except ImportError:
    pass
