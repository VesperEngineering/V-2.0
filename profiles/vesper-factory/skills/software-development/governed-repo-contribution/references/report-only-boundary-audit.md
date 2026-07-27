# Report-only capability boundary audit

Use this before reusing a component described as **report-only**, **read-only**, or **safe** in a governed system.

## Required inspection

1. Trace imports and construction paths, not just the public name or CLI help.
2. Identify transitive authority: worker/runtime invocation, provider transport or spend, lease claiming, Kanban/DB writes, scheduler mutation, promotion/deployment/risk hooks, broker/order access, and secrets.
3. If any denied capability is present, do **not** retrofit the component into a stricter packet. Build a separate narrow reader/observer with no import path to the denied capability.
4. Make authority posture literal in every artifact: `report_only=true`, `execution_authority=false`, `safe_for_planning=false`, `planning_safety=unavailable`.
5. Add test-first AST/import or spy tests for forbidden paths, plus tests that missing/malformed evidence displays `UNAVAILABLE` rather than a healthy fallback.
6. Keep evidence flow one-way: completed local receipt → bounded integrity-linked ledger → read-only dashboard projection. Never make the dashboard a control input.

## Release gate

An independent reviewer must verify the complete diff for transitive authority, including runners and CLI arguments. Do not schedule or launch a resident loop merely because its code is complete; activation remains a separate human-authorized scope.
