# agent_registry.py

from typing import Dict
from shared_types import Ticket


class AgentRegistry:

    def __init__(self):
        self.agents: Dict[str, dict] = {
            "agent-1": {
                "skills": {"Billing": 0.9, "Technical": 0.2, "Legal": 0.1},
                "capacity": 5,
                "load": 0
            },
            "agent-2": {
                "skills": {"Billing": 0.3, "Technical": 0.9, "Legal": 0.2},
                "capacity": 5,
                "load": 0
            },
            "agent-3": {
                "skills": {"Billing": 0.4, "Technical": 0.4, "Legal": 0.9},
                "capacity": 3,
                "load": 0
            }
        }

    def assign(self, ticket: Ticket) -> str:
        best_agent = None
        best_score = -1

        for agent_id, data in self.agents.items():

            if data["load"] >= data["capacity"]:
                continue  # skip full agents

            skill_score = data["skills"].get(ticket.category, 0)
            availability = 1 - (data["load"] / data["capacity"])

            score = skill_score * availability

            if score > best_score:
                best_score = score
                best_agent = agent_id

        if best_agent:
            self.agents[best_agent]["load"] += 1
            return best_agent

        return "queued"

    def release(self, agent_id: str):
        if agent_id in self.agents:
            self.agents[agent_id]["load"] -= 1