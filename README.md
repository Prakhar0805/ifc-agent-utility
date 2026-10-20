## Files

- labels.yaml: the label for each tool
- measure.py: checks each task's ground-truth solution against the rule

## Run

Commands:
pip install agentdojo==0.1.35 pyyaml
python measure.py

It prints a summary and writes results.md with the per-task details.