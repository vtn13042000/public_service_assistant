# Invalid RAGAS outputs — do not cite

These are from the first full RAGAS pass (2026-10-10, 06:51–07:22Z). `eval/ragas_run.py` then passed only the top 8 evidence items to
the judge. The guardrailed graph lists 7 procedure-summary DB rows first, so the document rows its answers cite were cut, and
correct answers scored faithfulness 0.0 (T-004/5/6). The baseline was truncated too. The fix is `eval/ragas_run.py:context_sets`:
cited evidence for faithfulness/relevancy, all evidence in graph order for precision/recall, and a 12,000-char budget. The valid
re-run files are `eval/results/ragas_*.json`; their `meta.context_budget_chars` is set. Kept only as a record (R3 §5).
