# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
