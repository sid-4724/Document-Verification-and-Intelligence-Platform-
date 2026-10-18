# Official implementation references

Library versions are resolved in `backend/requirements.lock` and `frontend/package-lock.json`. The lock files, executed tests, and checked-in source are authoritative for this implementation.

- [Next.js installation](https://nextjs.org/docs/app/getting-started/installation) and the installed Next.js package's `dist/docs` guides for App Router, rewrites, proxy body size, and disabling development indicators.
- [SQLAlchemy ORM DML](https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html) for conditional updates and RETURNING; PostgreSQL row locks fence transactional writers.
- [SentenceTransformer constructor](https://sbert.net/docs/package_reference/sentence_transformer/model.html) for local-files-only loading, cache directories, and normalized vectors.
- [Claude Messages API](https://platform.claude.com/docs/en/api/messages) for the optional backend-only HTTP provider. No live key or response was used in validation.
- [Playwright browser channels](https://playwright.dev/docs/browsers#chromium-new-headless-mode) for the full Chromium headless channel used to test PDF viewing.
