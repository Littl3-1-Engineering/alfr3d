# Todo: Export DB Schema Diagram for README + Wiki

## Status: 🔲 Not started

## Goal
Export the current (latest) MySQL schema and generate an up-to-date entity-relationship diagram, then embed it in the repo README and the Notion/wiki docs. The last schema diagram (if any) predates recent migrations (personality/context tables, IoT columns, routines, etc.) and is stale.

## Notes / Approach
- [ ] Export current schema from the running DB (e.g. `mysqldump --no-data` or equivalent) as the source of truth, rather than hand-collating migration files.
- [ ] Generate an ER diagram from the exported schema (tool TBD — e.g. `mysql-workbench`, `dbdiagram.io` import, `schemaspy`, or a quick script into Mermaid `erDiagram` syntax so it renders natively in GitHub/README and Notion).
- [ ] Add the diagram to the README (per this repo's "Keep docs current, every session" rule — screenshots/diagrams should come from this session's own generation, not stale reuse).
- [ ] Add/update the diagram on the shared Notion wiki page per the Documentation Sync Protocol.
- [ ] Note: re-run this whenever a new migration lands significantly changes the schema — consider whether this should become a recurring task rather than one-off.
