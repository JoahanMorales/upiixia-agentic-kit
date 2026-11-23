# Spec · Dashboard onboarding (UI-001, UI-002, UI-003, UI-004)

User guide: [docs/DASHBOARD.md](../../DASHBOARD.md). Evidence for the decision: `kit/.uak/docs/WHY.md`, the setup rows.

## Journey

1. `bash install.sh --wizard [PROJECT] [--no-open]` prints a loopback address and opens it.
2. Welcome → Your project → Your workflow → Review & install → Get ready. Install runs `install.sh` with the chosen
   options; nothing is written before it.
3. "Check what's next" runs `uak start`; the next step shown anywhere (Configuration, Beginner) comes from that result.
4. Plan in the page: IDEA.md, a headless Claude Code or Codex run, cards, "Ask for changes", "Approve and publish".
5. When `uak start` is ready, the exact claim command is offered and Beginner opens project progress.

## Guarantees and the tests that prove them

Test files are in `kit/.uak/tests/`.

| Guarantee | Tests |
|---|---|
| `--wizard` serves before any install choice; the CLI installer stays non-interactive | `test_setup_wizard.py`: `wizard_starts_before_installation`, `legacy_install_remains_noninteractive` |
| No token, wrong Host or Origin, oversized or nested JSON cannot change anything | `invalid_requests_cannot_mutate`, `nested_json_is_rejected` |
| Installer options are literal argv from an allowlist; every stack preset is selectable | `installer_arguments_are_literal`, `all_stack_presets_are_selectable` |
| A second install is refused; a partial one can be repaired; unrelated settings survive | `duplicate_install_is_rejected`, `partial_install_can_recover`, `setup_preserves_unrelated_settings`, `ambiguous_settings_are_not_reported_saved` |
| Installed is not ready; an older installed engine is not ready | `installed_is_not_ready`, `an_older_installed_engine_is_not_ready` |
| Without an installer next to setup the refusal is explicit; setup runs its own Bash (Git Bash) | `installer_absent_package_is_explicit`, `installer_bash_is_preferred`; `test_unified_workspace.py`: `windows_bash_path_from_git_bash_is_accepted` |
| Guidance follows the readiness gate; stale or failed guidance is never shown as current | `guidance_follows_the_readiness_gate`, `ready_line_is_kept_for_the_next_action`, `stale_or_failed_guidance_is_not_shown_as_current`; `test_dashboard_profiles.py`: `next_action_matches_real_state` |
| Only the exact claim command is copyable | `only_the_claim_command_is_copyable`; `copy_command_is_exact` |
| The dashboard needs the session and reads the real plan; no remote is told apart from a failed refresh | `dashboard_requires_session_and_uses_real_plan`, `remote_states_are_distinguished`, `language_and_navigation_are_available`, `navigation_controls_and_isolated_frame_are_declared` |
| Beginner shows one action, persists in the browser, and opens progress when ready; Advanced keeps every detail | `beginner_shows_one_action`, `beginner_profile_persists`, `ready_opens_progress`, `advanced_profile_preserves_details` |
| Configuration re-checks on its own; a long path never overflows at 390 px | `configuration_rechecks_automatically`, `long_project_path_wraps` |
| `Live-URL` is https only, saved atomically, and a malformed value never blocks reads | `live_url_is_https_only`, `live_url_link_is_shown_when_set`, `live_url_is_saved_atomically_and_added_when_missing`, `malformed_live_url_never_blocks_reads` |
| Project content is rendered as text; the static dashboard stays offline | `hostile_content_is_text`, `static_dashboard_remains_offline` |
| IDEA.md is plain text; overwriting needs confirmation | `test_setup_planning.py`: `idea_is_saved_as_plain_text` |
| The planner's command is fixed; it cannot approve, commit, push or edit other files (index flags included) | `planner_command_is_fixed_and_literal`, `planner_never_approves_or_pushes`, `duplicate_planning_is_rejected` |
| Approval needs the typed folder name and the reviewed digest; it commits exactly the four plan files, pushes the verified SHA, and refuses failing lint | `approval_requires_typed_confirmation`, `approval_commits_only_plan_files`, `approval_refuses_failing_lint` |
| The whole journey end to end (UI-003) | `test_dashboard_journey.py`: `new_project_visual_setup_journey`, `interrupted_install_can_recover`, `missing_prerequisites_remain_actionable`; browser evidence in `evidence/` (1280x720 and 390x844, keyboard and reduced motion, `report.json`) |

## Out of scope

The page never registers identities, changes a remote, decides readiness on its own, or changes permissions, mode or
gates from the Beginner/Advanced choice. Gemini CLI and Cursor do not plan headless.
