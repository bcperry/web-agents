# Quickstart: Agents as Tools

End-to-end walkthrough for an admin configuring a parent agent that delegates to a sub-agent.

## Prereqs

- Backend running locally: `AUTH_DISABLED=true uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
- Frontend built: `cd frontend && npm run build` (or `npm run dev` for hot-reload).
- At least one existing agent (built-in or custom) you want to use as the **sub-agent**. For this quickstart we'll use the built-in `azgov` (Azure Government Specialist) profile.

## 1. Create the parent agent

1. Open the app at `http://localhost:8000`.
2. Click **ADMIN** → **AGENTS** → **+ NEW CUSTOM AGENT**.
3. Fill the basics:
   - **Name**: `Research Coordinator`
   - **Description**: `Coordinates research across specialized agents.`
   - **System Prompt**: `You coordinate research. When the user asks an Azure Government question, delegate to the consult_azgov_specialist tool and incorporate the response into your final answer.`
   - **Temperature**: `0.2`

## 2. Add a sub-agent as a tool

Scroll to the new **AGENTS AS TOOLS** section (it sits between **MCP SERVERS** and **STARTER QUESTIONS**).

1. Click **+ ADD AGENT TOOL**.
2. **Pick agent**: select `Azure Government Specialist` from the dropdown. (The agent you're currently editing is excluded; agents you've already picked are also excluded.)
3. The row immediately shows the **derived tool name** (`azure_government_specialist`) and **derived description** (the target agent's own description) as read-only previews — no further input required.
4. Save the agent.

If you try to:
- Pick the same agent twice → it's not in the picker (and backend rejects with **duplicate_target**).
- Pick yourself → the agent is not in the picker (and backend rejects with **self_reference**).
- Create a direct cycle (agent B already has agent A as a tool, then add B as a tool on A) → **direct_cycle** error blocks save.

If you later **rename** or **edit the description** of `Azure Government Specialist`, every parent that references it automatically picks up the new tool name and description on next load — nothing to update by hand.

## 3. Use the parent agent in chat

1. Click **BACK TO CHAT**.
2. Switch the active profile to **Research Coordinator** (it appears under **CUSTOM AGENTS**).
3. Send: `What's the FedRAMP High status of Azure OpenAI in Azure Government?`

Expected behavior:
- The Coordinator's LLM emits a tool call to `consult_azgov_specialist` with a `request` argument like `"FedRAMP High status of Azure OpenAI in Azure Government"`.
- The trace panel shows a `tool_call` event with `tool_kind: "sub_agent"` and the `agentRef` it resolved to.
- The sub-agent runs to completion and returns its answer.
- The Coordinator composes a final response that uses the sub-agent's reply.

## 4. Verify subsection header consistency

Open the agent edit page again and visually scan the form. All seven section headers should share one consistent style — clearly subordinate to the page title `Edit Agent`:

- `TOOLS`
- `AI SEARCH CONTEXT` (when shown)
- `SKILLS`
- `MCP SERVERS`
- `AGENTS AS TOOLS`
- `STARTER QUESTIONS`

Run `uv run python scripts/capture_admin_agent_screenshots.py --base-url http://localhost:8000` to regenerate the visual-verification screenshots that prove this.

## 5. Edge cases to try

- **Delete the sub-agent** (`Azure Government Specialist`). Reopen the parent agent — the orphaned ref appears with an error indicator and a remove button. Send a chat message anyway: the parent runs fine and the trace logs a warning that the sub-agent tool was omitted.
- **Rename the sub-agent**. The reference stays valid (it's by stable ID), and the picker shows the new name on next render.
- **Sub-agent timeout**: configure a sub-agent that uses a slow tool. The parent's tool call returns a structured error and the parent LLM continues.
