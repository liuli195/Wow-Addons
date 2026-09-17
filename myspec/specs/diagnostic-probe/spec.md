# Diagnostic Probe

## Purpose

Record, on demand and offline, what changed a watched value, when, and from which call path — for silent third-party defects that raise no Lua error.

## Requirements

### Requirement: On-demand probe sessions persist evidence

The system MUST expose `/probe start | mark | stop | status | clear`, collect only inside a session the user explicitly started, and persist each session into SavedVariables together with its write records (before/after snapshots and a call stack) and its marks.

#### Scenario: Session survives a reload

- **WHEN** the user runs `/probe start`, reproduces the defect, runs `/probe mark <note>` and `/probe stop`, then `/reload`
- **THEN** SavedVariables contains that session with write records, the mark, timestamps and stacks, and the session is marked as ended.

#### Scenario: Session survives a reload without stop

- **WHEN** the user runs `/probe start`, reproduces the defect, and reloads or logs out without running `/probe stop`
- **THEN** SavedVariables still contains that session, its records and its self-check, marked as ended.
### Requirement: Coverage self-check is persisted

The system MUST persist, inside each session, whether each declared hook target was actually installed, so coverage can be judged offline without reading the in-game chat.

#### Scenario: A late hook target stays visible in the record

- **WHEN** a declared target never appears during the session because the observed addon's UI module is not loaded yet
- **THEN** the persisted session reports that target as missing instead of reporting an unqualified successful session.
### Requirement: Unreadable values degrade instead of dropping records

When a watched value cannot be read, the system MUST record it as `unavailable` and MUST keep the surrounding record.

#### Scenario: Unreadable field keeps its record

- **WHEN** a watched field holds a value the client refuses to expose
- **THEN** the record is still written, with that field recorded as `unavailable`.
### Requirement: The observed addon keeps its behaviour and files

The system MUST NOT modify the observed addon's files, and MUST NOT change the arguments, return values or side effects of any call it intercepts.

#### Scenario: Observed addon is unchanged

- **WHEN** a probe session has run against an addon
- **THEN** that addon's files on disk are byte-identical to before the session and its intercepted calls still return their original results.
### Requirement: The first-party probes stay independent

The system MUST NOT require another first-party probe addon to be installed, enabled or loaded.

#### Scenario: Only one probe enabled

- **WHEN** only one of the first-party probe addons is enabled
- **THEN** it still installs its own hooks and records its own sessions.
