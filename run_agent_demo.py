from pathlib import Path

from insightpilot.agent import DataAnalystAgent
from insightpilot.tools import AnalysisContext, ToolRegistry, build_data_tools

ROOT = Path(__file__).parent
DATASET = ROOT / "data" / "sample_sales.csv"


def build_agent() -> DataAnalystAgent:
    registry = ToolRegistry()
    for tool in build_data_tools():
        registry.register(tool)

    context = AnalysisContext()
    registry.execute("load_dataset", {"path": str(DATASET)}, context)

    return DataAnalystAgent(
        registry=registry,
        context=context,
    )


def main() -> None:
    agent = build_agent()

    question = "What are the top 3 products by total revenue?"
    result = agent.ask(question)

    print("=== QUESTION ===")
    print(question)

    print("\n=== TOOL CALLS ===")
    for call in result.tool_calls:
        print(call)

    print("\n=== FINAL ANSWER ===")
    print(result.answer)

    print("\n=== ITERATIONS ===")
    print(result.iterations)


if __name__ == "__main__":
    main()
