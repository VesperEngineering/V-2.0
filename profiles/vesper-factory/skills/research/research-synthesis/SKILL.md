---
name: research-synthesis
description: Research multiple related topics in parallel, extract key principles from authoritative sources, and synthesize findings into a structured, actionable document for a specific project.
category: research
triggers:
  - "Research multiple related topics"
  - "Compare best practices / style guides / standards"
  - "Synthesize findings from several sources into one document"
  - "Find and summarize coding standards for a project"
  - "Weekly research scan / paper survey"
notes:
  - "research: This skill is about finding and synthesizing information from multiple external sources. It is NOT for analyzing the current codebase — use codebase-inspection or governed-repo-contribution for that."
  - "This skill pairs well with the `plan` skill: research first, then plan the implementation."
---

# Multi-Source Research Synthesis

A structured workflow for researching multiple related topics in parallel, extracting key principles from authoritative sources, and producing a single, actionable synthesis document.

## Workflow

### Phase 1: Parallel Discovery

Use **one** `web_search` call per subtopic, all in parallel. Aim for 3–5 results per query. For a topic like "coding standards for Python quant projects," you might search:

- Google Python Style Guide  
- PEP 8 and PEP 257  
- Hitchhiker's Guide to Python project structure  
- Clean Architecture / Clean Code for Python  
- Quant/hedge-fund project structure patterns  
- Open-source quant projects (Zipline, PyPortfolioOpt, QuantConnect)

**Rule:** Fire all independent searches in a single response. Do not serialize searches that don't depend on each other.

#### Fallback: When web tools are unavailable

If `web_search` / `web_extract` fail (Firecrawl billing issues, bot blocks, rate limits), fall back to direct API calls:

**arXiv API** (free, no key, ideal for academic/quant research):
```bash
# Search papers by keyword
curl -s "https://export.arxiv.org/api/query?search_query=all:KEYWORD1+AND+all:KEYWORD2&max_results=10&sortBy=relevance"
```

**Field prefixes:** `ti:` (title), `au:` (author), `abs:` (abstract), `all:` (all fields). Combine with `+AND+` (intersection) or `+OR+` (union). No API key.

**Parse Atom XML with Python stdlib (no deps):**
```bash
curl -s "https://export.arxiv.org/api/query?search_query=...&max_results=10" | python -c "
import sys, xml.etree.ElementTree as ET
data = sys.stdin.read()
root = ET.fromstring(data)
ns = {'a': 'http://www.w3.org/2005/Atom'}
for entry in root.findall('a:entry', ns):
    title = entry.find('a:title', ns).text.strip()
    link = entry.find('a:id', ns).text
    summary = entry.find('a:summary', ns).text.strip()
    print(f'TITLE: {title}')
    print(f'LINK: {link}')
    print(f'ABSTRACT: {summary[:500]}')
    print('===')
"
```

**Check which python binary exists first:** `which python && python --version` — the system may have `python` but not `python3`, or vice versa. Adjust the shebang accordingly. On Windows with git-bash, `python3` may not be found (the OS redirects to the Microsoft Store) but `python` works — use `python`, not `python3`.

**arXiv API URL scheme:** The arXiv API at `export.arxiv.org` redirects HTTP → HTTPS (301 Moved Permanently). Always use `https://export.arxiv.org/...` — not `http://`. The `curl -sL` flag (follow redirects) works but adds latency; use HTTPS directly.

**Fetching full abstracts from arXiv paper pages:** When `web_extract` fails (Firecrawl billing, rate limits) and the arXiv API truncates summaries at ~500 chars, fetch the paper's HTML page directly and grep for the `citation_abstract` meta tag:

```bash
curl -sL "https://arxiv.org/abs/2509.16206" | grep -oP '(?<=citation_abstract" content=").*?(?=" />)' | head -1
```

This returns the full abstract without any API key or scraping service. Combine with the arXiv API for bulk metadata + HTML grep for full text.

**Browser as last resort:** when both web tools and direct APIs fail, `browser_navigate` can hit Google Scholar or arxiv search pages. Expect slower results and possible bot detection (CAPTCHA, rate limiting).

**Codebase inspection as research input:** For project-specific research (e.g. "why do only 2/16 factors survive"), examine the actual codebase concurrently with external sources. Read key files — factor infrastructure, evaluation scripts, configuration — so findings can directly reference real code. See the `codebase-inspection` skill for systematic code exploration.

See the `arxiv` skill for full query syntax, category codes, and Semantic Scholar citation data.

### Phase 2: Extract from Top Sources

From the search results, pick the most promising URLs (prefer primary/authoritative sources). Fetch them in parallel with `web_extract`. Use `char_limit=12000` for long pages — you'll get head+tail with the full text saved to cache for paging.

For reference-style or API docs, also try the `site:github.com` search hack to find actual directory/module listings:

```
web_search(query="site:github.com PyPortfolioOpt pypfopt tree main source modules")
```

### Phase 3: Targeted Follow-Up

After reading the top sources, you'll often need specific details the initial extraction missed. Search/fetch for:

- Actual directory tree listings (module names, file organization)
- Code examples or architecture diagrams
- Comparison tables or migration guides

This is where you fill gaps: e.g., if you know PyPortfolioOpt's modules but want its docstring format, search for that specifically.

### Phase 4: Synthesize

#### Open-source bug-candidate research

When the requested synthesis is "find a small, unclaimed bug to fix," treat issue activity, current reproducibility, and source localization as separate evidence streams:

1. List recent open bugs and open PRs in parallel; issue comment count alone does not reveal linked work.
2. Read each shortlisted issue in full and search PR bodies for its issue number. Exclude assigned issues, active human threads, and open PRs.
3. Re-run the minimal reproducer against current trunk or the latest hosted build. Open issues often remain after refactors silently fix the original failure.
4. Read closed PR reviews before selecting a candidate. A closed PR is not active work, but reviewer feedback can identify a tempting symptom-only patch and the correct root-fix direction.
5. Trace the live failure into current source. Report both the root-fix area and the assertion/crash site, explicitly distinguishing them.
6. Locate the narrowest existing regression-test suite and state the expected non-crashing behavior or diagnostic.
7. Briefly list rejected alternatives and why: fixed on trunk, actively claimed, or architecturally broad.

See `references/open-source-bug-candidate-triage.md` for query patterns, live compiler probing, and a concise reporting template.

#### Quant/asset-pricing research scan

When running a periodic (weekly) research scan for a quant project:

1. **Search** each topic via arXiv API or web search, 7-10 topics, all in parallel.
2. **Read abstracts** of the most promising papers (2-3 per topic), extracting: title, arXiv ID, submission date, and the full abstract.
3. **Rate each finding** on three axes:
   - Relevance to our factor model (1-5)
   - Implementation difficulty (1-5)
   - Potential impact (1-5)
4. **Write a structured memo** with: Papers Found, Techniques Worth Exploring, Code/OS Discoveries, Action Items (with priority), and Implementation Notes for the top item.
5. **Create kanban cards** for the top 1-2 research directions (see section below).

Write the output document with these sections (adapt to topic):

1. **Source Summary** — For each source: name, URL, key principles, and how they apply to the target project
2. **Cross-Cutting Themes** — Principles that appear across multiple sources
3. **Violations Found** — Specific issues in the current codebase that need fixing (actionable items)
4. **Recommendations** — Ordered by urgency: Immediate (week 1), Short-term (month 1), Medium-term (quarter 1)
5. **Tool Recommendations** — Specific tools with configuration notes
6. **References** — All URLs for future reading

## Output Format

The output should be a markdown file saved to the project's `data/research_engineering/` directory (or equivalent research folder). Name it descriptively:

```
data/research_engineering/<topic>_research.md
```

For dated/weekly scans (e.g., a cron job that scans new papers), use a date-based filename:

```
data/research_engineering/YYYYMMDD.md
```

The directory must exist before writing — create it with `mkdir -p "data/research_engineering/"` (POSIX) or `mkdir -p /d/path/data/research_engineering/` (Windows git-bash /d/ drive prefix).

The document should:
- Be actionable, not theoretical — each section ends in "what to do"
- Include a summary table per source (Principle | Rule | Application)
- Note specific code smells / violations found in the target project
- Reference specific URLs so the reader can dive deeper

## Extending the output: kanban card creation

For research workflows that produce actionable proposals (e.g., factor research, experiment ideas), consider creating kanban cards for the top 1-2 findings as a second output channel alongside the memo:

1. Check the target board exists: `hermes kanban boards`
2. Create cards with `hermes kanban --board <slug> create "Title" --body '...'`. The title is positional (no `--title` flag). Priority is an integer, not a string.
3. Each card body should include: hypothesis, economic rationale, and a fenced JSON experiment spec block.
4. Kanban card creation is a separate output channel — it does not replace the markdown memo file. Both should be produced.

## Pitfalls

1. **Stop at surface level** — Don't just list search results. Always fetch the actual pages and extract specific rules, not just summaries.
2. **Ignore the target project** — Every finding must answer "and what does this mean for our codebase?" If you can't project the finding onto actual files, you're not done researching.
3. **Serialize independent work** — Batch independent calls. The only serialization should be Phase 2 needing Phase 1's URLs, or Phase 3 needing Phase 2's content.
4. **Cite secondary sources** — Prefer primary sources: PEPs over blog posts about PEPs, Google's own style guide over Medium articles about it. Secondary sources are fine for examples and elaboration but shouldn't be the only thing cited.
5. **All theory, no violations** — If you didn't identify specific problems in the actual codebase, you didn't look hard enough. Search the project for anti-patterns that match the standards you discovered.
6. **Forgetting the research-engineering folder** — Always create the directory if it doesn't exist: `mkdir -p "data/research_engineering/"`
7. **Skipping the evaluation step** — For quant research scans, always rate each paper on Relevance/Implementation Difficulty/Impact. Without this step, the memo is just a list — not an actionable document.
8. **Forgetting the second output channel** — When research produces actionable proposals, create kanban cards alongside the memo. The memo is the archive; the cards are the execution queue.

## Related Skills

- `plan` — Use after research to create an implementation plan
- `codebase-inspection` — Use alongside to analyze codebase metrics
- `governed-repo-contribution` — Use when implementing research findings
- `arxiv` — Specialized arXiv search with query syntax, category codes, and Semantic Scholar integration
- `vesper-kanban-operations` — Kanban card creation, board management, and approval workflows