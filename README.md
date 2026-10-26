# ifc-agent-utility

Needs Python 3.10 or newer.

```
pip install agentdojo==0.1.35 pyyaml
```

Count on paper how many AgentDojo tasks the rule blocks (no LLM needed):

```
python measure.py
```

Prints a summary per suite and writes results.md.

Run it with an actual agent (Gemini 3.1 Flash Lite, 11 tasks, with and without the rule). Put a
Gemini API key in the GEMINI_API_KEY environment variable first, the free tier is enough but slow:

```
python run_agent.py
python traces.py
```

The conversations are saved in runs/. traces.py turns them into traces.md. Finished runs are
skipped on a rerun, delete the folder under runs/ to redo one.
