# Twelve TheAgentCompany tasks as an AgentDojo suite. Importing this registers it.
from agentdojo.task_suite.load_suites import register_suite

from .tasks import suite

register_suite(suite, "v1.2.2")
