#!/usr/bin/env python3
"""Create new versions of the two FLV prompt agents in Microsoft Foundry."""

from __future__ import annotations

import os

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import DefaultAzureCredential


PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
MODEL_DEPLOYMENT = os.getenv("FOUNDRY_MODEL_DEPLOYMENT", "gpt-4-1-mini-flv")

AGENTS = {
    "flv-customer-agent": (
        "Guide an insurance customer through first-look vehicle verification in a "
        "friendly, professional tone. Ask for one clear vehicle image, registration, "
        "or title at a time. Ask at most one clarifying question per turn. Summarize "
        "only confidently extracted evidence. Do not request unrelated sensitive data "
        "or make coverage, fraud, or legal-authenticity decisions."
    ),
    "flv-employee-agent": (
        "Answer insurance employee questions only from the case evidence supplied in "
        "the prompt. Clearly distinguish extracted facts from inferences, mention "
        "confidence and missing evidence, and cite filenames when useful. Never make "
        "the final coverage, fraud, or legal-authenticity decision."
    ),
}


def main() -> None:
    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )
    for name, instructions in AGENTS.items():
        agent = project.agents.create_version(
            agent_name=name,
            definition=PromptAgentDefinition(
                model=MODEL_DEPLOYMENT,
                instructions=instructions,
            ),
        )
        print(f"Configured {agent.name} version {agent.version}")


if __name__ == "__main__":
    main()

