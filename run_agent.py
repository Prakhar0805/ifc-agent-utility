# Run Gemini on a handful of AgentDojo tasks, once normally and once with the rule
# (after the agent has read private AND untrusted data, hide every external tool).
# Needs GEMINI_API_KEY in the environment. Finished runs are reused on a rerun.
import os
from pathlib import Path

import openai
import yaml
from agentdojo.agent_pipeline import (AgentPipeline, BasePipelineElement, InitQuery, OpenAILLM, SystemMessage,
                                      ToolsExecutionLoop, ToolsExecutor)
from agentdojo.agent_pipeline.agent_pipeline import load_system_message
from agentdojo.agent_pipeline.llms import openai_llm
from agentdojo.benchmark import load_task_results, run_task_without_injection_tasks
from agentdojo.functions_runtime import EmptyEnv
from agentdojo.logging import OutputLogger
from agentdojo.task_suite.load_suites import get_suite

HERE = Path(__file__).parent
RUNS = HERE / "runs"
MODEL = "gemini-3.1-flash-lite"
NAME = "gemini-flash-lite"

# the 9 tasks whose reference solution trips the rule, then 2 that should not (sanity check)
TASKS = [
    ("workspace", 20),
    ("banking", 2), ("banking", 12), ("banking", 15),
    ("slack", 5), ("slack", 9), ("slack", 10), ("slack", 18), ("slack", 19),
    ("banking", 0), ("travel", 0),
]

labels = yaml.safe_load((HERE / "labels.yaml").read_text())

client = openai.OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                       api_key=os.environ["GEMINI_API_KEY"],
                       max_retries=10)  # free tier gives a lot of 503s

# Workaround: Gemini 3 returns a "thought_signature" with every tool call and refuses
# the next request if it is not sent back. AgentDojo's OpenAI client drops it, so we
# keep the signatures by tool call id and patch them back in before each request.
signatures = {}
original_request = openai_llm.chat_completion_request


def request_with_signatures(client, model, messages, *args, **kwargs):
    patched = []
    for m in messages:
        if m["role"] == "assistant" and m.get("tool_calls"):
            calls = []
            for tc in m["tool_calls"]:
                if tc["id"] in signatures:
                    tc = dict(tc, extra_content=signatures[tc["id"]])
                calls.append(tc)
            m = dict(m, tool_calls=calls)
        patched.append(m)
    completion = original_request(client, model, patched, *args, **kwargs)
    for tc in completion.choices[0].message.tool_calls or []:
        extra = tc.model_dump().get("extra_content")
        if extra:
            signatures[tc.id] = extra
    return completion


openai_llm.chat_completion_request = request_with_signatures


def kinds_read(messages, suite_labels):
    # which kinds of data (private / trusted / untrusted / none) the successful tool calls so far have read
    kinds = set()
    for m in messages:
        if m["role"] == "tool" and m["error"] is None:
            kinds.add(suite_labels[m["tool_call"].function]["reads"])
    return kinds


class HideExternalTools(BasePipelineElement):
    """Sits in the tool loop after the executor. Once private and untrusted data have both
    been read, removes every tool with sends_external: true from the runtime, so the LLM
    does not see them on its next call."""

    def __init__(self, suite_labels):
        self.labels = suite_labels

    def query(self, query, runtime, env=EmptyEnv(), messages=[], extra_args={}):
        read = kinds_read(messages, self.labels)
        if "private" in read and "untrusted" in read:
            keep = {}
            for name, f in runtime.functions.items():
                if not self.labels[name]["sends_external"]:
                    keep[name] = f
            runtime.update_functions(keep)
        return query, runtime, env, messages, extra_args


def make_agent(suite_name, with_rule):
    llm = OpenAILLM(client, MODEL)
    steps = [ToolsExecutor(), llm]
    if with_rule:
        steps.insert(1, HideExternalTools(labels[suite_name]))
    agent = AgentPipeline([SystemMessage(load_system_message(None)), InitQuery(), llm, ToolsExecutionLoop(steps)])
    agent.name = NAME + "-rule" if with_rule else NAME
    return agent


with OutputLogger(str(RUNS)):
    for suite_name, n in TASKS:
        suite = get_suite("v1.2.2", suite_name)
        task = suite.get_user_task_by_id(f"user_task_{n}")
        for with_rule in (False, True):
            agent = make_agent(suite_name, with_rule)
            passed, _ = run_task_without_injection_tasks(suite, agent, task, RUNS, force_rerun=False)

            # quick summary line; traces.py does the proper write-up
            messages = load_task_results(agent.name, suite_name, task.ID, "none", "none", RUNS).messages
            read = kinds_read(messages, labels[suite_name])
            fired = with_rule and "private" in read and "untrusted" in read
            bad_calls = 0
            for m in messages:
                if m["role"] == "tool" and m["error"] and m["error"].startswith("Invalid tool"):
                    bad_calls += 1
            print(suite_name, n, "rule" if with_rule else "no rule", "| passed:", passed,
                  "| rule fired:", fired, "| calls to hidden tools:", bad_calls)
