# Dictionary hydration and display contract

Dictionary matching returns exact SQLite references; hydration supplies the
content and display fields for those references. Keeping entry identity, the
matched spelling, and the dictionary lemma separate lets a popup explain an
inflected form without losing the source entry.

## Identity and data flow

A headword reference carries `storage_kind`, `db_alias`, and `entry_row_id`.
A form reference also carries `form_row_id`. The
[hydration endpoint](../../language_engine/http/dictionary_index.py) returns
`entry_store` and `ref_to_key`, linking each requested reference to its payload.
`runtime_entry_id` identifies the underlying entry independently of the matched form.

[dict_lookup_sqlite.py](../../dict_lookup_sqlite.py) reads selected records and
their form metadata. `_build_hydrated_display_payload()` in
[serializers.py](../../language_engine/http/serializers.py) constructs the display
contract consumed by the browser:

| Field | Meaning |
|---|---|
| `runtime_entry_id`, `ref_key` | Underlying entry identity and exact match identity |
| `match_kind` | Headword or form match |
| `display_headword`, `lemma_headword` | Visible matched spelling and dictionary lemma |
| `display_reading`, `entry_reading` | Reading for the displayed match and the source entry |
| `morph_info`, `morph_base` | Supplied morphology and its base form |
| `is_alternate_match` | Alternate classification for the triggering form |
| `source`, `senses`, `senses_full`, `forms` | Provenance and lexical content |

Headword matches use the entry's spelling and reading. Form matches use the
triggering form's spelling, romanization, and tags, while retaining the lemma
and entry reading separately. Generated entries can supply morphology from
their commentary and lemma fields. The serializer keeps these source-specific
rules at the hydration boundary.

## Browser ownership

| Stage | Implementation |
|---|---|
| Batch requests and lookup orchestration | [lookup-service.mjs](../../frontend/dictionary/client/lookup-service.mjs) |
| Payload normalization and grouped display rows | [entry-adapters.mjs](../../frontend/dictionary/client/entry-adapters.mjs) |
| Entry-identity deduplication | [hydration.mjs](../../frontend/dictionary/client/hydration.mjs) |
| Main and alternate buckets | [result-merging.mjs](../../frontend/dictionary/client/result-merging.mjs) |
| Fields carried into segment/fill results | [lookup-payloads.mjs](../../frontend/dictionary/client/lookup-payloads.mjs) |
| Popup and panel presentation | [rendering guide](RENDERING_ARCHITECTURE.md) |

Final deduplication groups rows by entry identity. Headword matches take
precedence for the same entry; matching form text can contribute morphology,
while distinct displayed forms retain separate rows. Alternate buckets use
the explicit `is_alternate_match` field from hydration.

The selected reference, SQLite record, serialized payload and rendered row
form a continuous identity chain from lexical match to presentation.
