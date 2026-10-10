"""Ask the agents one question from the command line, showing every tool call."""

import asyncio
import sys

from google.adk.runners import InMemoryRunner

from specdelta.agents.assistant.agent import root_agent


async def main(question: str) -> None:
    runner = InMemoryRunner(agent=root_agent, app_name="specdelta")
    await runner.run_debug(question, verbose=True)


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:])))
