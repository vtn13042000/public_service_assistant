# Test-set freeze

Frozen by the lead at 2026-10-10T05:11:07Z, after w-graph milestone (b). From this point no prompt, threshold or config may be tuned against these files; proposals for changes go through the lead and are applied only with a new freeze entry.

- `data/testset.jsonl`  71 items  sha256 `8e360e9f4a0834c5…`
- `data/testset_adversarial.jsonl`  7 items  sha256 `238e35635a9d86d5…`
- `data/testset_heldout.jsonl`  20 items  sha256 `f9a1ed51cea308b8…`

Verify: `sha256sum data/testset*.jsonl`. Full hashes:
```
8e360e9f4a0834c5c48b0d73fcf7a479df554580ea872033a3d2e626731de06a  data/testset.jsonl
238e35635a9d86d5215523d4c76e519342ddbe0678f18386dc79ec4d30817376  data/testset_adversarial.jsonl
f9a1ed51cea308b8e489154ff0171c1598eb12c1e9456b3a6e001606cd0323ec  data/testset_heldout.jsonl
```
