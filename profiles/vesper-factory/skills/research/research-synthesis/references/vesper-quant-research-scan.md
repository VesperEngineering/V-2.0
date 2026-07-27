# Vesper Quant Research Scan Workflow

## Overview

Weekly cron job that scans academic papers across 7+ quant finance topics, evaluates applicability to the Vesper factor model, produces a structured research memo, and creates kanban cards for the top findings.

## Search Topics (weekly)

1. "quantitative factor models recent advances"
2. "machine learning asset pricing cross-sectional"
3. "sentiment analysis stock returns transformer"
4. "portfolio optimization entropy hurst features"
5. "news-based trading signals alternative data"
6. site:arxiv.org "factor investing"
7. site:arxiv.org "stock return prediction" deep learning

## Execution Steps

### Step 1: Search for papers

Run all 7 topic searches in parallel. When `web_search` is unavailable (Firecrawl billing, rate limits), use the arXiv API directly:

```bash
curl -sL "https://export.arxiv.org/api/query?search_query=all:%22factor+investing%22+AND+all:%22machine+learning%22&sortBy=submittedDate&sortOrder=descending&max_results=10"
```

Also try the arXiv HTML search page for ids, then use the API to fetch metadata:

```bash
# Get paper IDs from search page
curl -sL "https://arxiv.org/search/?searchtype=all&query=factor+investing+machine+learning&start=0" | grep -oP 'arXiv:\d+\.\d+|href="/abs/\d+\.\d+"'

# Fetch full metadata for specific papers
curl -sL "https://export.arxiv.org/api/query?id_list=2509.16206,2408.02694,2601.17773"
```

### Step 2: Read abstracts and metadata

Parse arXiv API XML with Python stdlib:

```bash
curl -sL "https://export.arxiv.org/api/query?id_list=ID1,ID2,ID3" | python -c "
import sys, xml.etree.ElementTree as ET
data = sys.stdin.read()
root = ET.fromstring(data)
ns = {'a': 'http://www.w3.org/2005/Atom'}
for entry in root.findall('a:entry', ns):
    title = entry.find('a:title', ns).text.strip()
    arxiv_id = entry.find('a:id', ns).text.strip().split('/abs/')[-1]
    summary = entry.find('a:summary', ns).text.strip()[:500]
    print(f'ID: {arxiv_id}')
    print(f'Title: {title}')
    print(f'Abstract: {summary}')
    print('===')
"
```

For full abstracts (the API truncates at ~500 chars), grep the HTML page:

```bash
curl -sL "https://arxiv.org/abs/ID" | grep -oP '(?<=citation_abstract" content=").*?(?=" />)' | head -1
```

### Step 3: Evaluate each paper

Rate each paper on three axes:

| Axis | Scale | Meaning |
|------|-------|---------|
| Relevance | 1-5 | How directly applicable to Vesper's factor model |
| Difficulty | 1-5 | How hard to implement (1 = drop-in, 5 = multi-month research project) |
| Impact | 1-5 | Potential improvement in Sharpe, interpretability, or robustness |

### Step 4: Write the research memo

Output path: `D:\vesper\data\research_engineering\YYYYMMDD.md`

Sections:
- **Research Date:** YYYY-MM-DD
- **Papers Found This Week** — For each: title + link, one-paragraph summary, relevance statement, concrete implementation suggestion
- **Techniques Worth Exploring** — Name, why relevant, how to implement
- **Code / Open Source Discoveries** — GitHub repos, libraries, tools
- **Action Items** — 2-3 concrete items with priority (High/Medium/Low)
- **Implementation Notes** — For the highest-priority item, sketch code changes

### Step 5: Create kanban cards

For the top 1-2 findings, create kanban cards on the vesper board:

```bash
hermes kanban --board vesper create "Research direction: <short name>" \
  --body '**Hypothesis:** ...

**Economic rationale:** ...

```json
{"features": ["mom_12_1", "mom_6_1", "mom_3_1", "rev_1m", "rvol_21", "rvol_63"], "horizon": 21,
 "question": "<the hypothesis as a question>",
 "rationale": "<why it should work>", "budget_seconds": 600}
```'
```

Available features: mom_12_1, mom_6_1, mom_3_1, rev_1m, rvol_21, rvol_63
Available horizons: 5, 21, 63

## Known Pitfalls

- **Firecrawl billing:** When web_search/web_extract fail with "Payment Required", switch to arXiv API + HTML grep immediately. Don't retry the failing tool.
- **python vs python3:** On Windows git-bash, `python3` redirects to the Microsoft Store. Use `python` instead.
- **arXiv API truncation:** The API summary is truncated (~500 chars). Use HTML grep for the full abstract.
- **arxiv.org HTML parsing:** The arxiv.org HTML page structure may change. The `citation_abstract` meta tag and `blockquote.abstract` CSS class are the two stable targets.
- **Kanban create syntax:** Title is positional (not `--title`). Priority is an integer. Body is `--body`. No `--status` flag exists — default status is "ready".