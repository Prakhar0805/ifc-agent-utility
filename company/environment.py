# The sandbox company: a chat server, a file cloud, a GitLab and a Plane board, all in memory.
# Shapes follow what the real sites expose; the data comes from TheAgentCompany (see README.md).
import json
from pathlib import Path

from agentdojo.functions_runtime import TaskEnvironment
from pydantic import BaseModel

DATA = Path(__file__).parent / "data"

CHANNELS = ["engineering", "general", "help-desk", "hr-announcements", "kudos", "product", "project-ai",
            "project-graphdb", "project-lowcode", "project-search", "project-streamdb", "project-webcrawler",
            "project-ecommerce", "frontend", "random", "sales-marketing", "tech-talk"]


class Message(BaseModel):
    sender: str
    text: str


class User(BaseModel):
    username: str
    name: str
    occupation: str


class Chat(BaseModel):
    me: str = "theagentcompany"
    users: list[User] = []
    channels: dict[str, list[str]] = {}        # channel -> member usernames
    dms: dict[str, list[Message]] = {}         # username -> the conversation, both directions
    posts: dict[str, list[Message]] = {}       # channel -> messages
    scenarios: dict[str, dict[str, str]] = {}  # colleague name -> what they know and how they behave in this task
    people: dict[str, dict[str, str]] = {}     # username -> persona fields (age, gender, public_info)


class File(BaseModel):
    content: str
    origin: str = "company"   # "outside" if someone outside the company wrote it (a receipt, a resume)
    kinds: list[str] = []     # helper mode: labels of hidden text that was written into the file


class Cloud(BaseModel):
    files: dict[str, File] = {}
    shares: dict[str, str] = {}   # share token -> path


class Comment(BaseModel):
    author: str
    body: str
    created_at: str


class Issue(BaseModel):
    iid: int
    title: str
    description: str
    state: str
    author: str
    created_at: str
    labels: list[str] = []
    comments: list[Comment] = []


class IssueSummary(BaseModel):
    iid: int
    title: str
    state: str
    author: str
    created_at: str
    comments: int


class GitLab(BaseModel):
    projects: dict[str, list[Issue]] = {}


class PlaneIssue(BaseModel):
    id: str
    title: str
    description: str
    state: str
    assignee: str | None = None
    url: str = ""


class PlaneProject(BaseModel):
    id: str = ""          # the project's id in Plane URLs, where a task gives one
    states: list[str]
    issues: list[PlaneIssue]


class Plane(BaseModel):
    projects: dict[str, PlaneProject] = {}


class Workspace(BaseModel):
    files: dict[str, str] = {}
    kinds: dict[str, list[str]] = {}   # helper mode: labels of hidden text written into a local file


class Var(BaseModel):
    content: str      # a tool result the main agent was not shown (helper mode)
    kinds: list[str]
    source: str


class CompanyEnvironment(TaskEnvironment):
    name: str = "company"
    task: str = ""
    chat: Chat = Chat()
    cloud: Cloud = Cloud()
    gitlab: GitLab = GitLab()
    plane: Plane = Plane()
    workspace: Workspace = Workspace()
    access_log: list[str] = []   # what was opened, for the checkpoints that look at the trajectory
    read_kinds: list[str] = []   # private / untrusted, as the tools report them, for the rule
    vars: dict[str, Var] = {}    # helper mode: hidden results, by name ($v1, $v2, ...)
    mode: str = ""               # "helper" when company/helper.py runs the tools

    def model_post_init(self, _):
        # environment.yaml is just a stub; the company is built from data/ here
        if not self.chat.users:
            fill_company(self)


def _load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def fill_task(env: CompanyEnvironment, task: str) -> CompanyEnvironment:
    """What differs per task: which colleagues are scripted, and the local files."""
    env.task = task
    env.chat.scenarios = {}
    scen = DATA / "scenarios" / f"{task}.json"
    if scen.exists():
        env.chat.scenarios = json.loads(scen.read_text(encoding="utf-8"))
    env.workspace = Workspace(files={"/instruction/template.md": (DATA / "files/template.md").read_text(encoding="utf-8")})
    env.access_log = []
    env.read_kinds = []
    env.vars = {}
    return env


def fill_company(env: CompanyEnvironment) -> CompanyEnvironment:
    """The company itself: people, channels, files, issues, boards."""
    env.chat = Chat()
    for p in _load("npc_definition.json"):
        name = f"{p['first_name']} {p['last_name']}"
        if p["first_name"] == "theagentcompany":
            continue
        username = f"{p['first_name']}_{p['last_name']}".lower()
        env.chat.users.append(User(username=username, name=name, occupation=p["occupation"]))
        env.chat.people[username] = {k: str(p.get(k, "")) for k in ("age", "gender", "public_info", "slack_channels")}
    for c in CHANNELS:
        env.chat.channels[c] = [env.chat.me]
    for username, p in env.chat.people.items():
        wanted = p["slack_channels"].lower()
        for c in CHANNELS:
            everything = ("all project" in wanted or "all technical" in wanted) and c.startswith("project-")
            if "#" + c in wanted or everything:
                env.chat.channels[c].append(username)
    env.cloud = Cloud(files={p: File(**f) for p, f in _load("files/cloud.json").items()})
    env.gitlab = GitLab(projects={p: [Issue(**i) for i in issues] for p, issues in _load("gitlab/issues.json").items()})
    env.plane = Plane(projects={p: PlaneProject(**b) for p, b in _load("plane/boards.json").items()})
    env.workspace = Workspace(files={"/instruction/template.md": (DATA / "files/template.md").read_text(encoding="utf-8")})
    return env
