"""Fixed context and tool budgets for the single local Qwen runtime."""

MAX_CONTEXT_TOKENS = 65_536
MAX_INPUT_TOKENS = 49_152
OUTPUT_RESERVE_TOKENS = 16_384
MAX_TOOL_CALLS = 8


class ContextBudgetExceeded(RuntimeError):
    pass


class ContextBudgetGuard:
    def validate(self, *, prompt_tokens: int, tool_calls: int) -> None:
        if prompt_tokens < 0 or prompt_tokens > MAX_INPUT_TOKENS:
            raise ContextBudgetExceeded(
                f"observed prompt tokens {prompt_tokens} exceed {MAX_INPUT_TOKENS}"
            )
        if tool_calls < 0 or tool_calls > MAX_TOOL_CALLS:
            raise ContextBudgetExceeded(f"tool calls {tool_calls} exceed {MAX_TOOL_CALLS}")
