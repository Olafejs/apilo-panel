# Changelog

All important changes should be tracked here together with the application version from `VERSION`.

## [Unreleased]

### Changed

- (none yet)

### Fixed

- (none yet)

### Planned

- Additional validation coverage for SMTP fields.

## [1.0.22] - 2026-03-11

### Added

- Added low-stock alert preview and manual alert email sending in Settings.

### Changed

- Sales report can now explicitly switch between all paid orders and paid-plus-realized orders.

### Fixed

- Sales report now uses the real Apilo order-status map to detect `Zrealizowane` instead of always falling back to all paid orders.

## [1.0.21] - 2026-03-10

### Added

- Added dashboard KPI cards for shortages, zero stock, no-sales products, and total inventory value.
- Added business preset filters for shortages, zero stock, missing EAN, missing images, no-sales products, and highest-value items.

### Changed

- Improved the main inventory screen layout to make status, filters, and product context easier to scan.
- Added product badges for yearly sales, stock value, and missing-data warnings.
- Improved the mobile layout so product rows behave like stacked cards on small screens.
- Simplified `README.md` into a shorter operational quick-start.

## [1.0.20] - 2026-03-10

### Added

- Added a `/sync/status` endpoint and live sync status indicators on the main screen.
- Added separate environment controls for inventory sync cadence, sales-cache cadence, yearly sales-cache cadence, and thumbnail download limits.

### Changed

- Split background refresh into separate inventory and sales-cache jobs to avoid recalculating sales suggestions on every product pull.
- Replaced one-shot `requests` calls in the Apilo client with a shared retrying `requests.Session`.
- Stopped the browser from auto-triggering `POST /sync/pull` followed by a full page reload.
- Enabled lazy thumbnail loading in the product list.

### Fixed

- Reduced repeated heavy yearly sales recalculations by refreshing the yearly cache only when it is stale or explicitly requested.
- Limited thumbnail downloads by timeout and maximum size while keeping stale cached images as fallback.

## [1.0.19] - 2026-03-10

### Changed

- Switched the Docker Compose runtime back to `network_mode: host` because the server's default Docker bridge cannot reliably reach external HTTPS endpoints.

### Fixed

- Restored outbound connectivity from the running container to Apilo API after the port-published bridge setup caused connection timeouts.
- Clarified in `README.md` that both build and runtime use host networking on this server.

## [1.0.18] - 2026-03-10

### Changed

- Docker Compose now builds with host networking to avoid package-download failures when the default Docker bridge cannot reach PyPI.
- Docker image builds now use longer pip timeouts and retries for more resilient dependency installation.

### Fixed

- Documented the Docker build-network workaround in `README.md`.

## [1.0.17] - 2026-03-10

### Added

- Added SQLite-backed login attempt tracking for rate limiting.
- Added `APP_SETUP_TOKEN`, `SESSION_LIFETIME_MINUTES`, `SESSION_COOKIE_SECURE`, `LOGIN_RATE_LIMIT_MAX_ATTEMPTS`, and `LOGIN_RATE_LIMIT_WINDOW_SECONDS` environment options.

### Changed

- Hardened Flask session cookie settings and enabled timed sessions.
- Stopped rendering stored API and SMTP secrets back into the settings form.
- Preserved stored API/SMTP secrets when the related password field is left empty.
- Documented safer first-run password setup in `README.md` and `.env.example`.

### Fixed

- Blocked remote first-password setup unless the request comes from localhost or uses a valid setup token.
- Added login rate limiting with logged blocking events after repeated failed attempts.
- Added standard security response headers for browser hardening.
- Stopped trusting `X-Forwarded-For` by default unless explicitly enabled in the environment.

## [1.0.16] - 2026-03-10

### Added

- Added Docker deployment files: `Dockerfile`, `docker-compose.yml`, and `.dockerignore`.

### Changed

- Added configurable app host/port support through `APP_HOST` and `APP_PORT`.
- Documented Docker Compose startup in `README.md`.
- Switched Docker Compose to explicit port publishing on `5080` instead of host network mode.
- Updated `.gitignore` to ignore local `data/` runtime state.
- Enabled explicit app logger propagation for container and service logs.

### Fixed

- Excluded `.env` files from Docker build context to avoid baking local secrets into the image.
- Added failed-login IP logging for easier operational monitoring.

## [1.0.15] - 2026-02-28

### Changed

- Updated `start.sh` to automatically open the default browser at `http://127.0.0.1:5000` after startup when the system supports it.
- Updated `README.md` to mention automatic browser opening in the quick start steps.

## [1.0.14] - 2026-02-28

### Added

- Added `start.sh`, a simple Terminal launcher for macOS and Linux that prepares `.venv`, installs dependencies, creates `.env` if needed, and starts the app.

### Changed

- Simplified `README.md` quick start for macOS and Linux to use `bash start.sh`.
- Removed the unnecessary `xattr` step from the default startup instructions.

## [1.0.13] - 2026-02-28

### Removed

- Removed the macOS launcher system from the repository (`Start-Apilo.command`, `Build-Start-Apilo-App.command`, generated `.app` handling, and `AppIcon.icns`).
- Removed the separate `JAK-URUCHOMIC.md` file.

### Changed

- Moved the simplest startup steps directly into `README.md` under `Szybki start`.
- Simplified `README.md` by removing the deployment, project structure, security, and versioning sections.

## [1.0.12] - 2026-02-28

### Added

- Added `JAK-URUCHOMIC.md` with a very short end-user startup guide for macOS, Windows, and Linux.

### Changed

- Added a prominent link to `JAK-URUCHOMIC.md` near the top of `README.md` so users can find the simplest startup steps immediately.

## [1.0.11] - 2026-02-28

### Added

- Added `Build-Start-Apilo-App.command` to generate a local `Start Apilo.app` launcher on macOS.

### Changed

- Updated README with instructions for creating a local `.app` launcher to avoid Finder blocking the raw `.command` file.
- Added generated macOS app bundles to `.gitignore` so local launchers are not committed by accident.
- The macOS `.app` launcher generator now uses the local `AppIcon.icns` file as the app icon when present.

## [1.0.10] - 2026-02-28

### Added

- Added a clickable macOS launcher script `Start-Apilo.command` that opens Terminal, prepares the virtual environment, installs dependencies when needed, creates `.env` from `.env.example`, starts the app, and opens the browser automatically.

### Changed

- Updated README with a one-click macOS startup section for the new launcher script.
- Clarified in Settings that the price-list ID is an Apilo price list used to fetch Allegro prices during sync, not a value taken directly from Allegro.

## [1.0.9] - 2026-02-27

### Changed

- Removed the `Szablon linku do zamówienia` option from Settings; order links now consistently use the built-in default based on current API base URL.
- Added contextual help for `ID cennika Allegro`, including where the value comes from in Apilo and which endpoint uses it.
- Updated README with a dedicated explanation of Allegro price list ID source and usage.

### Fixed

- Suggestions now use the selected sales window (`30/60/120/180/365`) instead of always dividing by 30 days.
- Suggestions include a yearly-sales fallback when selected-window sales are zero, reducing underestimation for seasonal/intermittent products.
- API settings form is now hidden by default when configuration and tokens are valid; only status indicators are shown (with optional explicit edit mode).

## [1.0.8] - 2026-02-27

### Fixed

- Improved keyboard accessibility by adding clear `:focus-visible` states for links, buttons and form controls.
- Improved product table accessibility with descriptive image alt text and quantity input labels.
- Reduced product thumbnail hover zoom intensity to avoid covering nearby content.
- Prevented automatic refresh from triggering while user is typing in form fields.
- Added ARIA expansion state handling for suggestion details toggles.
- Improved auth form ergonomics with `autocomplete`, `required`, and initial field focus.

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
