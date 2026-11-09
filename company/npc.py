# Colleagues. TheAgentCompany drives each one with an LLM (sotopia) that gets the persona from
# npc_definition.json and the task's scenarios.json as its goal. Same here, same text. A colleague
# with no entry in the task's scenarios.json does not answer, as in the benchmark.
# COMPANY_NPC=script swaps the LLM for the canned replies in data/scripted_replies.json (offline tests).
import json
import os
from pathlib import Path

from . import llm

SCRIPTED = json.loads((Path(__file__).parent / "data/scripted_replies.json").read_text(encoding="utf-8"))

SCENARIO = "People are working in a startup communicating through rocketchat. There is an AI agent working with them."


def prompt(user, persona, scenario):
    goal = "You goal is to collaborate with AI agent in the working space."
    for key in ("extra_info", "strategy_hint", "clarification_hint"):
        if key in scenario:
            goal += f" <{key}>{scenario[key]}</{key}>"
    return (f"Imagine you are {user.name}, your task is to act/speak as {user.name} would, keeping in mind "
            f"{user.name}'s social goal.\n"
            f"Here is the context of this interaction:\n"
            f"Scenario: {SCENARIO}\n"
            f"{user.name}'s background: {user.name} is a {persona['age']}-year-old {persona['gender'].lower()}, "
            f"{user.occupation} at The Agent Company. {persona['public_info']}\n"
            f"{user.name}'s goal: {goal}\n"
            f"You are chatting on RocketChat with the company's AI assistant (username theagentcompany). "
            f"Write only your next chat message as {user.name}: plain text, no name prefix, short unless your "
            f"goal asks you to give details.")


def reply(env, user, conversation):
    scenario = env.chat.scenarios.get(user.name) or env.chat.scenarios.get(user.name.split()[0])
    if not scenario:
        return None
    if os.environ.get("COMPANY_NPC") == "script":
        return SCRIPTED.get(env.task, {}).get(user.name)
    messages = [{"role": "system", "content": prompt(user, env.chat.people[user.username], scenario)}]
    for m in conversation[-20:]:
        role = "user" if m.sender == env.chat.me else "assistant"
        text = m.text if m.sender in (env.chat.me, user.username) else f"[{m.sender} wrote in the channel] {m.text}"
        if role == "assistant" and m.sender != user.username:
            role = "user"
        messages.append({"role": role, "content": text})
    return llm.chat(messages)
