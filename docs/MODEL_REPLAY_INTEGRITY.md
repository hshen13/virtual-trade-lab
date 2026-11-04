# Saved model-comparison replay integrity

This change hardens the existing synthetic order-sensitivity and repeated-order comparisons. It does not call a model, create new observations, alter saved decisions, fit real consumer data, or execute third-party benchmark code.

## Reproduced failure

Both original replay scripts accepted an empty `freeze.sha256` plus a changed `L_AB.prompt.txt`, and returned the ordinary four/eight rows without an error. The loop checked listed hashes but did not require any particular entries. A partially truncated manifest could similarly omit verification of a protocol or prompt.

## Correction

Both replayers now require exactly the protocol and four known prompt entries, rejecting missing, duplicate, unexpected, malformed, or mismatching entries. They also verify the fixed study identity, complete case IDs, case counts, condition assignments, and prompt mapping. A self-consistently rehashed protocol cannot silently drop or duplicate a run and change the denominator. Non-UTF-8 reply bytes are retained by their digest and counted as invalid, with no invented decision; comparison results that depend on that reply remain unavailable.

The ordinary output schema and all saved decisions remain unchanged. The four-response exploratory study and eight-response repeated study stay separate; their observations are not pooled. Re-running the corrected scripts reproduces both saved `results.json` files byte for byte.

## Tests and limits

Eleven new tests each cover both replayers: empty manifest, missing protocol entry, missing prompt entry, duplicate entry, unexpected path, malformed digest, duplicate case, dropped case, changed prompt mapping, changed condition, and invalid UTF-8 response. The protocol mutations update its listed hash to test structural validation independently of byte-integrity checks.

This is accidental-corruption and schema protection, not authenticated provenance or a security boundary. Someone who can change the code and all evidence can replace the study. The hash file remains a local integrity record, not externally timestamped preregistration. The saved outputs still show disagreement within identical high-price prompts, and do not establish causal order effects, real consumer calibration, or product superiority.

Run `python -m unittest discover -s tests -p 'test_order*.py' -v` for the focused suite, and the normal and optimized full suites in CONTRIBUTING.md for regression coverage.
