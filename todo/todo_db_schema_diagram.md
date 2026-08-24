# Todo: Export DB Schema Diagram for README + Wiki

## Status: ✅ Done 2026-08-24 (Notion sync complete)

## Goal
Export the current (latest) MySQL schema and generate an up-to-date entity-relationship diagram, then embed it in the repo README and the Notion/wiki docs. The last schema diagram (if any) predates recent migrations (personality/context tables, IoT columns, routines, etc.) and is stale.

## Notes / Approach
- [x] Export current schema from the running DB (`mysqldump --no-data` against the live `alfr3d_db` container) as the source of truth, rather than hand-collating migration files. 21 tables.
- [x] Generate an ER diagram from the exported schema — hand-written into Mermaid `erDiagram` syntax (renders natively in GitHub README and Notion) rather than an external tool, since the schema was small enough to transcribe directly from the mysqldump output with full accuracy.
- [x] Add the diagram to the README, replacing the stale `db_arch.png` (dated April, predated personality/context/IoT tables) — the image file was deleted, superseded by the generated Mermaid block under "Database Architecture".
- [x] Add/update the diagram on the shared Notion wiki page per the Documentation Sync Protocol — Timeline DB row ("DB schema ER diagram for README/wiki", Status: Shipped) and the Present-section prose bullet were already in place from an earlier pass; added 2026-08-24 as a collapsible toggle with the full Mermaid `erDiagram` mirrored 1:1 from the README, nested under "Alfr3d Backend — Current State" on the "Alfr3d: Past, Present and Future" page.
- [x] Noted in the README that this should be re-run whenever a migration significantly changes the schema; not set up as an automated/recurring task.
