# Security Policy

## Supported versions

Security fixes are provided for the latest released minor version.

## Reporting a vulnerability

Use GitHub private vulnerability reporting when available. If private reporting is unavailable, open a public issue requesting a private contact channel without including exploit details, secrets, personal data, local paths, or private Skill content.

Include the affected version, operating system, Python version, reproduction conditions, impact, and any proposed mitigation.

## Execution and data model

The scanner runs locally with the permissions of the calling agent. It reads bounded UTF-8 `SKILL.md` files, parses text, and emits metadata. It is designed not to execute scanned instructions, follow scanned commands, make network requests, or write a persistent index.

Output can include absolute paths and excerpts from local Skill files. Keep inventory output private unless it has been reviewed and redacted for public sharing.
