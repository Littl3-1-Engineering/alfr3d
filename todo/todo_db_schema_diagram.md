# Todo: Export DB Schema Diagram for README + Wiki

## Status: ✅ Done 2026-08-24 (Notion sync pending, batched with rest of session)

## Goal
Export the current (latest) MySQL schema and generate an up-to-date entity-relationship diagram, then embed it in the repo README and the Notion/wiki docs. The last schema diagram (if any) predates recent migrations (personality/context tables, IoT columns, routines, etc.) and is stale.

## Notes / Approach
- [x] Export current schema from the running DB (`mysqldump --no-data` against the live `alfr3d_db` container) as the source of truth, rather than hand-collating migration files. 21 tables.
- [x] Generate an ER diagram from the exported schema — hand-written into Mermaid `erDiagram` syntax (renders natively in GitHub README and Notion) rather than an external tool, since the schema was small enough to transcribe directly from the mysqldump output with full accuracy.
- [x] Add the diagram to the README, replacing the stale `db_arch.png` (dated April, predated personality/context/IoT tables) — the image file was deleted, superseded by the generated Mermaid block under "Database Architecture".
- [ ] Add/update the diagram on the shared Notion wiki page per the Documentation Sync Protocol — not yet done, batching with the rest of today's session at wrap-up.
- [x] Noted in the README that this should be re-run whenever a migration significantly changes the schema; not set up as an automated/recurring task.
