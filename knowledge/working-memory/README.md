# V20 working memory

The controller keeps one small core per agent under this directory:

```text
working-memory/
└── <agent-id>/
    ├── Core Memory.md
    ├── Archive/
    └── History/
```

Each core is capped at 2,000 words. Candidates come from validated controller
receipts or the operator curation command. Lower-value items move to the local
archive; history records the previous and next core so a change can be rolled
back. This directory is not an approved `memory/` or `skills/` root.
