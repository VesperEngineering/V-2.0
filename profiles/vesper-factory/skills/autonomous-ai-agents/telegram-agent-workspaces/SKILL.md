---
name: telegram-agent-workspaces
description: Organize and operate focused Hermes workstreams through Telegram groups without losing integration discipline.
version: 1.0.0
author: Hermes Agent
---

# Telegram Agent Workspaces

## Use when

A user wants to coordinate several Hermes workstreams through Telegram groups or topics while retaining a single integration/decision thread.

## Workspace design

1. Keep one **main integration chat** for cross-stream decisions, evidence review, and approval of changes.
2. Create one focused group/topic per independent concern, for example dashboard/UI, compute research, or feature research.
3. Prefer concise, visually scannable group names. A `// <workstream>` convention works well when the user likes a pinned workspace stack.
4. Treat every group/topic as a separate active session: it has its own context window and may compress independently. This does not delete the session history, but side agents should return compact handoffs.
5. Parallelize research and inspection; serialize edits to shared files and all integration decisions.

## First message for a side workspace

Give every side agent a bounded role that states:

- its exact scope;
- forbidden actions (especially spending, credentials, model/risk/broker/config/scheduler changes as relevant);
- whether it may edit files;
- a required handoff format: findings, evidence paths, changed files, verification, and untouched scope.

Keep the prompt narrower than the main objective. A side workspace should produce an input to a decision, not independently change the system.

## Telegram bot setup

1. Add the exact Hermes bot account to each target group; bots are members per group and do not inherit membership from another chat.
2. Test with an explicit `@bot_username` mention first.
3. If Telegram shows that the bot has no access to messages, use the official **@BotFather** chat:
   - send `/setprivacy` to BotFather, not to the Hermes bot;
   - select the owned Hermes bot;
   - choose **Disable** only if the user wants the bot to receive ordinary new group messages.
4. Explain the privacy consequence clearly: disabling privacy permits normal **new** messages in groups where the bot is a member; it does not grant access to unrelated chats or old history.
5. If the desired bot is not listed by BotFather, do not attempt ownership or credential changes. Keep privacy mode and use explicit mentions, or ask the bot owner/administrator to change the setting.
6. After changing privacy settings, send a plain test message in the group. If it does not arrive, remove and re-add the bot, then test again.

## Handoff format

Ask side agents to end work with:

```text
Result:
Evidence / report paths:
Files changed:
Verification performed:
Not touched:
Recommendation / open question:
```

Bring the handoff to the main integration chat. Confirm externally visible claims by reading the cited artifacts rather than trusting a summary alone.

## Routing assignments through desktop automation

When the main coordinator posts into Telegram groups through computer-use:

1. Read the side agent's actual reply before approving implementation. An explicit user instruction to "execute if all looks good" is not permission to bypass the group scope, inspect sensitive data, spend money, or change broker/risk/live-execution behavior.
2. Send each assignment as **one single-line message**, then send it with one explicit Return key action. Some native Telegram input paths synthesize embedded newlines as Enter presses, creating multiple partial messages and repeatedly interrupting the recipient agent.
3. After each send, re-capture and verify the target group name, full outgoing text, and delivery state before switching groups.
4. If a short, unexplained message appears in the main chat or a send target is uncertain, treat it as an unverified UI/routing anomaly. Pause further sends and do not attribute it to the user; resume only after the user confirms the intended scope.
5. For a recommendation that depends on unavailable point-in-time data or other unverified prerequisites, advance it first to a read-only feasibility/go-no-go audit rather than starting an implementation.

## Pitfalls

- Do not describe separate Telegram workspaces as saving a shared global model context budget. They create separate session contexts; active concurrent work can still use tokens and system resources.
- Do not assume a side agent shares the main thread's working context. Give it the necessary project paths, constraints, and deliverable.
- Do not let multiple agents edit the same code/data/configuration area concurrently.
- Do not type bot tokens, passwords, payment details, or other secrets into Telegram groups.
