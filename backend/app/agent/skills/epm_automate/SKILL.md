---
name: epm-automate
version: 1.0.0
description: Generate, validate, explain, and safely orchestrate Oracle Cloud EPM Automate commands for Planning, Planning Modules, FreeForm, Strategic Workforce Planning, Sales Planning, Data Integration, Migration, snapshots, files, substitution variables, business rules, and administrative workflows.
tags:
  - oracle-epm
  - epm-automate
  - planning
  - data-integration
  - migration
  - automation
source_of_truth: https://docs.oracle.com/en/cloud/saas/enterprise-performance-management-common/cepma/toc.htm
last_reviewed: 2026-07-17
---

# Oracle EPM Automate Skill

## Purpose

Use this skill whenever a user asks EPM Wizard to:

- create or troubleshoot an EPM Automate command;
- build a Windows, Linux, UNIX, or macOS automation script;
- upload, list, download, copy, rename, or delete files and snapshots;
- run a business rule, ruleset, Data Integration integration, pipeline, or legacy data rule;
- import or export data or metadata;
- refresh, restructure, compact, or clear a cube;
- read or update substitution variables;
- back up, clone, migrate, restore, or administer an Oracle Cloud EPM environment;
- diagnose EPMAT errors, exit codes, authentication failures, paths, Java setup, maintenance-window conflicts, or parameter-order problems.

This is a command-generation and orchestration skill. Oracle documentation remains the source of truth. Never invent a command, parameter, allowed value, role requirement, file location, or service compatibility.

## Default behavior

1. Determine the user's desired outcome, target business process, operating system, and whether they want explanation, a single command, or a complete script.
2. Classify the operation's risk before producing commands.
3. Prefer the newest supported Oracle command when an older command is deprecated.
4. Validate mandatory positional parameters in the documented order.
5. Quote names and values that contain spaces or shell-sensitive characters.
6. Use placeholders for secrets. Never print or request a real password in a command.
7. Show the exact command preview, explain what it changes, list prerequisites, and give a verification command.
8. Never claim a command succeeded unless actual command output or a zero exit status is available.
9. When command syntax is uncertain, direct the runtime to use `epmautomate COMMAND_NAME help` or consult the Oracle source page before generating the final command.

## Risk classification

### Read-only

Examples: `help`, `listFiles`, `listBackups`, `getSubstVar`, `getApplicationAdminMode`, report exports, and status inspection. These may be generated directly.

### Write

Examples: `uploadFile`, `runBusinessRule`, `runRuleSet`, `runIntegration`, `runPipeline`, `importData`, `importMetadata`, `refreshCube`, `setSubstVars`, and file copy operations. Explain the affected application, cube, period, POV, file, integration, or rule. Include a verification step.

### Destructive or environment-wide

Examples: `deleteFile`, `clearCube`, `importSnapshot`, `cloneEnvironment`, `restoreBackup`, `restoreEnvironment`, `recreate`, `resetService`, `runDailyMaintenance`, admin-mode changes, user removal, security imports, and data-replacement operations.

For these operations:

- clearly label the command as destructive or environment-wide;
- require explicit user approval before execution when EPM Wizard has an execution connector;
- identify the target environment URL and environment name;
- recommend a recent snapshot or backup when applicable;
- describe the rollback or recovery path;
- do not hide `Replace`, `REPLACE_DATA`, clear, purge, reset, restore, or overwrite behavior.

## Authentication and secret handling

- Prefer OAuth 2.0 over Basic Authentication when the environment and command support it.
- EPM Automate cannot use normal organization SSO credentials.
- Basic-authentication users configured with MFA cannot use the `login` command in that mode.
- Some identity-management commands, including `addUsers`, `removeUsers`, `assignRole`, and `unassignRole`, require Basic Authentication rather than OAuth refresh-token login.
- Prefer an encrypted `.epw` file or a parameter file. Never embed a real password in generated scripts, logs, UI previews, examples, shell history, or source control.
- Use placeholder values such as `<USERNAME>`, `<PASSWORD_FILE>`, `<EPM_URL>`, and `<OAUTH_EPW_FILE>`.
- Do not display the private encryption key after generating an `encrypt` command.
- Avoid enabling shell tracing around credentials. In shell scripts, use `set +x` before authentication.

### Secure login patterns

Linux, UNIX, or macOS:

```bash
./epmautomate.sh login "<USERNAME>" "<ABSOLUTE_PATH_TO_PASSWORD.epw>" "<EPM_URL>"
```

Windows:

```bat
epmautomate login "<USERNAME>" "C:\secure\password.epw" "<EPM_URL>"
```

Parameter-file pattern:

```bash
./epmautomate.sh login -p login_parameters.txt
```

The `-p FILE_NAME` contents are inserted exactly where `-p` appears. Mandatory values in a parameter file remain positional and must follow the command's documented usage order.

### Encrypt a password or OAuth refresh token

```bash
./epmautomate.sh encrypt "<PASSWORD_OR_REFRESH_TOKEN>" "<PRIVATE_KEY>" "<PASSWORD_FILE.epw>"
```

For OAuth, include the client identifier:

```bash
./epmautomate.sh encrypt "<REFRESH_TOKEN>" "<PRIVATE_KEY>" "<OAUTH_FILE.epw>" ClientID="<CLIENT_ID>"
```

## Platform and installation rules

- Linux, UNIX, and macOS require Java 17 and a valid `JAVA_HOME`.
- The executable is normally `./epmautomate.sh` on Linux, UNIX, and macOS and `epmautomate` from Command Prompt or a batch file on Windows.
- On Linux and macOS, the default local file location is the current directory from which EPM Automate is invoked.
- On Windows, EPM Automate commonly uses `ProgramData\Oracle\EPM Automate` for uploads, downloads, logs, password files, preferences, and parameter files.
- Use absolute paths whenever file location ambiguity is possible.
- To update an installed client, log in and use `epmautomate upgrade`. On Windows, an elevated prompt and write access may be required. Login is required again after upgrading.

## General syntax rules

- Mandatory parameters are positional and must appear in the exact documented sequence.
- Optional named parameters follow mandatory parameters and may usually appear in any order.
- EPM Automate command names and general parameter names are not case-sensitive.
- Command-specific values may be case-sensitive. `runIntegration` explicitly treats parameter names and values as case-sensitive; preserve Oracle's documented capitalization.
- Enclose names and `PARAMETER=VALUE` pairs in double quotes when spaces or special characters are present.
- Never assume that a runtime prompt was accepted. `runBusinessRule` and `runRuleSet` ignore prompt names that do not exactly match those defined in the rule or ruleset.
- When a command is unsupported for the connected service, do not suggest a spelling workaround. Select a supported command or explain the service limitation.

## Daily maintenance and concurrency

- Do not run EPM Automate commands while daily maintenance is active. Oracle may return `EPMAT-11` while the service is unavailable.
- Avoid snapshot operations while the maintenance snapshot is being generated.
- Schedule large clones after maintenance. Source-environment maintenance can terminate an in-progress clone.
- For simultaneous sessions from the same directory, use a unique `EPM_SID` for each process so one session's logout does not interfere with another.
- Do not parallelize commands that operate on the same file, snapshot, cube, integration POV, or environment-wide state unless the workflow is documented as safe.

## File-location model

Know the difference between local and Cloud EPM locations.

### Local

- Windows default: `ProgramData\Oracle\EPM Automate`
- Linux, UNIX, macOS default: current invocation directory

### Cloud EPM

- `inbox`: standard import and Data Integration input location
- `inbox/<directory>`: Data Integration subdirectory
- `outbox`: standard generated/exported output location
- `profitinbox` and `profitoutbox`: Profitability and Cost Management locations
- `to_be_imported`: Narrative Reporting backup import location
- default Migration upload/download location: snapshots and migration artifacts

Use `listFiles` before guessing a remote path.

## Core command reference

### Help and session

```bash
epmautomate help
epmautomate <COMMAND_NAME> help
epmautomate login <USERNAME> <PASSWORD_FILE> <URL>
epmautomate logout
```

A session remains active until logout. Complete scripts should attempt logout even when a middle step fails.

### Files

```bash
epmautomate listFiles
epmautomate uploadFile "<LOCAL_FILE>" [UPLOAD_LOCATION]
epmautomate downloadFile "<REMOTE_PATH_OR_FILE>"
epmautomate deleteFile "<REMOTE_PATH_OR_FILE>"
epmautomate copyFileFromInstance "<SOURCE_FILE>" "<SOURCE_USERNAME>" "<SOURCE_PASSWORD_FILE>" "<SOURCE_URL>" "<TARGET_FILE>"
```

Important: `uploadFile` does not overwrite an identically named remote file. Use a unique name or deliberately delete/rename the existing file first.

### Business rules and rulesets

```bash
epmautomate runBusinessRule "<RULE_NAME>" [RTP_NAME=VALUE ...]
epmautomate runRuleSet "<RULESET_NAME>" [RTP_NAME=VALUE ...]
```

Rules execute against the plan type to which they were deployed. Use exact rule, ruleset, and runtime-prompt names.

### Data Integration

Prefer `runIntegration`; Oracle marks `runDataRule` as deprecated.

```bash
epmautomate runIntegration "<INTEGRATION_NAME>" \
  importMode=Replace exportMode=Merge periodName="{Jan#FY26}" \
  [inputFileName="<FILE_NAME>"] ["<RUNTIME_PARAMETER>=<VALUE>" ...]
```

Required standard-mode values:

- `importMode`: `Append`, `Replace`, `Map and Validate`, `No Import`, or `Direct` where supported;
- `exportMode`: `Merge`, `Replace`, `Accumulate`, `Subtract`, `No Export`, or `Check`, subject to service and integration-mode restrictions;
- `periodName`: a valid single period, period range, Planning member format, substitution-variable format, or `{GLOBAL_POV}`.

Do not use `Replace` casually. Explain which POV dimensions or custom clear region will be cleared before loading. Legacy: `runDataRule "<RULE>" "<START>" "<END>" <IMPORT_MODE> <EXPORT_MODE> [FILE]` only when the environment still depends on Data Management.

### Pipelines

```bash
epmautomate runPipeline "<PIPELINE_CODE>" ["PARAMETER=VALUE" ...]
```

Common parameters: `STARTPERIOD`, `ENDPERIOD`, `IMPORTMODE`, `EXPORTMODE`, `ATTACH_LOGS`, `SEND_MAIL`, `SEND_TO`. Use only variables defined for that pipeline.

### Data / metadata jobs

```bash
epmautomate importData "<IMPORT_JOB>" [FILE_NAME] errorFile="<ERROR_FILE.zip>"
epmautomate exportData "<EXPORT_JOB>" [FILE_NAME.zip]
epmautomate importMetadata "<IMPORT_JOB>" [FILE_NAME.zip] errorFile="<ERROR_FILE.zip>"
epmautomate exportMetadata "<EXPORT_JOB>" [FILE_NAME.zip]
epmautomate refreshCube [DATABASE_REFRESH_JOB]
```

After metadata import, a cube refresh is normally required. Only dimensions configured in the import job are imported; member renames through modified `old_name`/`unique_name` are ignored; review the error ZIP before refreshing if rejected records occurred.

### Cube administration

```bash
epmautomate refreshCube [JOB_NAME]
epmautomate clearCube "<CLEAR_CUBE_JOB>"
```

`clearCube` is destructive. Identify the exact configured job and its clear region before approval. For `compactCube`, `restructureCube`, `mergeDataSlices`, `enableQueryTracking`, `executeAggregationProcess`, `optimizeASOCube`, `essbaseBlockAnalysisReport`, consult the command-specific Oracle page first.

### Substitution variables

```bash
epmautomate getSubstVar ALL
epmautomate getSubstVar "<CUBE_NAME>" name="<VARIABLE_NAME>"
epmautomate setSubstVars ALL "CurYear=FY26" "CurPeriod=Jul"
epmautomate setSubstVars "<CUBE_NAME>" "<VARIABLE>=<VALUE>" ["<VARIABLE>=<VALUE>" ...]
```

Do not use `setSubstVars` for multi-value expressions or functions. Preserve cube-level vs application-level scope.

### Snapshots and backup

```bash
epmautomate listBackups
epmautomate exportSnapshot "<EXISTING_MIGRATION_SNAPSHOT_NAME>"
epmautomate downloadFile "Artifact Snapshot"
epmautomate restoreBackup "<TIMESTAMP/Artifact_Snapshot.zip>" targetName="<TARGET_NAME>"
epmautomate importSnapshot "<SNAPSHOT_NAME>" [importUsers=true|false] [userPassword="<DEFAULT_PASSWORD>"] [resetPassword=true|false]
epmautomate copySnapshotFromInstance "<SNAPSHOT_NAME>" "<SOURCE_USERNAME>" "<SOURCE_PASSWORD_FILE>" "<SOURCE_URL>"
epmautomate renameSnapshot "<CURRENT_NAME>" "<NEW_UNIQUE_NAME>"
```

`importSnapshot` is environment-wide and potentially destructive. Default to application-artifact import only. Do not rename the maintenance snapshot; download it locally and rename the local copy.

### Clone environment

```bash
epmautomate cloneEnvironment "<TARGET_USERNAME>" "<TARGET_PASSWORD_FILE>" "<TARGET_URL>" \
  [SnapshotName="<NAME>"] [environmentBackup="<NAME>"] [UsersAndApplicationRoles=true|false] \
  [DataManagement=true|false] [appAudit=true|false] [jobConsole=true|false] \
  [storedSnapshotsAndFiles=true|false] [DailyMaintenanceStartTime=true|false] [ApplicationProperties=true|false]
```

Connect to the source first; target credential must be encrypted; use either `SnapshotName` or `environmentBackup`, not both; `storedSnapshotsAndFiles=true` clones only top-level inbox/outbox folders; schedule outside the source maintenance window.

### Administration mode & maintenance

```bash
epmautomate getApplicationAdminMode
epmautomate setApplicationAdminMode true|false
epmautomate runDailyMaintenance [skipNext=true|false] [-f]
```

Prefer `setApplicationAdminMode` over deprecated `applicationAdminMode`. `runDailyMaintenance` is environment-wide.

## EPM Wizard response contract

For a command request, render this compact structure:

```markdown
### EPM Automate plan
**Environment:** <name or URL>
**Operation:** <intent>
**Risk:** Read-only | Write | Destructive/environment-wide
**Required role:** <role>

#### Command
`​``shell
<validated command>
`​``

#### What it does
<plain-English explanation>

#### Before running
<prerequisites and assumptions>

#### Verify
`​``shell
<verification command or UI check>
`​``

#### Recovery
<rollback or error-file/log guidance when relevant>
```

For a multi-step workflow, show the commands in execution order and clearly separate local file paths from remote Cloud EPM paths.

## Command selection rules

- Prefer `runIntegration` over deprecated `runDataRule`.
- Prefer `setApplicationAdminMode` over deprecated `applicationAdminMode`.
- Prefer `listFiles` before `downloadFile`, `deleteFile`, or path-sensitive troubleshooting.
- Prefer `listBackups` before `restoreBackup` or `restoreEnvironment`.
- Prefer configured import/export jobs for repeatable data and metadata workflows.
- Use `runPipeline` when the integration process is intentionally a multi-job pipeline.
- Use `cloneEnvironment` only for a true environment clone; use snapshots for selective Migration artifacts.
- Use `getSubstVar` before changing dynamic period variables, and show old and new values.
- Use `refreshCube` after successful metadata changes, not as a generic fix.

## Error interpretation

- Exit code `1`: operation/API failure, insufficient privileges, missing resource, invalid snapshot/file, or server-side job failure.
- Exit code `6`: invalid URL, unavailable service, read/write timeout, network, proxy, or firewall problem.
- Exit code `7`: invalid command/parameter, password-file problem, unauthenticated session, unsupported service command, bad URL, or local execution problem.
- `EPMAT-11`: environment unavailable because daily maintenance is running.
- `EPMAT-7: Invalid or missing parameter`: check positional order, quoting, and multi-line parameter placement.

Do not reduce every failure to "wrong password." Use the exact message and context.

## Non-negotiable safeguards

Never: expose a real password, refresh token, client secret, encryption key, or `.epw` contents; invent an Oracle command or unsupported parameter; silently choose a production environment; silently use a destructive Replace/clear/delete/restore/reset/recreate/purge/snapshot import; claim that upload overwrites an existing file; tell the user a command ran successfully without execution evidence; run commands during daily maintenance; treat local and remote inbox/outbox paths as interchangeable; or use a deprecated command when a documented replacement exists unless maintaining a legacy script is the user's explicit goal.

## References

See `safe_epm_runner.sh` for a secure Linux/macOS automation template. Oracle documentation is the source of truth: https://docs.oracle.com/en/cloud/saas/enterprise-performance-management-common/cepma/toc.htm
