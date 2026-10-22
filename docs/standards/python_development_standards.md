# 800.2 - Python Development Standards

| Version         | Date           | Type             | Who             | Comment                                 |
| --------------- | -------------- | ---------------- | --------------- | --------------------------------------- |
| 1.0             | 13 Oct 2026    | Creation         | Shuohui         | First version of development standards  |

## 1. Introduction

This document defines practical development standards for 800.2 project (Professional Software Engineering assessment 2). It applies to application code, tests, configuration, documentation, and code review.

The goals are readable code, clear responsibilities, reproducible environments, reliable behavior, and straightforward maintenance.

- **Must** indicates a required rule.
- **Should** indicates a default practice. Departures must have a clear reason.
- **May** indicates an optional practice.

The team must record the supported Python versions, dependency management workflow, and quality checks in the repository. Exceptions to required rules must be documented and approved during code review.

## 2. Project Structure

Use a structure appropriate to the project's size. The following is a starting point; do not create empty layers or modules solely to match it.

```text
project/
├── README.md
├── web/
├── server/
├── database/
├── .gitignore
└── docs/
```

- Application code should live in a clearly identified package.
- Tests must be separated from production code.
- Program entry points must be explicit. Importing a module must not unexpectedly start the application or modify persistent data.
- Modules should be grouped by feature or responsibility, using one consistent approach.
- Generic utility modules should not become collections of unrelated business logic.

## 3. Naming and Formatting

| Element                       | Convention         | Example                        |
| ----------------------------- | ------------------ | ------------------------------ |
| Module or file                | `snake_case`       | `booking_service.py`           |
| Function, method, or variable | `snake_case`       | `create_booking`, `student_id` |
| Class                         | `PascalCase`       | `BookingService`               |
| Constant                      | `UPPER_SNAKE_CASE` | `MAX_BOOKINGS`                 |
| Internal member               | Leading underscore | `_connection`                  |
| Test module or function       | `test_` prefix     | `test_create_booking`          |

- Use four spaces for indentation and UTF-8 encoding.
- Use an 88-character formatting target. Longer lines may be retained when splitting them would reduce clarity.
- Use `Ruff` formatting consistently; do not manually enforce a conflicting quote style.
- Place imports at the top of the module, grouped as standard library, third-party packages, and project modules.
- Do not use wildcard imports.
- Use descriptive names. Avoid ambiguous names such as `data1` or `temp2` outside trivial local contexts.
- Do not shadow built-ins such as `list`, `dict`, `str`, or `id`.
- Replace unexplained business literals with named constants or configuration values.

## 4. Functions and Type Annotations

- Each function should perform one coherent task.
- Public functions and methods must annotate parameters and return values. Internal functions should also be annotated where useful.
- Type annotations do not replace runtime validation of external input.
- Avoid mutable global state and hidden dependencies.
- Do not use mutable default arguments.
- Prefer early returns to deeply nested control flow.
- Extract repeated logic when its meaning and behavior are genuinely shared.
- Prefer explicit parameters and return values over changes to unrelated shared state.
- Use `Decimal` or integer minor units for monetary calculations, with explicit rounding rules.

## 5. Object-Oriented Design and Responsibilities

- Classes must have clear responsibilities.
- Pass dependencies through constructors or function parameters when this improves testability.
- Prefer composition. Use inheritance when a subtype can reliably substitute for its parent.
- Use functions for simple operations; do not introduce classes without a useful responsibility.
- Keep persistence details out of business rules where practical.
- Use interfaces or protocols when interchangeable implementations are actually needed.
- Avoid speculative abstractions for features the project does not require.

## 6. Exceptions and Logging

- Catch specific exceptions that the code can handle meaningfully.
- Do not use bare `except:` or silently discard errors with `pass`.
- Broad exception handlers are allowed at application boundaries when they log the failure and apply a deliberate recovery or exit policy.
- Preserve exception context when translating errors, using `raise ... from exc`.
- Do not convert infrastructure failures into misleading results such as an empty collection or "not found."
- Error messages should explain the problem without exposing secrets or sensitive internals.
- Use `logging` for operational diagnostics. Use `print()` for intentional command-line output.
- Never log passwords, tokens, or unnecessary personal information.
- Avoid logging the same exception repeatedly at multiple layers. Applications should configure log levels and handlers centrally.

## 7. Databases and Resource Management

- Use parameterized SQL for values. Never concatenate untrusted input into SQL.
- Dynamic table or column names must come from a controlled allowlist; value placeholders do not bind identifiers.
- Define transaction boundaries explicitly and roll back failed operations.
- Keep write transactions short. Do not wait for user input or perform unrelated network requests inside them.
- Close files, database connections, and other resources predictably.
- Use `pathlib.Path` for filesystem paths.
- Keep schema changes in reproducible migration or initialization scripts.
- Do not share database connections across threads unless the driver and application design explicitly support it.

```python
from contextlib import closing
import sqlite3

with closing(sqlite3.connect("app.db")) as connection:
    with connection:
        connection.execute(
            "INSERT INTO students (name) VALUES (?)",
            ("Alex",),
        )
```

For SQLite, the connection context manager controls commit and rollback; it does not close the connection. `closing()` handles closure in this example. A single bound parameter must be a one-element sequence, such as `(student_id,)`.

## 8. Configuration, Dependencies, and Security

- Declare supported Python versions and direct dependencies in `pyproject.toml` or the project's documented equivalent.
- Use an isolated virtual environment for development.
- Choose one dependency management workflow and document exact setup commands.
- Application repositories should commit the dependency manager's lockfile. Libraries should declare appropriate dependency ranges and use a reproducible development environment.
- Keep development, test, and production configuration distinguishable.
- Read secrets from environment variables or a designated secret store.
- `.env.example` must contain only variable names and safe sample values. An `.env` file is not loaded automatically unless the application explicitly supports it.
- Validate external input, including types, lengths, ranges, and authorization where applicable.
- Do not commit credentials, private data, virtual environments, or generated caches.

Recommended `.gitignore` entries:

```gitignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
.env
```

Decide explicitly whether database files belong in version control. Prefer initialization scripts and sanitized fixtures to developer databases.

## 9. Testing

- Use pytest as the default test framework.
- Test core business rules, normal behavior, boundary conditions, and relevant failures.
- Tests must run independently and must not depend on execution order.
- Use temporary or dedicated test databases. Tests must not modify production data.
- Isolate external services when appropriate, and retain integration tests for important real interactions.
- Add a regression test when fixing a defect if it meaningfully verifies the failure scenario.
- Assert observable behavior rather than incidental implementation details.
- Treat coverage as supporting evidence, not proof of correctness.
- Map acceptance criteria to verification steps for delivered features.

## 10. Git and Code Review

- Keep the default branch runnable and releasable according to the project's release policy.
- Develop changes on short-lived branches, such as `feature/user_signup`. `feature/[VERSION]_dev` as a merging branch from all features of a version, `feature/[VERSION]_[USER_STORY]` for feature development, `fix/[VERSION]_[ISSUE_NUMBER]` for bug fix, `test/[VERSION]_[BRANCH_NAME]` for testing, and `hotfix/[VERSION]_[ISSUE_NUMBER]` for fixing issues on a published version.
- All completed feature branch must be firstly mergecd into `feature/[VERSION]_dev` for testing and debuging phases. Once testing is completed, then merge it into `main` to deploy and publish.
- Keep commits focused and describe the change clearly.
- Changes must be reviewed by another contributor before merging, normally the asignee will be the one who responds to the module.
- Do not commit conflict markers, temporary debugging code, or unexplained disabled checks.
- Update documentation when behavior, configuration, or setup changes.

## 11 Git branches management

Reference to [git branches management](./git_branches_management_standards.md)