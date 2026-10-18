# Project instructions

Build a lightweight personal project and website collection tool, with a Chinese interface.

- Python 3.12+ and the standard library are sufficient for runtime and backend tests.
- Keep both the standalone browser version (IndexedDB) and the optional Python server (SQLite) working.
- Run `python3 -m unittest discover -s tests -v` for meaningful storage, metadata or API changes.
- Build public pages with `python3 build_standalone.py --public`. Never publish a build containing personal records.
- Run `python3 build_standalone.py` only when intentionally producing a personal local copy; that generated HTML is ignored by Git.
- Preserve database migrations and v1/v2 JSON backup compatibility. Keep user data, screenshots with personal records, backups and `.env` files out of commits.
- Use parameterized SQL, render user text with DOM text APIs, and keep website-metadata reads on the supported proxy route with TLS verification.
- Keep the enlarged fonts and responsive layout. Validate relevant browser interactions after UI changes.
- Use the existing checkout. Each cloud task is already isolated; do not create a Git worktree unless the user explicitly requests one.
