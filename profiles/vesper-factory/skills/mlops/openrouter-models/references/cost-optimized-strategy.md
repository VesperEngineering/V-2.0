# Cost-Optimized Model Usage Strategy for Quant Research Workflows

## Key Distinction: Interactive vs Automated

**Interactive sessions** (conversational, turn-by-turn): use one cheap model and iterate. Benchmark gaps are statistical noise at single-query granularity — don't over-engineer.

**Automated pipelines** (cron jobs, batch processing, unattended runs): use the tiered approach below. At scale, even a 2% accuracy delta saves real money on re-runs.

---

## Interactive Workflow Pattern

**For daily interactive work, stay on one cheap capable model** (e.g. `deepseek/deepseek-v4-flash` at $0.27/M tokens, or `google/gemini-2.5-flash` at $2.80/M).

- **Do not switch models** for different task types mid-session
- **When the agent makes a mistake**, correct it — the correction turn costs pennies
- **Only upgrade** when the agent explicitly says it's stuck and needs a stronger model for a specific reasoning problem
- **Model switching** in the desktop app: use the composer model picker (left of the microphone). Sticky UI state — never writes to the profile default. Switching models scopes to the current chat only.

**Why this works:** At single-query granularity, all modern models (DeepSeek V4 Flash, Gemini 2.5 Flash, Qwen3 Coder, Claude Sonnet) produce roughly equivalent results for the same prompt. The 2–5% benchmark deltas only compound at scale. Over a conversation with corrections and iteration, the final output quality is the same — the cheap model just took 1–2 extra turns.

## Automated Pipeline Pattern (tiered approach)

For unattended batch runs, cron jobs, and high-volume automated pipelines where
manual correction isn't available:

## Current Model Pricing (Effective Rates After Caching)

1. **Qwen3 Coder**: $0.119 input / $1.05 output per 1M tokens
2. **Gemini 2.5 Flash**: $0.195 input / $2.49 output per 1M tokens  
3. **DeepSeek V4 Pro**: $0.164 input / $1.92 output per 1M tokens

## Tiered Approach for Quant Research Workflows

### 1. Primary Model (80% of tasks): Google Gemini 2.5 Flash
- **Why**: Extremely fast (84 tok/s), good for validation tasks, checking receipts, quick analysis
- **Best for**: 
  - Backtest validation checks
  - JSON receipt validation
  - Quick data verification
  - Running simple quant analysis
- **Cost**: ~$0.000154 per typical task (220 input + 380 output tokens)

### 2. Code Generation/Refactoring: Qwen3 Coder
- **Why**: Purpose-built for coding tasks, excellent at repository-level understanding
- **Best for**:
  - Framework migration work
  - Code generation for new modules
  - Complex refactoring tasks
- **Cost**: ~$0.000892 per typical task (300 input + 800 output tokens)

### 3. Complex Research/Analysis: DeepSeek V4 Pro
- **Why**: Strong reasoning capabilities, good for deep quantitative analysis
- **Best for**:
  - Model skill diagnostic analysis
  - Complex remediation planning
  - Research synthesis and recommendations
- **Cost**: ~$0.001384 per typical task (150 input + 650 output tokens)

## Monthly Cost Projection

Assuming 1,000 tasks/day:

- **Gemini Flash (80% of tasks)**: ~$12.32/month
- **Qwen3 Coder (15% of tasks)**: ~$4.01/month  
- **DeepSeek V4 Pro (5% of tasks)**: ~$2.08/month
- **Total**: ~$18.41/month

This is significantly cheaper than using DeepSeek V4 Pro for all tasks ($43.20/month) while maintaining high quality.

## Implementation Recommendation

Use explicit model routing:
- `/model google/gemini-2.5-flash` for validation/checking tasks
- `/model qwen/qwen3-coder` for code generation/refactoring
- `/model deepseek/deepseek-v4-pro` for complex analysis

This approach keeps costs under $20/month while leveraging the strengths of each model appropriately for quant research workflows.