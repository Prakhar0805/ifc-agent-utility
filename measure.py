# Counts AgentDojo tasks whose ground-truth solution calls an external tool
# after reading untrusted data, i.e. tasks the rule makes impossible.
from pathlib import Path

import yaml
from agentdojo.task_suite.load_suites import get_suites

HERE = Path(__file__).parent
labels = yaml.safe_load((HERE / "labels.yaml").read_text())


def check_task(sequence, suite_labels):
    first_untrusted = None
    for tool in sequence:
        if first_untrusted and suite_labels[tool]["sends_external"]:
            return first_untrusted, tool
        if suite_labels[tool]["reads"] == "untrusted" and not first_untrusted:
            first_untrusted = tool
    return first_untrusted, None


summary, per_task = [], []
total = total_blocked = total_external = 0

for name, suite in get_suites("v1.2.2").items():
    suite_labels = labels[name]
    missing = {t.name for t in suite.tools} - set(suite_labels)
    assert not missing, f"{name}: no label for {sorted(missing)}"

    env = suite.load_and_inject_default_environment({})
    external = blocked = 0
    for task_id, task in suite.user_tasks.items():
        sequence = [c.function for c in task.ground_truth(env.model_copy(deep=True))]
        first_untrusted, blocked_tool = check_task(sequence, suite_labels)
        external += any(suite_labels[t]["sends_external"] for t in sequence)
        blocked += blocked_tool is not None
        per_task.append((name, task_id, ", ".join(sequence), first_untrusted or "", blocked_tool or "",
                         "blocked" if blocked_tool else "ok"))

    n = len(suite.user_tasks)
    summary.append((name, n, external, blocked, 100 * blocked / n))
    total += n
    total_blocked += blocked
    total_external += external

summary.append(("all", total, total_external, total_blocked, 100 * total_blocked / total))

lines = ["# AgentDojo v1.2.2: tasks blocked by the rule\n",
         "| Suite | Tasks | Tasks using an external tool | Blocked | % blocked |",
         "|---|---|---|---|---|"]
for s, n, e, b, p in summary:
    lines.append(f"| {s} | {n} | {e} | {b} | {p:.1f}% |")
lines.append(f"\nStill possible: {total - total_blocked}/{total} ({100 * (total - total_blocked) / total:.1f}%)\n")
lines.append("| Suite | Task | Ground-truth tool calls | First untrusted read | Blocked call | Result |")
lines.append("|---|---|---|---|---|---|")
for row in per_task:
    lines.append("| " + " | ".join(row) + " |")

(HERE / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

for s, n, e, b, p in summary:
    print(f"{s:10s} {n:3d} tasks, {e:3d} use external tools, {b:3d} blocked ({p:.1f}%)")
