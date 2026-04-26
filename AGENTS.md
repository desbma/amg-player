## Lint / Test

- Lint & format: `ruff check`, `ruff format --check`, `uv run ty check`
- Run all tests: `uv run python -m unittest discover -s tests -v`
- Run a single test: `uv run python -m unittest tests.test_tag.TestTag.test_normalize_title_tag`

## Code Style

- Use `pathlib.Path` over `os.path`; use `subprocess` for external commands
- No `_` prefix on any name (methods, functions, variables, attributes) unless it is genuinely unused (e.g. `for _ in range(n)`). All names are plain, even internal helpers.
- Do not use `del` to discard unused function parameters. Instead, prefix the parameter name with `_` in the signature (e.g. `_prompt: str`).
- Docstrings mandatory on all functions (imperative mood).
- Typing:
  - Annotations mandatory on all function signatures. Always write the real type, never a string-quoted annotation.
  - Use `from __future__ import annotations` only when genuinely required for unresolved forward references.
  - Avoid `typing.Any`; use precise types, protocols, or generics instead. `Any` is acceptable only as a last resort when no precise type is feasible, never as a shortcut to skip proper typing.
  - Avoid `typing.cast`; prefer precise annotations, runtime narrowing (`isinstance` / assertions), or API shapes that type-check without casts.
- No verbose comments that paraphrase the code.
- Split large functions into small, single-responsibility ones when needed.
- No inline imports inside functions or methods; all imports must be at module level.
- Favor importing the root module and using fully qualified names in code. Exceptions: names from `typing`, and `pathlib.Path`.
- **IMPORTANT: Never inline raw escape codes, magic strings, thresholds, or unexplained literal values. All such values must be defined as named constants (module-level or class-level). No exceptions.**
- Never use `""` or `0` as sentinel values to mean "absent" or "not set". Use `None` (with `| None` in the type annotation) so the type system distinguishes missing from legitimately empty/zero.
- Group all module-level constants at the top of the file, before class and function definitions.
- Do not add large section-separator comment blocks (e.g. `# ===...` banners). Use class docstrings and natural whitespace to organize code.
- At the end of any refactor, remove dead code (unused constants, types, helpers, and imports) before finishing.
- All logging messages must start with a capital letter.
- Do not pass custom `msg` arguments to `assert*` methods in tests; let the default failure messages speak for themselves.
- Always set `stdin`, `stdout`, and `stderr` explicitly for every `subprocess.run` invocation.
- Always display user-facing paths with the repr format (e.g. `f"{str(path)!r}"`).
