# OSS Project Adoption & Trust Evaluation

Use this when the user asks "should I install this GitHub project?" — before running any rig-verification steps, assess whether the project is worth the risk.

## Evaluation Dimensions

### 1. Community Health (GitHub API)

| Metric | Green Flag | Yellow Flag | Red Flag |
|---|---|---|---|
| **Stars** | 500+ | 50–500 | < 50 |
| **Forks** | Meaningful ratio to stars (≥5% forks/stars suggests real use) | Low but non-zero | 0 forks |
| **Age** | 6+ months | 1–6 months | < 1 month |
| **Last commit** | Within 2 weeks | 2–8 weeks ago | > 8 weeks ago / stalled |
| **Age : silence ratio** | Active most of lifetime, short pause | Moderate lifetime, moderate pause | Very young (<3 months) AND silent (>3 weeks) = likely abandoned |
| **Contributors** | Multiple committers + community PRs merged | Single author with community issues | Single author, zero external contributions |
| **Open issues** | Low, or high but actively triaged | Moderate | Many stale, unaddressed |
| **License** | MIT, Apache 2.0, BSD | GPL-family (compatible with use case) | No license / unclear |

### 2. Dependency & Infrastructure Burden

| Factor | Light | Heavy |
|---|---|---|
| **Runtime deps** | Python packages only | Docker + databases + sidecar workers |
| **Setup**| Single command, few steps | Multi-phase install, manual config |
| **Persistence** | SQLite files | Requires running Qdrant/Redis/Postgres etc. |
| **Lock-in** | Compatible with upstream | Forked plugin, "not upstream-compatible" |
| **Uninstall** | `pip uninstall`, delete a folder | Tear down Docker volumes, restore configs |

### 3. Code Quality Signals

- **README quality**: Clear architecture docs, real examples, not just marketing
- **Tests**: Presence of smoke tests, CI badges that are green
- **Semantic versioning**: Tagged releases vs. only main branch
- **Security posture**: Dependency scanning, security reporting policy

### 4. Risk Assessment Heuristics

**High-risk indicators** (any two → strongly recommend against):
- Single developer + project under 3 months old
- Last commit over 4 weeks ago on a project under 2 months
- Requires Docker + persistent infrastructure for basic functionality
- "Heavily forked" plugin that's no longer upstream-compatible
- No license file
- No tagged releases

**When to recommend a trial** (not a dependency):
- Project is promising but young → suggest testing in a throwaway profile/container
- User can verify the claimed benefit with a quick smoke test
- The cost of trying is low (single install command, no persistent infra)

**When to skip entirely** (this session's confirmed signal):
- User explicitly risk-averse about young/unmaintained projects
- Heavy infra overhead for uncertain benefit
- Better/stable alternatives exist (including doing nothing)

## Data Sources

```bash
# Quick metadata
curl -s "https://api.github.com/repos/<owner>/<repo>" | python -c "import sys,json; d=json.load(sys.stdin); print(json.dumps({k:d.get(k) for k in ['name','stargazers_count','forks_count','open_issues_count','language','created_at','pushed_at','license']}, indent=2))"

# Recent commits
curl -s "https://api.github.com/repos/<owner>/<repo>/commits?per_page=5"

# README
curl -sL "https://raw.githubusercontent.com/<owner>/<repo>/main/README.md" | head -200

# Requirements / dependencies
curl -sL "https://raw.githubusercontent.com/<owner>/<repo>/main/requirements.txt" 2>/dev/null
curl -sL "https://raw.githubusercontent.com/<owner>/<repo>/main/setup.py" 2>/dev/null | head -50
```

## Response Format

Deliver as a structured assessment with:
1. **Project snapshot** — stars, age, last commit, license, language
2. **What it does** — one-paragraph summary from the README
3. **The Good** — green flags
4. **The Concerns** — yellow/red flags with specifics
5. **Verdict** — Yes / No / Trial with conditions and reasoning
