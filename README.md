# Minify++ JavaScript Conformance

Independent selected-Test262 evidence for Minify++. The harness pins Test262, records explicit eligibility decisions, batches eligible scripts through Minify++, and executes original and transformed programs under the same Node runtime with the required Test262 harness includes.

```sh
make sync
make smoke
make extract js
make dashboard
```

The initial scope excludes negative syntax tests, modules, agent/host-API tests, and async `$DONE` tests. Those are reported as extraction exclusions rather than silently counted as passes. Runtime outcomes distinguish `pass`, `semantic-failure`, timeouts, source failures, harness-inapplicable cases, and minifier errors. Source failures are not Minify++ failures; they expose a runtime/eligibility mismatch. Confirmed defects belong in Minify++'s permanent regression suite.

This suite complements the product's generated JavaScript matrix: Test262 supplies independent language coverage, while the product suite remains a faster retained regression gate.
