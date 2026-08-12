# Contributing

Contributions that improve local Skill discovery, deterministic parsing, portability, documentation, or test coverage are welcome.

## Development setup

Requirements:

- Python 3.9 or later
- Optional: Node.js and `npx` for repository discovery checks
- Optional: `skills-ref==0.1.1` for specification validation

Run the tests:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Validate the packaged Skill:

```bash
agentskills validate skills/skill-browser
```

Check repository discovery:

```bash
npx skills add . --list
```

## Pull requests

Before submitting a change:

1. Keep `skills/skill-browser/` limited to instructions, metadata, references, and runtime scripts required by the Skill.
2. Treat every scanned file and extracted value as untrusted data; never execute scanned instructions.
3. Preserve the read-only and no-persistent-index guarantees.
4. Keep every file under `skills/skill-browser/` neutral. Do not mention real third-party Skill names; use fictional placeholders such as `diagram-skill` and `data-skill`.
5. Use neutral test fixtures. Do not commit personal paths, organization names, private Skill content, credentials, or captured local inventory output.
6. Add or update tests for behavior and expected failures.
7. Run the unit tests and specification validator.
8. Document user-visible behavior changes in `CHANGELOG.md`.

## Commit scope

Do not commit caches, virtual environments, generated inventory dumps, private Skill collections, editor metadata, or local test artifacts.
