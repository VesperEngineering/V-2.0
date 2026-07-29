# Knowledge archive

This directory retains adaptive knowledge that is no longer in the active
corpus. Archive Markdown remains part of the repository-local Obsidian vault and
is searchable through derived local state, but it does not consume the active
3,000-line budget.

Operators manually archive a reviewed adaptive note by moving it to the matching
`memory/` or `skills/` subdirectory, setting `vesper_status: archived`, and
keeping `vesper_retention: adaptive`. Archive retrieval is temporary and capped
at two documents within the normal five-document/8,000-character context limits.
It does not reactivate or move a note.

Only an operator may archive, permanently reactivate, or delete a note. There is
no controller command for file movement or deletion.
