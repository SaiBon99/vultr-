# #42 - Vultr Agent Runtime Hackathon

- **Presented by:** [Stockholm MLOps](https://luma.com/StockholmMLOps?k=c) ([stockholmmlops.se](https://www.stockholmmlops.se/))
- **Hosted by:** [Patrick Couch](https://luma.com/user/usr-z4hAbpeioT3LKep)
- **Date & Time:** Friday, November 27, 9:00 AM - 9:00 PM GMT+1
- **Location:** [Netlight Consulting AB, Regeringsgatan 25, 111 53 Stockholm, Sweden](https://www.google.com/maps/search/?api=1&query=59.332285500000005%2C18.0677667&query_place_id=ChIJtWhka-d3X0YRFru_m29yM9g)
- **Event URL:** https://luma.com/stockholm-nn3n?tk=OyYr4b
- **Registration:** Approval Required (134 Going)

---

## About Event

All right!!!

**Meetup #42** will take the shape of **a full day 12h Hackathon!!!** Bring your laptops and your hacking chops and let's go! (And yes, there will be food, drinks and refreshments throughout the day!)

### Agenda

- 9:00 - Doors open. Breakfast & Registration.
- 9:30 - Welcoming Remarks
- 10:00 - Hacking begins
- 12:00 - Lunch is served
- 19:00 - Project submission deadline
- 19:00 - Raffle
- 19:15 - Pizza, drinks & networking
- 21:00 - Doors close

The hackathon is centred around a single challenge:

**Build a web-based agent that performs real work - writing and running code, or operating a real browser - with every action contained inside a sandbox running on Vultr**. Your system should act as a centralized control layer that plans a task, dispatches it to an isolated execution environment, and returns verifiable output.

Projects should demonstrate multi-step agentic workflows, real executed results rather than described ones, and a production-style web application - all running on Vultr infrastructure.

Containment-first is required. An agent that only chats is a demo; an agent that executes safely is a product.

There will be a team from Vultr on-site to help guide you through the day! More detailed agenda will be provided. Stay tuned!

### Who should participate?

Developers, AI/ML and platform engineers, and technical founders building agentic applications. Participants will work in teams of 2-4. If you show up solo, we'll help you join/form a team!

### Pre-reqs

Laptop and GitHub account, working Python (or TypeScript) and API experience, and basic LLM familiarity. No special hardware needed. Vultr will provide credits for cloud compute, and we'll share a short prep guide beforehand.

### Prizes

The three most impressive projects formally submitted will all receive cash prizes and additional Vultr credits! (More on this later... Stay tuned!)

### Hackathon Infrastructure

- Deploy a VM-based backend on Vultr (mandatory)
- Agent LLM calls must go through Vultr Serverless Inference (mandatory)
- Vultr should be the central system of control and orchestration, not just static hosting
- Sandboxes run as containers or throwaway instances on Vultr, never inside your app process
  - Open Source Sandbox example solutions:
    - [OpenSandbox](https://github.com/opensandbox-group/OpenSandbox?utm_source=luma)
    - [gVisor](https://gvisor.dev/?utm_source=luma)
    - [E2B Sandboxes](https://github.com/e2b-dev/e2b?utm_source=luma)
    - [Microsandbox](https://microsandbox.dev/?utm_source=luma)

### Execution Pattern Integration

Build against one or both patterns:

**Pattern A - Sandboxed Code Execution**
User asks -> model writes code -> code runs in a container -> real output (chart, file, test log) returns -> model explains it. On error, stderr is fed back for a retry.

Examples:
- **CSV Analyst** - upload a spreadsheet, ask a question in plain English, get an actually-executed chart plus the code that produced it
- **Prove-It Code Reviewer** - paste a snippet or PR; the agent runs it and its tests in the sandbox and reports what really happened
- **Chart Anything** - natural language in, executed matplotlib or plotly image out
- **File Fixer** - messy CSV or JSON in, cleaned file out, with an executed before/after diff
- **Self-Healing Runner** - the agent runs code, reads the error, patches it, and retries, with the retry loop visible on screen

**Pattern B - Sandboxed Browser Use**
User gives a goal -> model plans -> Playwright in a container navigates, clicks, types -> screenshots return -> a vision model on Serverless Inference verifies the result -> repeat, with a human approving anything final.

Examples:
- **Comparison Shopper** - two or three product URLs in, screenshot-backed comparison table out
- **Form Filler** - structured data in, multi-step web form filled, with a screenshot trail and an approve-before-submit gate
- **Site QA Sweep** - point it at a web app and get back broken flows and links with screenshots and repro steps
- **Research with Receipts** - a brief where every claim links to a screenshot of its source
- **Page Watcher** - monitors listing or pricing pages, extracts structured data, and diffs against yesterday

### Containment Focus

Address real safety and reliability challenges in agent execution:
- Process isolation - execution never touches the host or app runtime
- Secret hygiene - no API keys or credentials inside the sandbox
- Resource limits - time and memory caps on every run
- Lifecycle discipline - reset or destroy the environment after each task

Show how isolation makes autonomous execution shippable.

### Production-Ready Web Application

- Must be accessible via a public web browser
- Demonstrate a real product-style experience
- Clear user flows, not just a local demo

### Key Positioning

- Vultr is the central backend powering execution and orchestration
- Your application plans, dispatches, and verifies real work
- Focus on platform thinking, not just a one-off demo

### Developer Expectations

**Each team must provide:**
- GitHub repository with setup and documentation
- Vultr VM backend deployment, with agent LLM calls through Vultr Serverless Inference
- Public demo URL
- Recorded demo video
- **One containment moment** in the video - the sandbox absorbing something unsafe, such as an `rm -rf`, an infinite loop, or a hostile web page
- Clear explanation of architecture and use case

### Technology

**Required**
- Vultr VM backend
- Web application deployed on Vultr
- Vultr Serverless Inference for agent reasoning (OpenAI-compatible; base URL [https://api.vultrinference.com/v1](https://api.vultrinference.com/v1?utm_source=luma))
- A sandbox isolated from your application process

**Strongly Recommended**
- Docker container as the sandbox boundary
- REST or WebSocket APIs for run status and streaming output
- Web dashboards showing the execution loop, retries, and screenshot trails
- Approve-before-submit gates on any irreversible browser action

**Optional**
- Vultr API to spin up a throwaway instance per task and destroy it afterward, making Vultr itself the sandbox fabric
- Vision-capable models on Serverless Inference for screenshot reasoning
- Playwright in Docker for browser automation

### Platform & App Acceleration

**To help teams ship faster, we recommend:**
- **Vultr Serverless Inference:** [https://docs.vultr.com/products/serverless/inference/provisioning](https://docs.vultr.com/products/serverless/inference/provisioning?utm_source=luma)
- **Live model list:** [https://api.vultrinference.com/v1/models](https://api.vultrinference.com/v1/models?utm_source=luma)
- **Vultr API (throwaway-instance pattern):** [https://www.vultr.com/api/](https://www.vultr.com/api/?utm_source=luma)
- **How to Set Up Agent Sandboxing on Vultr Cloud Compute:** [https://docs.vultr.com/how-to-set-up-agent-sandboxing-on-vultr-cloud-compute](https://docs.vultr.com/how-to-set-up-agent-sandboxing-on-vultr-cloud-compute?utm_source=luma)

### Access Method

- $200 in free Vultr credits per participant.
- Redemption guide: activate via the Vultr Setup Guide
- Redemption walkthrough video: [https://del1.vultrobjects.com/tech-talk/redeem-vultr-credits-for-hackathons.mp4](https://del1.vultrobjects.com/tech-talk/redeem-vultr-credits-for-hackathons.mp4?utm_source=luma)

That's it! That's all! Good luck!!!

---

## Event Blasts

*Pending retrieval: Luma blasts require an authenticated host/guest session or enabled Luma MCP tools.*
