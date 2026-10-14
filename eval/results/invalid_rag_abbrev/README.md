# Quarantined: first Round-2 start with RAG_ABBREV=1 (2026-10-10, 09:46–09:48Z)

`eval/run_variant.py` defined guardrailed_v2 / guardrailed_v2_q36 with `RAG_ABBREV=1`, but ROUND-2.md item 4 recorded
abbreviation normalisation as a measured negative result and left it OFF. The lead stopped the run after 10/20 held-out
items of guardrailed_v2. These files used the wrong variant definition. They are kept for traceability only: do not cite
or merge them. The variants were corrected (RAG_ABBREV must be unset) and Round 2 was restarted from scratch.

- `heldout_guardrailed_v2.json`: partial, 10/20 items, config.env_flags shows RAG_ABBREV=1
- `run_round2.log`: log of the stopped run
