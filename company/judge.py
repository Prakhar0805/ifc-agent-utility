# The LLM judge, same question as TheAgentCompany's evaluate_with_llm in base_image/common.py.
# COMPANY_JUDGE=yes makes it always say yes, for offline checks of the plumbing.
import os

from . import llm


def indicates(content, predicate, additional_prompt=""):
    if not content:
        return False
    if os.environ.get("COMPANY_JUDGE") == "yes":
        return True
    query = (f'Does the content """{content}""" indicate {predicate}?'
             f' Please answer "yes" if it does, or "no" if it does not. {additional_prompt}')
    answer = llm.chat([{"role": "user", "content": query}]).lower().strip()
    return "yes" in answer
