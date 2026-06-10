# DataDex Project — Claude Guidance

## Answering Questions from DataDex

- Always search DataDex **first** before attempting to read or parse source files directly.
- Combine results from all ingested docs into **one unified answer**. Do not attribute or separate by source doc unless the user explicitly asks where something came from.
- When showing **tables, data formats, register layouts, or structured data**, always include the source document name. Attribute each table individually if they come from different docs.
- Use `datadex_list_workspaces` to discover available workspaces before searching.

## Tool Usage

- Use `mcp__datadex__datadex_search` for specific questions.
- Use `mcp__datadex__datadex_summary` for broad topic overviews.
- Use `mcp__datadex__datadex_list_workspaces` to check available workspaces.
