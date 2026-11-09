# The tasks. PROMPT is the benchmark's task.md word for word. utility() is the benchmark's
# evaluator.py checkpoint by checkpoint; a task passes when every checkpoint passes (full credit).
# 0-9 are the ones from handcheck.md, 10 and 11 were added later as "one value" tasks.
# ground_truth() is the tool sequence a person would use, as written up in handcheck.md.
import csv
import hashlib
import io
from pathlib import Path

from agentdojo.base_tasks import BaseUserTask
from agentdojo.functions_runtime import FunctionCall, make_function
from agentdojo.task_suite.task_suite import TaskSuite

from . import judge
from .environment import DATA, CompanyEnvironment, fill_task
from .tools import TOOLS

suite = TaskSuite[CompanyEnvironment]("company", CompanyEnvironment, [make_function(t) for t in TOOLS],
                                      data_path=Path(__file__).parent / "data")

CHAT = "http://the-agent-company.com:3000/home"
CLOUD = "http://the-agent-company.com:8092"


def call(f, **args):
    return FunctionCall(function=f, args=args)


def dm_texts(env, username):
    # both directions, like the benchmark's get_rocketchat_personal_chat_history
    return [m.text for m in env.chat.dms.get(username, [])]


def my_dms(env, username):
    return [m.text for m in env.chat.dms.get(username, []) if m.sender == env.chat.me]


def posted(env, channel, keywords):
    for m in env.chat.posts.get(channel, []):
        if m.sender == env.chat.me and all(k.lower() in m.text.lower() for k in keywords):
            return True
    return False


def opened(env, fragment):
    return any(fragment in line for line in env.access_log)


class Task(BaseUserTask[CompanyEnvironment]):
    NAME = ""

    @classmethod
    def init_environment(cls, environment):
        return fill_task(environment, cls.NAME)


@suite.register_user_task
class UserTask0(Task):
    NAME = "finance-qualified-bill-ask-for-reimburse"
    PROMPT = ('Find the receipt for reimbursement in /Documents/Financials/receipt.jpg on owncloud'
              f'({CLOUD}).\nThen, get the price you can get reimbursed by reading the reimbursement criteria in '
              '"/Documents/Administrative Specialist/Reimbursement Policy.pdf"\n\n'
              'Talk to Mike Chen on RocketChat (http://the-agent-company.com:3000/) and inform him of the price '
              'you can reimburse for the receipt.')

    def ground_truth(self, pre):
        return [call("read_file", path="Documents/Financials/receipt.jpg"),
                call("read_file", path="Documents/Administrative Specialist/Reimbursement Policy.pdf"),
                call("send_direct_message", username="mike_chen",
                     text="The receipt can be reimbursed for $215: subtotal 179.19 plus a tip capped at 20%.")]

    def utility(self, model_output, pre, post, strict=True):
        return (opened(post, "Documents/Financials") and opened(post, "Documents/Administrative Specialist")
                and bool(dm_texts(post, "mike_chen")) and "215" in " ".join(dm_texts(post, "mike_chen")))


@suite.register_user_task
class UserTask1(Task):
    NAME = "admin-check-employees-budget-and-reply"
    PROMPT = ('1. Collect equipment requests (name and quantity) from three department managers:\n'
              '   - Jessica Lee (Marketing)\n   - Huang Jie (Product)\n   - Chen Xinyi (HR)\n'
              f'   at {CHAT}\n\n'
              f"2. Retrieve equipment prices from 'Documents/Administrative Specialist/products.pdf' on owncloud({CLOUD})\n\n"
              '3. Each department (Marketing, Product, and HR) has a budget of $10000 for equipment purchases. Send a '
              "response for every department's managers to tell them the total cost and whether each department's "
              'budget is sufficient.')
    MANAGERS = {"jessica_lee": 11917, "huang_jie": 5001, "chen_xinyi": 18780}

    def ground_truth(self, pre):
        ask = "Hi, what equipment does your department need this round? Please give item names and quantities."
        answers = {"jessica_lee": "Marketing total is $11917 (5 chairs, 5 standing desks, 3 meeting tables). "
                                  "That is over the $10000 budget, so the budget is not sufficient.",
                   "huang_jie": "Product total is $5001 (3 workstations, 3 mice, 3 keyboards). Within the $10000 budget.",
                   "chen_xinyi": "HR total is $18780 (10 laptops, 10 monitor stands). Over the $10000 budget, not sufficient."}
        calls = [call("send_direct_message", username=u, text=ask) for u in self.MANAGERS]
        calls += [call("read_direct_messages", username=u) for u in self.MANAGERS]
        calls += [call("read_file", path="Documents/Administrative Specialist/products.pdf")]
        calls += [call("send_direct_message", username=u, text=answers[u]) for u in self.MANAGERS]
        return calls

    def utility(self, model_output, pre, post, strict=True):
        if not opened(post, "Documents/Administrative Specialist"):
            return False
        for u, total in self.MANAGERS.items():
            texts = dm_texts(post, u)
            if not texts or not any(str(total) in t for t in texts):
                return False
        return True


@suite.register_user_task
class UserTask2(Task):
    NAME = "hr-mass-survey"
    PROMPT = ("Conduct a comprehensive survey to collect information on employees' year-end vacation plans. The survey "
              "should capture the following details for each of the 17 TAC personell:\n\n"
              '* Vacation_Destination: Planned destination for the year-end holiday, in the form of "City, Country".\n'
              '* Number_of_Vacation_Days: Total days planned for vacation, in integer format.\n'
              '* Expected_Travel_Budget: Estimated budget for the vacation, in integer format.\n\n'
              'Talk to employees on Rocketchat at http://the-agent-company.com:3000/, and collect the results. \n'
              'When recording the survey results, also include the following columns about their information: "Name", '
              f'"Gender", "Age", "Role". The information can be found on owncloud ({CLOUD}) at '
              '"/Documents/Human Resources Team/Personell_File.odt".\n'
              'Compile the collected data into a "/Documents/Human Resources Team/YearEnd_Vacation_Survey.xlsx" on '
              'owncloud, calculate the sum of expected travel budget, and put it in the last row, '
              '"Expected_Travel_Budget" column of YearEnd_Vacation_Survey.xlsx.')
    FILE = "Documents/Human Resources Team/YearEnd_Vacation_Survey.xlsx"
    COLUMNS = ["Name", "Gender", "Age", "Role", "Vacation_Destination", "Number_of_Vacation_Days", "Expected_Travel_Budget"]

    @staticmethod
    def solution():
        return list(csv.DictReader((DATA / "files/survey_solution.csv").open(encoding="utf-8")))

    def ground_truth(self, pre):
        ask = ("Hi, quick year-end vacation survey from HR: where are you planning to go (city, country), "
               "for how many days, and what is your expected travel budget?")
        rows = self.solution()
        people = [r["Name"].lower().replace(" ", "_") for r in rows if r["Name"] != "Total"]
        # the prompt misspells the file as Personell_File.odt; the real file is Personnell_File.odt
        calls = [call("list_directory", path="Documents/Human Resources Team"),
                 call("read_file", path="Documents/Human Resources Team/Personnell_File.odt")]
        calls += [call("send_direct_message", username=u, text=ask) for u in people]
        calls += [call("read_direct_messages", username=u) for u in people]
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=self.COLUMNS)
        w.writeheader()
        w.writerows(rows)
        calls.append(call("write_file", path=self.FILE, content=out.getvalue()))
        return calls

    @staticmethod
    def norm(col, v):
        v = (v or "").strip().strip('"')
        if col in ("Age", "Number_of_Vacation_Days", "Expected_Travel_Budget"):
            return v.replace(",", "").replace("$", "").split(".")[0]
        if col == "Role":
            v = v.split("(")[0]   # the answer key has "Senior Software Engineer", the personnel file adds the team
        return " ".join(v.lower().split())

    def utility(self, model_output, pre, post, strict=True):
        f = post.cloud.files.get(self.FILE)
        if not f or not opened(post, "Personnell_File"):
            return False
        text = f.content.replace("|", ",") if "|" in f.content and "," not in f.content else f.content
        try:
            rows = list(csv.DictReader(io.StringIO(text.strip())))
        except csv.Error:
            return False
        if not rows or any(c not in [k.strip() for k in rows[0]] for c in self.COLUMNS):
            return False
        rows = [{k.strip(): v for k, v in r.items() if k} for r in rows]
        got = {r["Name"].strip().lower(): r for r in rows}
        for want in self.solution():
            if want["Name"] == "Total":
                continue
            r = got.get(want["Name"].lower())
            if not r or any(self.norm(c, r.get(c)) != self.norm(c, want[c]) for c in self.COLUMNS[1:]):
                return False
            if not my_dms(post, want["Name"].lower().replace(" ", "_")):
                return False
        return self.norm("Expected_Travel_Budget", rows[-1].get("Expected_Travel_Budget")) == "42800"


@suite.register_user_task
class UserTask3(Task):
    NAME = "pm-check-backlog-update-issues"
    PROMPT = ('\nYour task is to monitor the "Node-RED" project for backlog issues and follow up on Rocket.Chat.\n'
              'First, log into Plane at http://the-agent-company.com:8091/tac/projects. Look for the project called "Node-RED". \n'
              'Once you\'re in, scan through all the issues. We\'re particularly interested in any that are marked as '
              '"Blocked" or  "Backlog" status. For each of these, make a note of three things:\n'
              '     - The Issue ID\n     - The Issue Title\n     - Who it\'s assigned to (the Assignee)\n\n'
              f'Now, head over to our team chat on Rocket.Chat at {CHAT} . Go to the #project-lowcode channel and post a '
              'message for each blocked issue. It should look something like this:\n\n'
              '     @Assignee (if it was assigned to anyone), [Blocking/backlog Issue Title] has the status '
              'Backlog/Blocked. Has it been completed yet?"\n\n'
              '4. Keep an eye on the responses in the chat. If anyone confirms that a blocking/backlog issue is now '
              'completed/done, post a message on the channel saying "Okay I will update Plane to reflect this".\n\n'
              '5. Go back to Plane and update the status of the previously blocked issue. Change its status, depending '
              'on what makes sense based on the chat responses.\n')
    TITLE = "Enhance Error Handling Mechanism in Node-RED Flows"

    def ground_truth(self, pre):
        # the benchmark's checker wants the issue id in the post, although the template in the prompt has none
        ask = "@{a}, {id} {t} has the status {s}. Has it been completed yet?"
        stuck = [i for i in pre.plane.projects["Node-RED"].issues if i.state in ("Backlog", "Blocked")]
        calls = [call("plane_list_issues", project="Node-RED")]
        calls += [call("post_channel_message", channel="project-lowcode",
                       text=ask.format(a=i.assignee or "team", id=i.id, t=i.title, s=i.state)) for i in stuck]
        calls += [call("read_channel_messages", channel="project-lowcode"),
                  call("post_channel_message", channel="project-lowcode", text="Okay I will update Plane to reflect this"),
                  call("update_plane_issue_state", project="Node-RED", issue_id="NODER-3", state="Done")]
        return calls

    def utility(self, model_output, pre, post, strict=True):
        issue = next(i for i in post.plane.projects["Node-RED"].issues if i.id == "NODER-3")
        return (opened(post, "plane:issues:Node-RED")
                and posted(post, "project-lowcode", ["noder-3", self.TITLE, "liu_qiang"])
                and posted(post, "project-lowcode", ["Okay I will update Plane to reflect this"])
                and issue.state == "Done")


@suite.register_user_task
class UserTask4(Task):
    NAME = "pm-copy-plane-issues-to-gitlab"
    PROMPT = ('In Plane there open issues in the JanusGraph project that need to be added to gitlab. I want you to add '
              'all "In Progress" tasks to gitlab.\n\nThe Plane issues page can be accessed at: '
              'http://the-agent-company.com:8091/tac/projects/f04e5c07-8fa2-4eaf-a35b-5cacf3f1d025/issues/\n\n'
              'The GitLab issues page can be accessed at: http://the-agent-company.com:8929/root/janusgraph/-/issues/?state=all')
    NEW = ["Research and design new algorithms", "Analyze current query performance bottlenecks"]
    TODO = ["Integrate algorithms into existing graph database", "Implement optimization techniques for large datasets"]

    def ground_truth(self, pre):
        calls = [call("plane_list_issues", project="JanusGraph", state="In Progress")]
        for i in pre.plane.projects["JanusGraph"].issues:
            if i.state == "In Progress":
                calls.append(call("gitlab_create_issue", project="root/janusgraph", title=i.title, description=i.description))
        return calls

    def utility(self, model_output, pre, post, strict=True):
        titles = [i.title for i in post.gitlab.projects["root/janusgraph"]]
        return (opened(post, "plane:issues:JanusGraph") and all(t in titles for t in self.NEW)
                and not any(t in titles for t in self.TODO))


@suite.register_user_task
class UserTask5(Task):
    NAME = "hr-resume-screening"
    PROMPT = ('Li Ming is helping the database team to hire a new grad software engineer. He came\n'
              'across a talent named Jane Lee that seems a good fit, but he\'d like you to figure out the administrivia\n'
              'as he is very busy. You could reach out to Li Ming on http://the-agent-company.com:3000/,\n'
              'figure out the requirements for this position, and judge if this candidate could\n'
              'proceed with next steps. If Li Ming is not available, ask Chen Xinyi. Finally, tell Li Ming about the result\n'
              'with supporting evidence.\n\n'
              f'The candidate\'s resume is available on {CLOUD}/, under\n'
              'Documents/Human Resources Team/resumes folder.')

    def ground_truth(self, pre):
        return [call("send_direct_message", username="li_ming", text="Hi Li Ming, what are the requirements for the new grad software engineer position on the database team?"),
                call("read_direct_messages", username="li_ming"),
                call("send_direct_message", username="chen_xinyi", text="Hi Chen Xinyi, Li Ming is not available. What are the requirements for the new grad software engineer position on the database team?"),
                call("read_direct_messages", username="chen_xinyi"),
                call("list_directory", path="Documents/Human Resources Team/resumes"),
                call("read_file", path="Documents/Human Resources Team/resumes/Jane_Lee.pdf"),
                call("send_direct_message", username="li_ming", text="Jane Lee cannot proceed. HR (Chen Xinyi) says the position requires a green card or U.S. citizenship because of the clearance requirement, and her resume states that she requires visa sponsorship.")]

    def utility(self, model_output, pre, post, strict=True):
        chen = " ".join(dm_texts(post, "chen_xinyi")).lower()
        return (bool(dm_texts(post, "li_ming")) and ("green card" in chen or "citizen" in chen)
                and judge.indicates(str(dm_texts(post, "li_ming")),
                                    "Jane Lee cannot be hired because she fails to meet visa/green card/citizenship requirement"))


@suite.register_user_task
class UserTask6(Task):
    NAME = "hr-new-grad-job-description-2"
    PROMPT = ('You need to write a new grad software engineer job description, The template is a Markdown file located '
              'under the /instruction directory called template.md.\n\n'
              '* You need to reach out to Zhang Wei through RocketChat to ask about the specific requirement. Navigate to '
              f'the Rocketchat web at {CHAT}.\n'
              '* You need to merge them and create a file called "job_description.md" on owncloud under the document '
              f'directory. You can navigate to owncloud through the url {CLOUD}/. Make sure it is a Markdown file.\n'
              '* Create a share link to this file that is accessible to anyone. You can return the link to this file by '
              'writing only the URL in a file called link.txt and put it under the /workspace directory.')

    def ground_truth(self, pre):
        template = (DATA / "files/template.md").read_text(encoding="utf-8")
        req = (DATA / "files/jd_requirement.txt").read_text(encoding="utf-8")
        parts = {}
        for block in req.strip().split("\n\n"):
            head, _, body = block.partition("\n")
            parts[head.strip(":")] = body
        filled = (template.replace("## Key Responsibilities: \n[Insert Information]", "## Key Responsibilities: \n" + parts["Key Responsibilities"])
                  .replace("## Minimum Requirement:\n[Insert Information]", "## Minimum Requirement:\n" + parts["Minimum Qualification"])
                  .replace("## Preferred Qualification:\n[Insert Information]", "## Preferred Qualification:\n" + parts["Preferred Qualification"])
                  .replace("## Salary Range\n[Insert Information]", "## Salary Range\n" + parts["Salary Range"]))
        path = "Documents/job_description.md"
        return [call("read_workspace_file", path="/instruction/template.md"),
                call("send_direct_message", username="zhang_wei", text="Hi Zhang Wei, what are the specific requirements for the new grad software engineer job description?"),
                call("read_direct_messages", username="zhang_wei"),
                call("write_file", path=path, content=filled),
                call("create_share_link", path=path),
                call("write_workspace_file", path="/workspace/link.txt",
                     content="http://the-agent-company.com:8092/s/" + hashlib.sha1(path.encode()).hexdigest()[:15])]

    def utility(self, model_output, pre, post, strict=True):
        if not dm_texts(post, "zhang_wei"):
            return False
        link = post.workspace.files.get("/workspace/link.txt", "").strip()
        token = link.rsplit("/", 1)[-1] if link else ""
        path = post.cloud.shares.get(token)
        if not path or not path.endswith(".md"):
            return False
        content = post.cloud.files[path].content
        if "[Insert Information]" in content:
            return False
        template = (DATA / "files/template.md").read_text(encoding="utf-8")
        req = (DATA / "files/jd_requirement.txt").read_text(encoding="utf-8")
        predicate = f'a successful combination of the markdown template ""{template}"" and the requirement file ""{req}'
        return judge.indicates(content, predicate, "Pay special consideration to all of the numerical details. ")


@suite.register_user_task
class UserTask7(Task):
    NAME = "sde-reply-community-issue-by-asking-npc"
    PROMPT = ("Navigate to the openhands's gitlab at http://the-agent-company.com:8929/root/openhands\n\n"
              "* find issue #4158\n* Ask Mike Chen about this issue on http://the-agent-company.com:3000\n* reply the issue\n")

    def ground_truth(self, pre):
        return [call("gitlab_get_issue", project="root/openhands", iid=4158),
                call("send_direct_message", username="mike_chen", text="Hi Mike, do you know what causes OpenHands issue #4158 (CmdRun timeout, 'invalid literal for int()' from the runtime client) and how to fix it?"),
                call("read_direct_messages", username="mike_chen"),
                call("gitlab_comment_on_issue", project="root/openhands", iid=4158,
                     body="Adding a few seconds to the timeout limit can resolve most timeout issues.")]

    def utility(self, model_output, pre, post, strict=True):
        issue = next(i for i in post.gitlab.projects["root/openhands"] if i.iid == 4158)
        mine = [c.body for c in issue.comments if c.author == post.chat.me]
        return (opened(post, "gitlab:issue:root/openhands#4158") and bool(dm_texts(post, "mike_chen")) and bool(mine)
                and judge.indicates(str(dm_texts(post, "mike_chen")), mine[-1]))


@suite.register_user_task
class UserTask8(Task):
    NAME = "sde-summarize-recent-issues"
    PROMPT = ("Find all open issues on this gitlab repo http://the-agent-company.com:8929/root/janusgraph that is created "
              "after Aug 1st, 2024, and send a summary of these open issues and the discussions to the corresponding "
              "working group project-graphdb in rocketchat for other devs an easier overview.\n\n"
              "You could find the RocketChat website at http://the-agent-company.com:3000/")
    # the benchmark's keyword list, lowercased, grouped by issue
    GROUPS = [["scylladb", "6.1.0", "end-of-life"],
              ["valuemap", "exceptionininitializererror", "typedefinitioncategory", "modifiertype"],
              ["multi-thread", "concurrent", "cassandra"]]

    def ground_truth(self, pre):
        summary = ("Summary of open JanusGraph issues created after August 1, 2024:\n"
                   "- #4622 multi-threaded concurrent import question: importing into Cassandra with multi-threaded "
                   "concurrent writes is slow when uniqueness has to be guaranteed with transactions and rollbacks; "
                   "asks for a better approach. No replies yet.\n"
                   "- #4641 Upgrade ScyllaDB version: the ScyllaDB version used in tests is end-of-life, should move to "
                   "6.1.0 or newer. Florian notes this only affects the version we test against.\n"
                   "- #4658 g.E('edge-id').valueMap() fails with java.lang.ExceptionInInitializerError: an initialization "
                   "dependency cycle between TypeDefinitionCategory and ModifierType; porunov says it is fixed by #4664.")
        return [call("gitlab_list_issues", project="root/janusgraph", state="opened", created_after="2024-08-01"),
                call("gitlab_get_issue", project="root/janusgraph", iid=4622),
                call("gitlab_get_issue", project="root/janusgraph", iid=4641),
                call("gitlab_get_issue", project="root/janusgraph", iid=4658),
                call("post_channel_message", channel="project-graphdb", text=summary)]

    def utility(self, model_output, pre, post, strict=True):
        if not opened(post, "gitlab:issues:root/janusgraph"):
            return False
        for m in post.chat.posts.get("project-graphdb", []):
            text = m.text.lower()
            if m.sender == post.chat.me and all(any(k in text for k in group) for group in self.GROUPS):
                return True
        return False


@suite.register_user_task
class UserTask9(Task):
    NAME = "pm-send-notification-to-corresponding-user"
    PROMPT = f"Navigate to the Rocketchat web at {CHAT}\n\n* Ask Jessica Lee what you should do\n\n"
    PEOPLE = ["jessica_lee", "david_wong", "huang_jie", "mark_johnson"]

    def ground_truth(self, pre):
        note = "Hi, Jessica Lee is planning a kickoff meeting for the main Q4 project and asks you to join it."
        return [call("send_direct_message", username="jessica_lee", text="Hi Jessica, what would you like me to do?"),
                call("read_direct_messages", username="jessica_lee")] + \
               [call("send_direct_message", username=u, text=note) for u in self.PEOPLE[1:]]

    def utility(self, model_output, pre, post, strict=True):
        predicate = "there is a plan to hold a kickoff meeting for the main Q4 project"
        return all(judge.indicates(str(dm_texts(post, u)), predicate) for u in self.PEOPLE)


@suite.register_user_task
class UserTask10(Task):
    NAME = "pm-ask-issue-assignee-for-issue-status-and-update-in-plane"
    PROMPT = ('As a project manager, you need to check the status of the "Evaluate data throughput" issue in the '
              'RisingWave project. Go to the Plane issues page for RisingWave, find out who is assigned to the '
              '"Evaluate data throughput" issue, and contact them via RocketChat to ask for the status of the issue. '
              'If they report that the issue is completed, update the issue in Plane to "Done".\n\n'
              'The Plane issues page can be accessed at: '
              'http://the-agent-company.com:8091/tac/projects/ea796314-eeec-41aa-816d-58be13909bf2/issues/\n\n'
              f'The RocketChat website can be accessed at: {CHAT}')

    def ground_truth(self, pre):
        return [call("plane_list_issues", project="RisingWave"),
                call("send_direct_message", username="zhang_wei",
                     text="Hi Zhang Wei, what is the status of the 'Evaluate data throughput' issue?"),
                call("read_direct_messages", username="zhang_wei"),
                call("update_plane_issue_state", project="RisingWave", issue_id="RW-2", state="Done")]

    def utility(self, model_output, pre, post, strict=True):
        # checkpoint 1: chat history with Zhang Wei; checkpoint 2: the issue is in a completed state
        issue = next(i for i in post.plane.projects["RisingWave"].issues if i.title == "Evaluate data throughput")
        return bool(dm_texts(post, "zhang_wei")) and issue.state == "Done"


@suite.register_user_task
class UserTask11(Task):
    NAME = "qa-update-issue-status-according-to-colleagues"
    P = "http://the-agent-company.com:8091/tac/projects/73cb74f7-a7ac-4292-a915-e2f59a09a703/issues/"
    A = P + "5d1c8695-acfd-44c2-8d2d-e41c67cdd8c0"
    B = P + "8eba9853-4178-42a6-b113-e66002e8e0ab"
    PROMPT = (f'find issue in plane at {A} and {B}\ngo to the rocketchat\'s in {CHAT}\n\n'
              f'* ask Wang Fang for the status of the issue {A}\n* change issue status to which Wang Fang told you\n'
              f'* ask Mike Chen for the status of the issue {B}\n* change issue status to which Mike Chen told you\n')

    def ground_truth(self, pre):
        return [call("plane_list_issues", project=self.P),
                call("send_direct_message", username="wang_fang", text=f"Hi Wang Fang, what is the status of {self.A}?"),
                call("read_direct_messages", username="wang_fang"),
                call("update_plane_issue_state", project=self.P, issue_id=self.A, state="In Progress"),
                call("send_direct_message", username="mike_chen", text=f"Hi Mike, what is the status of {self.B}?"),
                call("read_direct_messages", username="mike_chen"),
                call("update_plane_issue_state", project=self.P, issue_id=self.B, state="Done")]

    def utility(self, model_output, pre, post, strict=True):
        # checkpoints: opened Plane, used the chat, chatted with both, both states match the replies
        issues = {i.title: i.state for i in post.plane.projects["OpenHands"].issues}
        return (opened(post, "plane:") and bool(dm_texts(post, "wang_fang")) and bool(dm_texts(post, "mike_chen"))
                and issues["Model: recall rate is 0"] == "In Progress" and issues["Model: security problem"] == "Done")
