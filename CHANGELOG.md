# Changelog

All notable changes to gaik-toolkit are documented here. Versioning follows
[SemVer](https://semver.org/) and is tagged via `git tag vX.Y.Z`
(`setuptools_scm` reads the version from the tag — no manual bumps in
`pyproject.toml`).

## [v0.5.13] - 2026-05-18

### Changed

- **Breaking — `CompositeExtractionRequirements`:** Constructor moved from
  `child_container_name=` + `child_requirements=` kwargs to
  `children: list[ChildRequirements]`. Allows a single parent record with
  multiple distinct repeated child collections. Backwards-compat read-only
  properties preserved (`child_container_name`, `child_requirements` proxy to
  `children[0]`).
- `vision_extractor`: schema generator refactored to iterate through
  `requirements.children` instead of a single child key. Composite requirements
  detected via `parent_with_nested_list` structure type emit one child container
  per `ChildRequirements` entry.
- `extractor.__init__`: re-exports `ChildRequirements` for downstream consumers
  that build `CompositeExtractionRequirements` programmatically.

### Migration

```python
# Before (v0.5.12 and earlier)
CompositeExtractionRequirements(
    parent_requirements=...,
    child_container_name="items",
    child_requirements=ExtractionRequirements(...),
)

# After (v0.5.13+)
CompositeExtractionRequirements(
    parent_requirements=...,
    children=[
        ChildRequirements(
            container_name="items",
            container_description="Purchase order line items",
            requirements=ExtractionRequirements(...),
        ),
    ],
)
```

Reading `result.requirements.child_container_name` or
`result.requirements.child_requirements` still works (returns `children[0]`)
so downstream code that only inspects results is unaffected.

## [v0.5.12] - earlier

See git history for prior tags.
