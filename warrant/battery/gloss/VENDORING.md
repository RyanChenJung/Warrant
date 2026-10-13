# Vendored Gloss detectors

This package is a copy of the seven Gloss detectors and the modules they import, taken from the
public Gloss release. It is the baseline battery (ADR 0002, ADR 0007, issue #28). There is no
runtime dependency on Gloss: nothing in this repo imports a package named `gloss`.

## Source

- Public repository: https://github.com/RyanChenJung/gloss-public (MIT licence)
- Release commit: `b5025fb43bbad0308737a89684ad8f6f92003a07`
- Private original commit named in the release README's Provenance section:
  `16d42780b525c08cc0d21e34301e45457f55763b` (16d4278, that repository's last commit, dated
  2026-08-24; its first commit is dated 2026-08-23). The comparison of the release with the private
  original is recorded by #60 on issue #26.
- Copied from the tracked files of the release commit (`git show <commit>:<path>`), never from a
  working tree.
- DuckDB: pinned to 1.5.5 in `pyproject.toml` and `uv.lock`, the version the release's own
  `uv.lock` pins. The copied tests pass on it under Python 3.13.

The licence notice of the release is `LICENSE` in this directory.

## Files copied

Each file is listed with its git blob id in the release commit's tree. The release files are also
committed byte for byte under `tests/fixtures/gloss_release/` (each with `.txt` appended to its
name), as the reference `tests/test_gloss_vendoring.py` compares against.

| Release path | Copied to | Blob id in the release | Import lines rewritten |
|---|---|---|---|
| `LICENSE` | `warrant/battery/gloss/LICENSE` | `931e7ce2207b0231074121a1c7a897a9bd61a856` | 0 |
| `gloss/__init__.py` | `warrant/battery/gloss/__init__.py` | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` | 0 |
| `gloss/detect/__init__.py` | `warrant/battery/gloss/detect/__init__.py` | `c301f26bfb5161ae8d7970b339409cb02d9db281` | 12 |
| `gloss/detect/field.py` | `warrant/battery/gloss/detect/field.py` | `5bb1f8a2ca84a05c3e4f70e9ee47cf62d020e1e0` | 4 |
| `gloss/detect/grain.py` | `warrant/battery/gloss/detect/grain.py` | `9b5b0023d906f46ec4c4ed193423ae952b88e560` | 3 |
| `gloss/detect/limit.py` | `warrant/battery/gloss/detect/limit.py` | `b9120e9edd9eb927635102e6369fb9b9ce795c14` | 3 |
| `gloss/detect/link.py` | `warrant/battery/gloss/detect/link.py` | `756bcb0d74a7255eb92a5a0fbd87aa745cb27c04` | 4 |
| `gloss/detect/rule.py` | `warrant/battery/gloss/detect/rule.py` | `efd1fa5f70df7ba0fcd8b4fe8811efc3b500e922` | 4 |
| `gloss/detect/scope.py` | `warrant/battery/gloss/detect/scope.py` | `95f1d490249623a08f3eef793c84551bab30c510` | 3 |
| `gloss/detect/value.py` | `warrant/battery/gloss/detect/value.py` | `dbb5a0233f83394b157e473aa3c6e27e9a480dd8` | 3 |
| `gloss/dictionary.py` | `warrant/battery/gloss/dictionary.py` | `5b40cdc5bd3f8dfa8cc20986f3f38cbb3d40a3c0` | 1 |
| `gloss/evidence.py` | `warrant/battery/gloss/evidence.py` | `ba9821b516eae1da689cf6d2ba2204ee2de10335` | 1 |
| `gloss/model.py` | `warrant/battery/gloss/model.py` | `a0a49dea39f1de6ba55b56fc3ac77a5259bbd820` | 0 |
| `gloss/source.py` | `warrant/battery/gloss/source.py` | `2bd6a6dd2655970cd25b1dae8a476c8fa1031694` | 0 |
| `tests/conftest.py` | `tests/battery/conftest.py` | `bec68e7c8b1b4a4bec80328ea5ffd86222ac0a12` | 1 |
| `tests/test_detect_field.py` | `tests/battery/test_detect_field.py` | `62318ba1ba835e093a543960c88355b73e6e0d38` | 5 |
| `tests/test_detect_grain.py` | `tests/battery/test_detect_grain.py` | `2b19d778a7c3c8bd1c9347c3b738253f631957b1` | 4 |
| `tests/test_detect_limit.py` | `tests/battery/test_detect_limit.py` | `db0696b6d751f51533c6d5f81b8fb9e0fb8bdd54` | 5 |
| `tests/test_detect_link.py` | `tests/battery/test_detect_link.py` | `cd2a884b04a414afefcceff7b1d65978f1ecf8a5` | 4 |
| `tests/test_detect_rule.py` | `tests/battery/test_detect_rule.py` | `86dbf2428c9a267d6187eca21cf8b2c818621c61` | 5 |
| `tests/test_detect_rule_identities.py` | `tests/battery/test_detect_rule_identities.py` | `181778f550b5d44115bce289fdffcae305d0e34b` | 4 |
| `tests/test_detect_scope.py` | `tests/battery/test_detect_scope.py` | `6b7e18fd1122520b08c1173d55b3be8aeca7a9c1` | 4 |
| `tests/test_detect_value.py` | `tests/battery/test_detect_value.py` | `fc19f1a1220e14cb0a9eaa2f1831634b68d12292` | 5 |

The supporting modules are exactly the ones the detectors import, directly or through each other:
`model` (finding and assertion records), `evidence` (evidence records), `source` (data access) and
`dictionary` (the dictionary types). The release has eight `tests/test_detect_*.py` files; all eight
are copied, with the whole of `tests/conftest.py`, because the detector tests use all three of its
fixtures.

## Not copied

- `gloss/probe.py` (`OrdinalDirectionProbe`) is not vendored. It is not one of the seven detectors
  and none of them imports it. `run_all` in `detect/__init__.py` imports it inside the function body
  and appends it as an eighth check. `run_all` is left unedited, so it is **not usable** here: calling
  it raises `ModuleNotFoundError`. Callers run the seven detectors directly in `run_all`'s order:
  `GrainDetector` first, then `ctx.grain_filter = derive_grain_filter(ctx)`, then `ScopeDetector`,
  `FieldDetector`, `ValueDetector`, `LinkDetector`, `RuleDetector`, `LimitDetector`.
- Nothing else under `gloss/` or `tests/` in the release is copied.

## Changes made

1. **Import path.** In every `from gloss… import …` statement the module path prefix `gloss` is
   rewritten to `warrant.battery.gloss`: 38 lines in the package and 37 in the tests and their
   `conftest.py`, counted per file in the table above. Nothing else on those lines changes, and no
   other line changes in the vendoring commit. Docstrings and comments are as released.

2. **Declared-foreign-key pairing in the link detector** (`detect/link.py`, in its own commit after
   the vendoring commit and before the first injection; decided on #28). The released detector pairs
   key columns by name only, and 256 of the 257 foreign keys declared in LiveSQLBench-Base-Lite join
   differently named columns, for example `signals.telescref -> telescopes.telescregistry`. The
   detector now also pairs columns on declared foreign keys. This changes which column pairs the
   detector reads; what it checks on each pair is as released. The parts of the module that differ
   from the release are exactly these:
   - `declared_key_pairs` (new function): the column pairs that the declared keys give for one
     table and one peer. The keys are (child table, child column, parent table, parent column)
     tuples. A key is paired from child to parent only, never from the parent back to the child:
     pairing both directions adds fan-out records (#28, from the freeze values on #34).
   - `LinkDetector.__init__` (new method): takes the declared keys as an explicit input,
     `LinkDetector(declared_keys=...)`. The default is no keys, which gives the released behaviour.
     #30 will pass the keys that `warrant.data.release.load_database` returns.
   - `LinkDetector._pairs` (changed method): returns the same-named pairs from `name_matched_pairs`
     as before, followed by the declared pairs that are not already among them.
   - The module docstring gains one paragraph that points here.

   `name_matched_pairs`, `LinkDetector.run`, `LinkDetector._analyse`, `LinkDetector._unmatched`,
   `LinkDetector._reverse_coverage`, the imports and `_MIN_MATCH_RATE` are as released. The parent
   table still has to be among the context's peers, as for a same-named pair.
   Declared names are matched exactly, so the export (#30) must keep the SQLite table and column
   names as declared.
   `tests/test_link_declared_keys.py` covers the change.

`tests/test_gloss_vendoring.py` checks both changes: with docstrings and comments stripped and the
import prefix read back as `gloss`, the syntax tree of every vendored module equals the release's,
except that in `detect/link.py` the three parts named above may differ and every other part must
match.
