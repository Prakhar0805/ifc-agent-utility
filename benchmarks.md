# Which benchmark to do the hand analysis on

## Second pass (Nov 2026)

The first pass picked AppWorld, and the hand check there (handcheck.md) came out friendly: 7 of 10
tasks still work under the rule with a helper or a plan, because the untrusted data in AppWorld is
almost always one number, one id, a yes/no, or something that can be passed on by reference. That
is not what we are after. We want ordinary, non-attack tasks where the rule costs real utility even
for a careful human. So the criterion changed.

A task is "hard under the rule" if one of these holds:

- B: the instruction lives in the untrusted content ("do what she asked in chat", "handle the
  requests in the inbox").
- C: the outgoing text has to be written from the untrusted content (summarise, reply, draft, fill
  a sheet from a document, copy issue text somewhere others see it).
- D: several messages or documents have to be read and the agent decides from them what to do.

Everything else is A (the untrusted content supplies one value or one pick, so a helper could
return it typed) or 0 (the rule never fires: no untrusted read, no private read, or nothing goes
out).

I tagged tasks from seven benchmarks this way, all of them when there were at most 200, otherwise
a random sample of 60 (seed 0, stratified by domain). The tagging is by reading the instruction, so it is a judgement, and the
notes at the end say where the judgement calls were.

| Benchmark | Tagged | Rule fires | Hard (B/C/D) | Hard among firing | Tasks are | Setup to run | License |
|---|---|---|---|---|---|---|---|
| tau2-bench | 60 of 278 | 49 (82%) | 36 (60%): B 10, C 7, D 19 | 73% | customer service chat, agent changes bookings and orders | pip, litellm, any API model | MIT |
| TheAgentCompany | 175 of 175 | 71 (41%) | 31 (18%): B 1, C 28, D 2 | 44% | software company work over chat, GitLab, ownCloud, Plane | Docker, 30 GB, OpenHands, days per run | MIT |
| OfficeBench | 60 of 300 | 7 (12%) | 3 (5%): B 1, C 2 | 43% | word, excel, email, calendar in a sandbox; short and sloppy | Docker | Apache 2 |
| Toolathlon | 108 of 108 | 20 (19%) | 5 (5%): B 1, C 4 | 25% | real apps: Canvas, WooCommerce, Notion, GitHub, email | Docker plus real accounts for Google, GitHub, Notion, Snowflake | none stated |
| AppWorld | 60 of 244 | 16 (27%) | 3 (5%): B 1, D 2 | 19% | everyday phone, Gmail, Venmo, Amazon, Spotify | pip | data not redistributable |
| WorkBench | 60 of 690 | 0 | 0 | - | 69 email/calendar/CRM templates, 10 paraphrases each | pip | MIT |
| WebArena | 60 of 812 | 2 (3%) | 0 | 0% | web browsing on a shop, Reddit, GitLab clone; half the tasks are questions | Docker, very large | Apache 2 |

Two benchmarks stand out, for different reasons.

**TheAgentCompany** is the one that matches our setting: an assistant working for one person inside
a company, reading what colleagues wrote (chat, issues, documents, resumes, vendor quotes), using
internal data, and producing things others see. 71 of 175 tasks trip the rule and 31 of those are
hard, almost all of kind C: the output is a message, an issue, a wiki page, a shared sheet or a
slide deck written from what other people wrote. Examples: reply to a community issue after asking
a colleague, write a job description from two colleagues' chat answers, summarise recent issues in
a channel, copy issue text into a wiki, fill a survey sheet from 17 chat replies. Only one task is
pure B ("ask Jessica what you should do"). Downsides: no tool list (the agent drives a browser), so
labels have to be per action type rather than per API, and running it needs Docker, 30 GB and an
OpenHands setup. Reading the tasks needs none of that.

**tau2-bench** has the highest numbers by far, but the trust model is turned around: the agent works
for the airline or the shop, its private data is the customer's record, and the untrusted party is
the customer, who is also the one giving instructions. Every task is "the customer talks, the agent
changes their account", which is kind B or D by construction. It is a real setting (every
customer-facing agent has it) and it is the cheapest to run end to end. But it is not the
"assistant reads my inbox" picture, and our rule would block nearly every task there, which says
more about the rule's fit than about the rescue strategies.

My pick for the hand check is TheAgentCompany, with tau2 as the thing to run later if we want
numbers from an agent cheaply.

## Judgement calls in the tagging

- TheAgentCompany: company records (attendance, salary, price lists) counted as private only; free
  text written by people (chat, issues, documents, resumes, quotes) as untrusted; internal repo code
  as private. Saving a file into a shared ownCloud folder counted as going out. Asking a colleague a
  fixed question first and reading the reply later is A when all outgoing text follows from the
  instruction.
- tau2: the customer's messages are the untrusted input. The 7 C tasks are all hand-overs to a human
  agent with a summary written from the chat; nothing grades that summary, so they could be called A.
  Telecom is odd: the "untrusted" content is the customer reading out their own phone's status.
- AppWorld: Amazon catalog and Spotify song data trusted; files in the file system untrusted; own
  notes private. Venmo and Spotify likes, playlists and own-file edits do not count as going out.
- OfficeBench: many input files have no stated origin and were counted untrusted; with a stricter
  reading the 7 firing tasks drop to 4.
- Toolathlon: customer orders and support tickets inside the user's own shop counted as untrusted;
  if they are the user's own data, firing drops from 20 to 14.
- WebArena: only reading own orders, repos, profile or admin data counted as private, not being
  logged in. OSM and Wikipedia counted as reference data.

## First pass (Oct 2026), kept for the record

The first criterion was: realistic tasks, labelable tools, a readable reference solution per task,
tasks that mix the three ingredients, and no heavy setup. That pointed to AppWorld, the only one
with readable solution programs, and it was right for the first hand check. The old table:

| Benchmark | Tasks | What it is | Solutions readable? | Mixes the three? | Setup to read tasks |
|---|---|---|---|---|---|
| AppWorld | 750 | everyday tasks over Gmail, Venmo, Amazon, Spotify, Todoist, SimpleNote, Splitwise, Phone, FileSystem; 457 APIs | yes, solution program for the 147 train/dev tasks | yes | pip |
| TheAgentCompany | 175 | software company: GitLab, RocketChat, ownCloud, Plane; browser driven | no, only checkpoints | yes, often | Docker, 30 GB |
| tau2-bench | ~50 per domain | customer service with a policy and a simulated user | expected actions per task | the customer is the only other party | pip |
| MCPMark | 127 | Notion, GitHub, Postgres, Playwright, Filesystem | verify.py only | no email, chat or payments | containers |
| MCP-Universe | ? | web search, maps, GitHub, Notion, Blender | no | mostly lookups | API keys |
| MCP-Atlas | 500 | 36 MCP servers | reference trajectory | write actions and personal data excluded on purpose | API keys |
| Toolathlon | ~100 | real software | evaluators, no solution program | some | heavy |

MCPMark, MCP-Universe and MCP-Atlas were dropped for good after this: no third-party content or no
outgoing action, so the rule has nothing to bite on.

The AppWorld data is under a license that forbids redistributing it unencrypted, so the data/
folder stays out of the repo. Task instructions are public on their website, so quoting those is
fine. Toolathlon states no license at all; its task text should not be copied in bulk either.
