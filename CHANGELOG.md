# Changelog

All important changes should be tracked here together with the application version from `VERSION`.

## [Unreleased]

### Changed

- (none yet)

### Fixed

- (none yet)

### Planned

- Additional validation coverage for SMTP fields and API URL templates.

## [1.0.7] - 2026-02-27

### Fixed

- Improved settings form responsiveness to prevent fields from overflowing into neighboring cards.
- Adjusted settings grid breakpoints for clearer layout on medium-width screens.

## [1.0.6] - 2026-02-27

### Changed

- Reworked the Settings screen layout to make sections always visible and easier to navigate.
- Split Apilo API configuration from Allegro configuration in separate forms/cards.
- Moved "Kod autoryzacji" directly under "Client Secret" for clearer data entry flow.
- Removed "Developer ID" from UI and setup docs to reduce confusion.

## [1.0.5] - 2026-02-27

### Changed

- Replaced account-specific API endpoint hint with a neutral placeholder (`https://twoje-konto.apilo.com`).
- Added step-by-step Apilo API setup instructions in settings and README (including `.../admin/rest-api/` path).
- Aligned settings copy with Apilo field names shown after app creation (`Adres API`, `Client ID`, `Client Secret`, `Kod autoryzacji`, `Ważność do`).

### Fixed

- Prevented common clean-install misconfiguration by leaving `APILO_*` fields empty in `.env.example` (avoids `.env` overriding panel settings with placeholders).
- Documented configuration precedence (`.env` values override settings stored in panel) to reduce token-fetch failures.

## [1.0.4] - 2026-02-27

### Fixed

- Hardened `apilo.py` error handling with a dedicated `ApiloClientError` exception type.
- Removed raw `response.text` from token/API errors to avoid leaking sensitive API payloads.
- Added network/JSON parsing error handling with consistent, sanitized error messages.
- Added token payload validation before save (prevents writing incomplete/invalid token sets).
- Added token-expiry safety margins and one-time retry after `401` by forcing token refresh.
- Added token refresh lock to reduce race risk during concurrent token refresh attempts.

## [1.0.3] - 2026-02-27

### Fixed

- Restored non-breaking app startup when `FLASK_SECRET_KEY` is missing:
  - use `FLASK_SECRET_KEY` from `.env`/environment if present,
  - otherwise use persisted key from settings (`flask_secret_key`),
  - if missing in both places, generate a strong key once and persist it in settings.

## [1.0.2] - 2026-02-27

### Fixed

- Added a global sync lock for manual pull, background refresh, and manual suggestions refresh to avoid overlapping sync jobs.
- Added SQLite `busy_timeout` and `journal_mode=WAL` in DB connections to reduce `database is locked` issues under concurrent access.
- Replaced `SELECT -> UPDATE/INSERT` product sync with an atomic `INSERT ... ON CONFLICT DO UPDATE` upsert.
- Fixed DB connection leak in `update_allegro_auction_ids()` when auction map is empty.

## [1.0.1] - 2026-02-26

### Fixed

- Removed insecure Flask session secret fallback and now require `FLASK_SECRET_KEY`.
- Blocked open redirect after login by validating `next` redirect targets.
- Fixed order URL building for numeric order IDs in sales suggestions/details.
- Fixed thumbnail TTL logic so expired cached thumbnails are downloaded again.
- Sanitized user-facing error messages in key Flask actions to avoid exposing raw API responses.

## [1.0.0] - 2026-02-26

### Added

- First tracked local baseline in Git (previous file history was not available in this repository).
- Versioning process documentation.
