# ifc-agent-utility

How much does an information-flow rule cost an LLM agent in utility? The rule: once the agent has
read private and untrusted data, it may not send anything out. We label the tools, count how often
the rule bites, run an agent with and without it, and try a FIDES-style helper as a way around it.

Needs Python 3.10 or newer.

```
pip install agentdojo==0.1.35 pyyaml
```

## What is where

- `labels.yaml`, `measure.py`: labels for the AgentDojo tools, and a count on paper of how many
  tasks the rule blocks (`python measure.py`, no LLM needed).
- `benchmarks.md`: seven benchmarks tagged by what the agent needs from untrusted data, and why
  we picked TheAgentCompany.
- `handcheck.md`: tasks gone through by hand, with a verdict written before any run.
- `company/`: twelve TheAgentCompany tasks rebuilt as an AgentDojo suite, with the helper
  (`company/helper.py`). Its README says what is real and what is rebuilt.
- `run_agent.py`, `traces.py`: the agent runs. `traces.md` has every run we did, step by step.
- `notes.md`: what we saw.

## Running the agent

Gemini 3.1 Flash Lite. Put a key in the GEMINI_API_KEY environment variable first; the free tier
works but allows 500 requests a day.

```
python run_agent.py                     # everything in TASKS
python run_agent.py company 10 helper   # one task, one condition (none, rule, helper)
python traces.py
```

Runs are saved in runs/ (not in the repo) and skipped on a rerun; delete a folder there to redo one.

The TheAgentCompany data in `company/data/` comes from github.com/TheAgentCompany/TheAgentCompany
(MIT). AppWorld's data is not included, its license does not allow it.
