# Run Gemini on a handful of AgentDojo tasks, once normally and once with the rule
# (after the agent has read private AND untrusted data, hide every external tool).
# The company tasks (TheAgentCompany sandbox) get a third run with a FIDES-style helper
# (company/helper.py). Needs GEMINI_API_KEY in the environment. Finished runs are reused on a rerun.
import os
import sys
import time
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
from agentdojo.task_suite import task_suite as task_suite_module
from agentdojo.task_suite.load_suites import get_suite

import company  # noqa: F401  registers the "company" suite, the TheAgentCompany sandbox
from company.helper import PROMPT as HELPER_PROMPT
from company.helper import AddHelper, QuarantineExecutor
from company.tools import kinds_of

HERE = Path(__file__).parent
RUNS = HERE / "runs"
MODEL = "gemini-3.1-flash-lite"
NAME = "gemini-flash-lite"

# AgentDojo: the 9 tasks whose reference solution trips the rule, then 2 that should not (sanity check).
# company: the TheAgentCompany tasks we ran (3, 4 and 5 are built but not run yet).
TASKS = [
    ("workspace", 20),
    ("banking", 2), ("banking", 12), ("banking", 15),
    ("slack", 5), ("slack", 9), ("slack", 10), ("slack", 18), ("slack", 19),
    ("banking", 0), ("travel", 0),
] + [("company", n) for n in (0, 1, 2, 6, 7, 8, 9, 10, 11)]
MODES = []
# python run_agent.py company 0 3          -> only those tasks
# python run_agent.py company 7 helper     -> only that mode
if len(sys.argv) > 1:
    MODES = [a for a in sys.argv[2:] if a in ("none", "rule", "helper")]
    TASKS = [(sys.argv[1], int(a)) for a in sys.argv[2:] if a.isdigit()]

labels = yaml.safe_load((HERE / "labels.yaml").read_text())
labels.update(yaml.safe_load((HERE / "labels_theagentcompany.yaml").read_text()))

client = openai.OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                       api_key=os.environ["GEMINI_API_KEY"],
                       max_retries=10)  # free tier gives a lot of 503s

# Gemini 3 sends a thought_signature with each tool call and wants it back on the next request.
# AgentDojo's client drops it, so we keep them by call id and put them back.
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
    for attempt in range(30):  # the free tier answers 503 "high demand" for minutes at a time
        try:
            completion = original_request(client, model, patched, *args, **kwargs)
            break
        except (openai.InternalServerError, openai.RateLimitError) as e:
            if attempt == 29:
                raise
            print("api busy, waiting:", str(e)[:80])
            time.sleep(30)
    for tc in completion.choices[0].message.tool_calls or []:
        extra = tc.model_dump().get("extra_content")
        if extra:
            signatures[tc.id] = extra
    return completion


openai_llm.chat_completion_request = request_with_signatures

# AgentDojo retries a task up to 3 times on the same environment when the last message has no text,
# and keeps only the last try. The second try then sees what the first one did. We want one try.
original_output = task_suite_module.model_output_from_messages
task_suite_module.model_output_from_messages = lambda messages: original_output(messages) or []


def kinds_read(messages, suite_labels, env=None):
    # which kinds of data (private / trusted / untrusted / none) the successful tool calls so far have read
    kinds = set()
    for m in messages:
        if m["role"] == "tool" and m["error"] is None:
            kinds.add(suite_labels[m["tool_call"].function]["reads"])
    # the company tools report what they read themselves, since one tool can read both kinds
    kinds.update(getattr(env, "read_kinds", []))
    return kinds


class HideExternalTools(BasePipelineElement):
    """After a private and an untrusted read, drops every external tool from the runtime."""

    def __init__(self, suite_labels):
        self.labels = suite_labels

    def query(self, query, runtime, env=EmptyEnv(), messages=[], extra_args={}):
        read = kinds_read(messages, self.labels, env)
        if "private" in read and "untrusted" in read:
            keep = {}
            for name, f in runtime.functions.items():
                if not self.labels[name]["sends_external"]:
                    keep[name] = f
            runtime.update_functions(keep)
        return query, runtime, env, messages, extra_args


def make_agent(suite_name, mode):
    # mode: "none" (plain agent), "rule" (hide external tools), "helper" (quarantine + typed helper, company only)
    llm = OpenAILLM(client, MODEL)
    system = load_system_message(None)
    start = []
    if mode == "helper":
        steps = [QuarantineExecutor(labels[suite_name]), llm]
        system += "\n\n" + HELPER_PROMPT
        start = [AddHelper()]
    else:
        steps = [ToolsExecutor(), llm]
    if mode == "rule":
        steps.insert(1, HideExternalTools(labels[suite_name]))
    turns = 40 if suite_name == "company" else 15  # the survey task alone needs 17 messages and 17 reads
    agent = AgentPipeline([SystemMessage(system), InitQuery(), *start, llm, ToolsExecutionLoop(steps, max_iters=turns)])
    agent.name = NAME if mode == "none" else f"{NAME}-{mode}"
    return agent


def errors(messages, start):
    return sum(1 for m in messages if m["role"] == "tool" and m["error"] and m["error"].startswith(start))


with OutputLogger(str(RUNS)):
    for suite_name, n in TASKS:
        suite = get_suite("v1.2.2", suite_name)
        task = suite.get_user_task_by_id(f"user_task_{n}")
        modes = MODES or (["none", "rule", "helper"] if suite_name == "company" else ["none", "rule"])
        for mode in modes:
            agent = make_agent(suite_name, mode)
            passed, _ = run_task_without_injection_tasks(suite, agent, task, RUNS, force_rerun=False)

            # quick summary line; traces.py does the proper write-up
            messages = load_task_results(agent.name, suite_name, task.ID, "none", "none", RUNS).messages
            line = [suite_name, n, mode, "| passed:", passed]
            if mode == "rule":
                read = kinds_read(messages, labels[suite_name])
                if suite_name == "company":
                    for m in messages:
                        if m["role"] == "tool" and m["error"] is None:
                            text = " ".join(c["content"] for c in m["content"] if c.get("type") == "text")
                            read |= kinds_of(m["tool_call"].function, m["tool_call"].args, text)
                line += ["| rule fired:", "private" in read and "untrusted" in read,
                         "| calls to hidden tools:", errors(messages, "Invalid tool")]
            if mode == "helper":
                asks = sum(1 for m in messages if m["role"] == "tool" and m["tool_call"].function == "ask_helper")
                line += ["| helper calls:", asks, "| refused calls:", errors(messages, "Refused")]
            print(*line)
