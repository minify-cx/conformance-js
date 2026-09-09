# Minify++ JavaScript Conformance

Independent selected-Test262 evidence for Minify++. The harness pins Test262, records explicit eligibility decisions, batches eligible scripts through Minify++, and executes original and transformed programs under the same Node runtime with the required Test262 harness includes.

```sh
python3 -m pip install PyYAML
make sync
make smoke
make extract js
make dashboard
```

The full corpus can be split into deterministic resumable shards:

```sh
for i in 0 1 2 3 4 5 6 7; do
  python3 tools/conformance.py run-js --shard-count 8 --shard-index "$i" \
    --results "results/shard-$i.json"
done
python3 tools/conformance.py combine results/shard-{0..7}.json
```

The initial scope excludes negative syntax tests, modules and their `_FIXTURE.js` dependencies, missing-front-matter files, agent-only/HTML-DDA host tests, and exact source-text introspection tests such as `Function.prototype.toString`. Test262 front matter is parsed as YAML rather than approximated with regular expressions. Exclusions are reported rather than silently counted as passes. Async `$DONE`, realms, evaluation, buffer detachment, and garbage-collection hooks are supported by the local Node adapter. Runtime outcomes distinguish `pass`, `semantic-failure`, timeouts, runtime-inapplicable cases, harness errors, and minifier errors. An original program that the selected Node runtime cannot pass is never counted as a Minify++ failure. Confirmed defects belong in Minify++'s permanent regression suite.

This suite complements the product's generated JavaScript matrix: Test262 supplies independent language coverage, while the product suite remains a faster retained regression gate.

## Retained complete checkpoint

At Test262 revision `419d3e0a2273ba01a3bfcbec423f2801425b8e93`, YAML-based
selection produced 48,011 eligible scripts. Of those, 39,741 passed on the
selected Node runtime and all 39,741 also passed after Minify++. The remaining
8,270 originals are retained as classified runtime/harness incompatibilities
and are not credited as Minify++ passes. Extraction separately records negative
tests, modules, fixtures, host-only cases and 83 exact source-text-introspection
tests. The complete run found seven genuine transformations across three
lexical families; all were fixed and reduced into Minify++ product tests.
