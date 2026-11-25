# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.1.0] - 2026-11-25

### Changed

- **Privacy**: evidence snapshots are now opt-in (off by default). Existing entries keep the choice stored in
  their options; otherwise saving is turned off.
- **Privacy**: snapshots are saved in the private folder `/config/hazard_analysis/evidence` instead of the Media
  folder, which every user can browse. Existing images are not moved.
- Default retention is 15 days instead of 30. **The images already in the Media folder expire with it: those
  older than 15 days are deleted at the first start after the update.**
- The cleanup also runs at startup and when saving is off, and deletes only files created by the integration.

### Added

- Options `evidence_retention_days` (1–365) and `evidence_path` (refused inside a media folder or `www`).

### Fixed

- A snapshot that cannot be written no longer prevents the alert.

## [1.0.0] - 2026-11-15

First public release.

- AI hazard analysis of one to four cameras through any AI Task entity with image support: fire, smoke,
  flood, accident and other hazards scored 0-4, confidence, summary and recommended action, active
  incidents and visible precursors.
- Validation and clamping of the AI response, hard timeout, optional fallback engine.
- Hysteresis: immediate escalation, de-escalation after two consecutive lower readings.
- Dynamic schedule by risk level, occupancy and working hours; extra analysis on occupancy.
- Optional environment sensors as corroborating evidence.
- Persistent notification and optional push notifications on high and critical risk.
- Evidence snapshots in the Media folder, kept 30 days.
- Bundled `hazard-analysis-card` dashboard card, loaded automatically, with a visual editor.
- English and Italian.
