# Hindsight — Full Database Schema

**Probed:** 2026-07-04 on production instance (Docker container, bank=main).
**Database:** PostgreSQL 18 via embedded pg0.

## How to probe the schema yourself

Hindsight runs an embedded pg0 PostgreSQL inside its Docker container.
The default credentials are hardcoded in `/app/api/hindsight_api/pg0.py`:

```python
DEFAULT_USERNAME = "hindsight"
DEFAULT_PASSWORD = "hindsight"
DEFAULT_DATABASE = "hindsight"
```

Probing commands:

```bash
# Find the pg0 installation path
docker exec hindsight sh -c 'find /home/hindsight/.pg0 -name psql -type f'

# Connect and list tables
docker exec hindsight sh -c \
  'PGPASSWORD=hindsight /home/hindsight/.pg0/installation/18.1.0/bin/psql \
   -U hindsight -h 127.0.0.1 -d hindsight -c "\dt"'

# Describe a table
docker exec hindsight sh -c \
  'PGPASSWORD=hindsight /home/hindsight/.pg0/installation/18.1.0/bin/psql \
   -U hindsight -h 127.0.0.1 -d hindsight -c "\d memory_units"'

# Get instance info (port, version, URI)
docker exec hindsight python3 -c 'import pg0; print(pg0.info("hindsight"))'
```

## All 20 Tables

```
 public | alembic_version          | migrations
 public | async_operations         | background job queue
 public | audit_log                | operation audit trail
 public | banks                    | memory bank configs
 public | chunks                   | document chunking for long-form inputs
 public | directives               | bank-level hard rules
 public | documents                | ingested documents (per bank)
 public | entities                 | named entities (canonical)
 public | entity_cooccurrences     | entity pair co-occurrence stats
 public | file_storage             | binary file attachments
 public | graph_maintenance_queue  | graph link recalculation queue
 public | invalidated_memory_units | soft-deleted / invalidated facts
 public | llm_requests             | LLM call logs
 public | memory_links             | typed edges between memory units
 public | memory_units             | THE CORE TABLE — all facts + observations
 public | mental_model_history     | version history of mental models
 public | mental_models            | user-curated summaries
 public | observation_history      | version history of observations
 public | unit_entities             | many-to-many: memory_unit ↔ entity
 public | webhooks                 | webhook subscriptions
```

## Key Table: memory_units (core fact storage)

ALL three fact types (world, experience, observation) live in ONE table
with a `fact_type` discriminator column — NOT separate tables.

```
Column              | Type               | Notes
--------------------|--------------------|--------------------------------------
id                  | uuid               | PK
bank_id             | text               | memory bank
text                | text               | fact text / observation summary
embedding           | vector(384)        | BGE-small embedding, HNSW-indexed
fact_type           | text               | 'world' | 'experience' | 'observation'
context             | text               | surrounding conversation context
event_date          | timestamptz        | when the fact occurred
occurred_start      | timestamptz        | temporal range start
occurred_end        | timestamptz        | temporal range end
mentioned_at        | timestamptz        | when first mentioned
proof_count         | integer            | confirmation count (repeated → higher)
source_memory_ids   | uuid[]             | observation ← source facts (traceability)
observation_scopes  | jsonb              | observation consolidation metadata
consolidated_at     | timestamptz        | when fact was consolidated into observation
consolidation_failed_at | timestamptz    | failed consolidation retry marker
access_count        | integer            | retrieval frequency
tags                | varchar[]          | user-defined tags
search_vector       | tsvector           | BM25 full-text (GIN-indexed)
document_id         | text               | source document
chunk_id            | text               | document chunk
metadata            | jsonb              | extensible metadata
created_at          | timestamptz        | ingestion time
updated_at          | timestamptz        | last modification
edited_at           | timestamptz        | manual edit time
```

**Key indexes:**

| Index | Type | Purpose |
|-------|------|---------|
| `pk_memory_units` | B-tree PK | Primary lookup |
| `idx_memory_units_embedding` | HNSW (vector_cosine_ops) | Semantic search |
| `idx_memory_units_text_search` | GIN (tsvector) | BM25 keyword search |
| `idx_memory_units_bank_date` | B-tree (bank_id, event_date DESC) | Temporal queries |
| `idx_memory_units_bank_fact_type` | B-tree (bank_id, fact_type) | Type-filtered queries |
| `idx_memory_units_source_memory_ids` | GIN (uuid[]) | Observation traceability |
| Per-bank+type HNSW | HNSW (vector_cosine_ops) WHERE | Bank-isolated semantic indexes |

**Fact types (constraint):** `'world'`, `'experience'`, `'observation'`

## Key Table: entities

```
Column           | Type    | Notes
-----------------|---------|--------------------------------------
id               | uuid    | PK
canonical_name   | text    | normalized entity name
bank_id          | text    | per-bank isolation
metadata         | jsonb   | type, aliases, attributes
first_seen       | timestamptz |
last_seen        | timestamptz |
mention_count    | integer | frequency tracking
```

Unique constraint: `(bank_id, lower(canonical_name))`
Trigram index: `GIN (lower(canonical_name) gin_trgm_ops)` for fuzzy name matching

## Key Table: unit_entities (M:N bridge)

```
Column    | Type | Notes
----------|------|--------------------------------------
unit_id   | uuid | FK → memory_units.id
entity_id | uuid | FK → entities.id
```

Composite PK: `(unit_id, entity_id)`. Links a memory unit to all entities it mentions.

## Key Table: memory_links (typed edges between memory units)

```
Column       | Type      | Notes
-------------|-----------|--------------------------------------
from_unit_id | uuid       | source memory unit
to_unit_id   | uuid       | target memory unit
link_type    | text       | relationship type (see below)
entity_id    | uuid       | mediating entity (nullable)
weight       | float8     | 0.0–1.0 confidence
bank_id      | text       | per-bank isolation
created_at   | timestamptz |
```

**7 link types (constraint):**

| Type | Meaning |
|------|---------|
| `temporal` | happened before/after |
| `semantic` | conceptually related |
| `entity` | share an entity |
| `causes` | causal relationship (forward) |
| `caused_by` | causal relationship (reverse) |
| `enables` | dependency/empowerment |
| `prevents` | blocking/disabling |

Unique constraint: `(from_unit_id, to_unit_id, link_type, COALESCE(entity_id, zero-uuid))`

**This is the graph retrieval backbone.** Graph traversal walks:
entities → unit_entities → memory_units → memory_links → related memory_units → unit_entities → other entities

## Key Table: entity_cooccurrences

```
Column             | Type      | Notes
-------------------|-----------|--------------------------------------
entity_id_1        | uuid       | smaller UUID (enforced by CHECK)
entity_id_2        | uuid       | larger UUID
cooccurrence_count | integer    | how often they appear together
last_cooccurred    | timestamptz |
```

CHECK: `entity_id_1 < entity_id_2` (canonical ordering). Used for entity-aware
recall — "find facts about entities that frequently co-occur with X."

## Key Table: observation_history

```
Column         | Type      | Notes
---------------|-----------|--------------------------------------
id             | bigint    | auto-increment PK
observation_id | uuid      | FK → memory_units.id (fact_type='observation')
bank_id        | text      |
content        | jsonb     | full observation snapshot at this version
changed_at     | timestamptz |
```

Version history for observations. Every time an observation is updated
(consolidation adds new evidence), a snapshot is written here.

## Key Table: mental_models

User-curated, high-level summaries for common queries.
Checked FIRST during reflect (highest priority source).

## Actual Data Distribution (2026-07-04, bank=main)

```
fact_type    | count
-------------|-------
world        | 2,349
observation  | 1,878
experience   | 1,588
TOTAL        | 5,815
```

Ratio: world ≈ 40%, observation ≈ 32%, experience ≈ 27%.

## Retrieval Index Architecture

Four retrieval strategies map to four index types, all on the SAME `memory_units` table:

| Strategy | Index | Column |
|----------|-------|--------|
| Semantic | HNSW (vector_cosine_ops) | `embedding` (384-dim) |
| Keyword (BM25) | GIN (tsvector) | `search_vector` |
| Graph | B-tree FKs → memory_links → memory_links indexes | via `unit_entities` + `memory_links` joins |
| Temporal | B-tree composite | `(bank_id, event_date)` / `occurred_start` / `occurred_end` |

Per-bank+type HNSW partial indexes exist for performance isolation
(e.g., `idx_mu_emb_worl_*` for fact_type='world' AND bank_id='main').

## Observation Consolidation Mechanism

1. World/experience facts are created by Iris Extract
2. `consolidated_at IS NULL` marks unconsolidated facts
3. Hindsight periodically groups related facts by entity overlap
4. An LLM call synthesizes an observation: deduplicated, evidence-weighted summary
5. `source_memory_ids` links the observation back to its source facts
6. `proof_count` tracks how many facts support the observation
7. `observation_history` records every version of the observation
8. Failed consolidations get `consolidation_failed_at` timestamp for retry
