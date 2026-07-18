# Watari CLI contract

Status: D002 design freeze
Issue: D002
Base/dependency SHA: `0d4f062ef8ecd567e977838f90c3330563c7d140`
Schema revision: `cli-contract.v1`

この文書はD001で固定したCLIのmachine-readable contractである。command manifestの各行は
一意のcommand IDを持ち、coverage lockの全commandを1行で表す。`state_class`、`network`、
`auth`、`external_write`は省略しない。unknown command/schema/versionはfail closedする。

## Field rules

| field | allowed values and rule |
| --- | --- |
| `command_id` | `CLI-*`。manifest内で一意 |
| `lock_id` | `LOCK-*`。manifest内で一意。baseline CLI coverage lockとの対応 |
| `alias_of` | canonical commandの`command_id`、または`-`。aliasはtargetと同じcontractを使う |
| `state_class` | `read`、`canonical-write`、`cache-write`。readは状態変更0 |
| `network` | `no`または`yes`。networkがないcommandは`no` |
| `auth` | `no`または`yes`。credential lifecycleを扱うcommandは`yes` |
| `external_write` | `no`または`yes`。D002では全command `no`。future external actionは別ticket |
| `human_output` | `human.v1`または`none` |
| `json_output` | `yes`または`no`。syntaxに`--json`がある行だけ`yes` |
| `json_schema` | `json_output=yes`のcommandだけversioned schema IDを持つ。`json_output=no`は`-` |
| `exit_codes` | stable exit codeを1つ以上、`/`区切りで列挙 |
| `failure` | 下表のfailure tokenを1つ以上、`;`区切りで列挙。silent fallback禁止 |
| `implementation_ticket` | baseline DAGの実装ticket ID |
| `contract_test` | `implementation_ticket`のbaseline issue-DAG変更範囲にあるexact test path。空欄、複数path、ticket mismatchは禁止 |
| `requirement_trace` | D001の要求/受入IDと、必要な後続ticket/test ID |

## Command manifest / coverage lock

| command_id | lock_id | command | alias_of | syntax | state_class | network | auth | external_write | human_output | json_output | json_schema | exit_codes | failure | implementation_ticket | contract_test | requirement_trace |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CLI-001 | LOCK-001 | `watari --help` | `-` | `watari --help` | read | no | no | no | human.v1 | no | - | 0/2 | USAGE | B002 | tests/packaging/test_entrypoint.py | RQ-012,AC-012,B002 |
| CLI-002 | LOCK-002 | `watari --version` | `-` | `watari --version` | read | no | no | no | human.v1 | no | - | 0/2 | USAGE | B002 | tests/packaging/test_entrypoint.py | RQ-012,AC-012,B002 |
| CLI-003 | LOCK-003 | `watari init --state-only` | `-` | `watari init --state-only [--non-interactive]` | canonical-write | no | no | no | human.v1 | no | - | 0/2/11/40/50 | USAGE;INVALID_SCHEMA;INTEGRITY;POLICY | S015 | tests/integration/test_init_state.py | RQ-003,RQ-011,AC-003,AC-011,S015 |
| CLI-004 | LOCK-004 | `watari init --restore` | `-` | `watari init --restore <remote-or-bundle> [--non-interactive]` | canonical-write | yes | yes | no | human.v1 | no | - | 0/2/11/12/20/30/40/50 | USAGE;INVALID_SCHEMA;UNSUPPORTED;AUTH;GIT;INTEGRITY;POLICY | G011 | tests/integration/test_restore_state.py | RQ-003,RQ-010,AC-003,AC-010,G011 |
| CLI-005 | LOCK-005 | `watari init` | `-` | `watari init [--non-interactive]` | canonical-write | yes | yes | no | human.v1 | no | - | 0/2/11/12/20/21/30/40/50 | USAGE;INVALID_SCHEMA;UNSUPPORTED;AUTH;SOURCE;GIT;INTEGRITY;POLICY | R018 | tests/integration/test_setup_wizard.py | RQ-003,AC-003,R018 |
| CLI-006 | LOCK-006 | `watari setup` | `-` | `watari setup [--non-interactive]` | canonical-write | yes | yes | no | human.v1 | no | - | 0/2/10/11/12/20/21/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;AUTH;SOURCE;INTEGRITY;POLICY | R018 | tests/integration/test_setup_wizard.py | RQ-003,AC-003,R018 |
| CLI-007 | LOCK-007 | `watari where` | `-` | `watari where` | read | no | no | no | human.v1 | no | - | 0/2/10 | USAGE;NOT_INIT | S003 | tests/contracts/test_status.py | RQ-012,AC-012,S003 |
| CLI-008 | LOCK-008 | `watari status` | `-` | `watari status [--json]` | read | no | no | no | human.v1 | yes | status.v1 | 0/2/10/11/30/40 | USAGE;NOT_INIT;INVALID_SCHEMA;GIT;INTEGRITY | S003 | tests/contracts/test_status.py | RQ-012,AC-012,S003 |
| CLI-009 | LOCK-009 | `watari doctor` | `-` | `watari doctor [--json]` | read | no | no | no | human.v1 | yes | doctor.v1 | 0/2/10/12 | USAGE;NOT_INIT;UNSUPPORTED | S004 | tests/integration/test_doctor.py | RQ-012,AC-012,S004 |
| CLI-010 | LOCK-010 | `watari doctor --deep` | `-` | `watari doctor --deep [--json]` | read | no | no | no | human.v1 | yes | doctor.v1 | 0/2/10/12 | USAGE;NOT_INIT;UNSUPPORTED | S004 | tests/integration/test_doctor.py | RQ-012,AC-012,S004 |
| CLI-011 | LOCK-011 | `watari verify` | `-` | `watari verify [--strict] [--json]` | read | no | no | no | human.v1 | yes | verify.v1 | 0/2/10/11/40 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY | S016 | tests/contracts/test_verify_rebuild_cli.py | RQ-010,RQ-012,AC-010,S016 |
| CLI-012 | LOCK-012 | `watari` | CLI-013 | `watari` | canonical-write | yes | yes | no | human.v1 | no | - | 0/2/10/11/12/20/21/30/40/50/60 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;AUTH;SOURCE;GIT;INTEGRITY;POLICY;PARTIAL | R019 | tests/integration/test_chat_dispatch.py | RQ-002,RQ-004,AC-002,AC-004,R019 |
| CLI-013 | LOCK-013 | `watari chat` | `-` | `watari chat [--runtime <id>] [--model <id>] [--no-auto-dream]` | canonical-write | yes | yes | no | human.v1 | no | - | 0/2/10/11/12/20/21/30/40/50/60 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;AUTH;SOURCE;GIT;INTEGRITY;POLICY;PARTIAL | R019 | tests/integration/test_chat_dispatch.py | RQ-002,RQ-004,AC-002,AC-004,R019 |
| CLI-014 | LOCK-014 | `watari profile show` | `-` | `watari profile show [--json]` | read | no | no | no | human.v1 | yes | profile.v1 | 0/2/10/11 | USAGE;NOT_INIT;INVALID_SCHEMA | C001 | tests/contracts/test_profile_cli.py | RQ-008,RQ-012,AC-008,AC-012,C001 |
| CLI-015 | LOCK-015 | `watari profile edit` | `-` | `watari profile edit <key> <value>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY;POLICY | C001 | tests/contracts/test_profile_cli.py | RQ-008,AC-008,C001 |
| CLI-016 | LOCK-016 | `watari profile validate` | `-` | `watari profile validate [--json]` | read | no | no | no | human.v1 | yes | profile.v1 | 0/2/10/11 | USAGE;NOT_INIT;INVALID_SCHEMA | C001 | tests/contracts/test_profile_cli.py | RQ-008,AC-008,C001 |
| CLI-017 | LOCK-017 | `watari profile history` | `-` | `watari profile history [--json]` | read | no | no | no | human.v1 | yes | profile.v1 | 0/2/10/11 | USAGE;NOT_INIT;INVALID_SCHEMA | C001 | tests/contracts/test_profile_cli.py | RQ-008,RQ-012,AC-008,C001 |
| CLI-018 | LOCK-018 | `watari context build` | `-` | `watari context build [--runtime <id>] [--json]` | read | no | no | no | human.v1 | yes | context.v1 | 0/2/10/11/12/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;POLICY | C007 | tests/contracts/test_context_memory_read_cli.py | RQ-009,RQ-012,AC-009,AC-012,C007 |
| CLI-019 | LOCK-019 | `watari context explain` | `-` | `watari context explain [--runtime <id>] [--json]` | read | no | no | no | human.v1 | yes | context.v1 | 0/2/10/11/12/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;POLICY | C007 | tests/contracts/test_context_memory_read_cli.py | RQ-009,RQ-012,AC-009,AC-012,C007 |
| CLI-020 | LOCK-020 | `watari memory list` | `-` | `watari memory list [--json]` | read | no | no | no | human.v1 | yes | memory.v1 | 0/2/10/11/40 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY | C007 | tests/contracts/test_context_memory_read_cli.py | RQ-012,AC-012,C007 |
| CLI-021 | LOCK-021 | `watari memory search` | `-` | `watari memory search <query> [--json]` | read | no | no | no | human.v1 | yes | memory.v1 | 0/2/10/11 | USAGE;NOT_INIT;INVALID_SCHEMA | C007 | tests/contracts/test_context_memory_read_cli.py | RQ-009,RQ-012,AC-009,C007 |
| CLI-022 | LOCK-022 | `watari memory show` | `-` | `watari memory show <id> [--json]` | read | no | no | no | human.v1 | yes | memory.v1 | 0/2/10/11/40 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY | C007 | tests/contracts/test_context_memory_read_cli.py | RQ-012,AC-012,C007 |
| CLI-023 | LOCK-023 | `watari memory explain` | `-` | `watari memory explain <id> [--json]` | read | no | no | no | human.v1 | yes | memory.v1 | 0/2/10/11/40 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY | C007 | tests/contracts/test_context_memory_read_cli.py | RQ-012,AC-012,C007 |
| CLI-024 | LOCK-024 | `watari memory correct` | `-` | `watari memory correct <id> <value>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY;POLICY | C008 | tests/contracts/test_memory_write_cli.py | RQ-013,AC-013,C006,C008 |
| CLI-025 | LOCK-025 | `watari memory forget` | `-` | `watari memory forget <id>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY;POLICY | C008 | tests/contracts/test_memory_write_cli.py | RQ-013,AC-013,C006,C008 |
| CLI-026 | LOCK-026 | `watari memory restore` | `-` | `watari memory restore <id>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY;POLICY | C008 | tests/contracts/test_memory_write_cli.py | RQ-013,AC-013,C006,C008 |
| CLI-027 | LOCK-027 | `watari memory rebuild` | `-` | `watari memory rebuild [--json]` | cache-write | no | no | no | human.v1 | yes | memory.v1 | 0/2/10/11/40 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY | S016 | tests/contracts/test_verify_rebuild_cli.py | RQ-010,RQ-012,AC-010,S016 |
| CLI-028 | LOCK-028 | `watari memory verify` | `-` | `watari memory verify [--json]` | read | no | no | no | human.v1 | yes | verify.v1 | 0/2/10/11/40 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY | S016 | tests/contracts/test_verify_rebuild_cli.py | RQ-010,RQ-012,AC-010,S016 |
| CLI-029 | LOCK-029 | `watari remember` | `-` | `watari remember <text>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY;POLICY | C008 | tests/contracts/test_memory_write_cli.py | RQ-013,AC-013,C006,C008 |
| CLI-030 | LOCK-030 | `watari memory candidates list` | `-` | `watari memory candidates list [--json]` | read | no | no | no | human.v1 | yes | candidate.v1 | 0/2/10/11 | USAGE;NOT_INIT;INVALID_SCHEMA | C008 | tests/contracts/test_memory_write_cli.py | RQ-013,AC-013,C006,C008 |
| CLI-031 | LOCK-031 | `watari memory candidates show` | `-` | `watari memory candidates show <id> [--json]` | read | no | no | no | human.v1 | yes | candidate.v1 | 0/2/10/11 | USAGE;NOT_INIT;INVALID_SCHEMA | C008 | tests/contracts/test_memory_write_cli.py | RQ-013,AC-013,C006,C008 |
| CLI-032 | LOCK-032 | `watari memory candidates accept` | `-` | `watari memory candidates accept <id>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY;POLICY | C008 | tests/contracts/test_memory_write_cli.py | RQ-013,AC-013,C006,C008 |
| CLI-033 | LOCK-033 | `watari memory candidates reject` | `-` | `watari memory candidates reject <id>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY;POLICY | C008 | tests/contracts/test_memory_write_cli.py | RQ-013,AC-013,C006,C008 |
| CLI-034 | LOCK-034 | `watari source list` | `-` | `watari source list [--json]` | read | no | no | no | human.v1 | yes | source.v1 | 0/2/10/11 | USAGE;NOT_INIT;INVALID_SCHEMA | A010 | tests/contracts/test_source_cli.py | RQ-005,RQ-012,AC-005,AC-012,A010 |
| CLI-035 | LOCK-035 | `watari source add` | `-` | `watari source add <id>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/12/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;INTEGRITY;POLICY | A010 | tests/contracts/test_source_cli.py | RQ-005,AC-005,A010 |
| CLI-036 | LOCK-036 | `watari source inspect` | `-` | `watari source inspect <id> [--json]` | read | no | no | no | human.v1 | yes | source.v1 | 0/2/10/11/21 | USAGE;NOT_INIT;INVALID_SCHEMA;SOURCE | A010 | tests/contracts/test_source_cli.py | RQ-005,RQ-012,AC-005,A010 |
| CLI-037 | LOCK-037 | `watari source test` | `-` | `watari source test <id>` | read | yes | yes | no | human.v1 | no | - | 0/2/10/12/20/21 | USAGE;NOT_INIT;UNSUPPORTED;AUTH;SOURCE | A010 | tests/contracts/test_source_cli.py | RQ-005,AC-005,A010 |
| CLI-038 | LOCK-038 | `watari source disable` | `-` | `watari source disable <id>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY;POLICY | A010 | tests/contracts/test_source_cli.py | RQ-005,AC-005,A010 |
| CLI-039 | LOCK-039 | `watari source remove` | `-` | `watari source remove <id>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY;POLICY | A010 | tests/contracts/test_source_cli.py | RQ-005,AC-005,A010 |
| CLI-040 | LOCK-040 | `watari runtime list` | `-` | `watari runtime list [--json]` | read | no | no | no | human.v1 | yes | runtime.v1 | 0/2/10/11 | USAGE;NOT_INIT;INVALID_SCHEMA | R017 | tests/contracts/test_runtime_model_cli.py | RQ-009,RQ-012,AC-009,R017 |
| CLI-041 | LOCK-041 | `watari runtime add` | `-` | `watari runtime add <id>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/12/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;INTEGRITY;POLICY | R017 | tests/contracts/test_runtime_model_cli.py | RQ-009,AC-009,R017 |
| CLI-042 | LOCK-042 | `watari runtime set-default` | `-` | `watari runtime set-default <id>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/12/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;INTEGRITY;POLICY | R017 | tests/contracts/test_runtime_model_cli.py | RQ-009,AC-009,R017 |
| CLI-043 | LOCK-043 | `watari runtime test` | `-` | `watari runtime test <id>` | read | no | no | no | human.v1 | no | - | 0/2/10/11/12 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED | R017 | tests/contracts/test_runtime_model_cli.py | RQ-009,AC-009,R017 |
| CLI-044 | LOCK-044 | `watari runtime disable` | `-` | `watari runtime disable <id>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/12/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;INTEGRITY;POLICY | R017 | tests/contracts/test_runtime_model_cli.py | RQ-009,AC-009,R017 |
| CLI-045 | LOCK-045 | `watari runtime remove` | `-` | `watari runtime remove <id>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY;POLICY | R017 | tests/contracts/test_runtime_model_cli.py | RQ-009,AC-009,R017 |
| CLI-046 | LOCK-046 | `watari model list` | `-` | `watari model list [--json]` | read | no | no | no | human.v1 | yes | model.v1 | 0/2/10/11 | USAGE;NOT_INIT;INVALID_SCHEMA | R017 | tests/contracts/test_runtime_model_cli.py | RQ-003,RQ-009,AC-003,AC-009,R017 |
| CLI-047 | LOCK-047 | `watari model add` | `-` | `watari model add <id>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/12/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;INTEGRITY;POLICY | R017 | tests/contracts/test_runtime_model_cli.py | RQ-003,RQ-009,AC-003,AC-009,R017 |
| CLI-048 | LOCK-048 | `watari model set-default` | `-` | `watari model set-default <id>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/12/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;INTEGRITY;POLICY | R017 | tests/contracts/test_runtime_model_cli.py | RQ-003,RQ-009,AC-003,AC-009,R017 |
| CLI-049 | LOCK-049 | `watari model test` | `-` | `watari model test <id>` | read | yes | yes | no | human.v1 | no | - | 0/2/10/12/20 | USAGE;NOT_INIT;UNSUPPORTED;AUTH | R017 | tests/contracts/test_runtime_model_cli.py | RQ-003,RQ-009,AC-003,AC-009,R017 |
| CLI-050 | LOCK-050 | `watari model disable` | `-` | `watari model disable <id>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/12/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;INTEGRITY;POLICY | R017 | tests/contracts/test_runtime_model_cli.py | RQ-003,RQ-009,AC-003,AC-009,R017 |
| CLI-051 | LOCK-051 | `watari model remove` | `-` | `watari model remove <id>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY;POLICY | R017 | tests/contracts/test_runtime_model_cli.py | RQ-003,RQ-009,AC-003,AC-009,R017 |
| CLI-052 | LOCK-052 | `watari auth list` | `-` | `watari auth list [--json]` | read | no | yes | no | human.v1 | yes | auth.v1 | 0/2/10/11 | USAGE;NOT_INIT;INVALID_SCHEMA | K005 | tests/contracts/test_auth_cli.py | RQ-003,RQ-012,AC-003,AC-012,K005 |
| CLI-053 | LOCK-053 | `watari auth login` | `-` | `watari auth login <provider>` | canonical-write | yes | yes | no | human.v1 | no | - | 0/2/10/11/12/20/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;AUTH;INTEGRITY;POLICY | K005 | tests/contracts/test_auth_cli.py | RQ-003,AC-003,K005 |
| CLI-054 | LOCK-054 | `watari auth status` | `-` | `watari auth status <provider> [--json]` | read | no | yes | no | human.v1 | yes | auth.v1 | 0/2/10/12/20 | USAGE;NOT_INIT;UNSUPPORTED;AUTH | K005 | tests/contracts/test_auth_cli.py | RQ-003,RQ-012,AC-003,K005 |
| CLI-055 | LOCK-055 | `watari auth refresh` | `-` | `watari auth refresh <provider>` | canonical-write | yes | yes | no | human.v1 | no | - | 0/2/10/11/12/20/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;AUTH;INTEGRITY;POLICY | K005 | tests/contracts/test_auth_cli.py | RQ-003,AC-003,K005 |
| CLI-056 | LOCK-056 | `watari auth logout` | `-` | `watari auth logout <provider>` | canonical-write | no | yes | no | human.v1 | no | - | 0/2/10/11/12/20/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;AUTH;INTEGRITY;POLICY | K005 | tests/contracts/test_auth_cli.py | RQ-003,AC-003,K005 |
| CLI-057 | LOCK-057 | `watari auth revoke` | `-` | `watari auth revoke <provider>` | canonical-write | yes | yes | no | human.v1 | no | - | 0/2/10/11/12/20/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;AUTH;INTEGRITY;POLICY | K005 | tests/contracts/test_auth_cli.py | RQ-003,AC-003,K005 |
| CLI-058 | LOCK-058 | `watari project list` | `-` | `watari project list [--json]` | read | no | no | no | human.v1 | yes | project.v1 | 0/2/10/11 | USAGE;NOT_INIT;INVALID_SCHEMA | C009 | tests/contracts/test_project_cli.py | RQ-009,RQ-012,AC-009,C009 |
| CLI-059 | LOCK-059 | `watari project trust` | `-` | `watari project trust <root>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY;POLICY | C009 | tests/contracts/test_project_cli.py | RQ-009,AC-009,C009 |
| CLI-060 | LOCK-060 | `watari project inspect` | `-` | `watari project inspect <root> [--json]` | read | no | no | no | human.v1 | yes | project.v1 | 0/2/10/11/50 | USAGE;NOT_INIT;INVALID_SCHEMA;POLICY | C009 | tests/contracts/test_project_cli.py | RQ-009,RQ-012,AC-009,C009 |
| CLI-061 | LOCK-061 | `watari project revoke` | `-` | `watari project revoke <root>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;INTEGRITY;POLICY | C009 | tests/contracts/test_project_cli.py | RQ-009,AC-009,C009 |
| CLI-062 | LOCK-062 | `watari dream` | `-` | `watari dream [--source <id>] [--since <timestamp>]` | canonical-write | yes | yes | no | human.v1 | no | - | 0/2/10/11/12/20/21/30/40/50/60 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;AUTH;SOURCE;GIT;INTEGRITY;POLICY;PARTIAL | M004 | tests/contracts/test_dream_cli.py | RQ-004,RQ-006,AC-004,AC-006,M004 |
| CLI-063 | LOCK-063 | `watari dream --dry-run` | `-` | `watari dream --dry-run [--source <id>] [--since <timestamp>]` | read | yes | yes | no | human.v1 | no | - | 0/2/10/12/20/21/50/60 | USAGE;NOT_INIT;UNSUPPORTED;AUTH;SOURCE;POLICY;PARTIAL;DRY_RUN | M004 | tests/contracts/test_dream_cli.py | RQ-006,AC-006,M004 |
| CLI-064 | LOCK-064 | `watari dream history` | `-` | `watari dream history [--json]` | read | no | no | no | human.v1 | yes | dream.v1 | 0/2/10/11 | USAGE;NOT_INIT;INVALID_SCHEMA | M004 | tests/contracts/test_dream_cli.py | RQ-006,RQ-012,AC-006,AC-012,M004 |
| CLI-065 | LOCK-065 | `watari dream show` | `-` | `watari dream show <id> [--json]` | read | no | no | no | human.v1 | yes | dream.v1 | 0/2/10/11 | USAGE;NOT_INIT;INVALID_SCHEMA | M004 | tests/contracts/test_dream_cli.py | RQ-006,RQ-012,AC-006,AC-012,M004 |
| CLI-066 | LOCK-066 | `watari sync status` | `-` | `watari sync status [--json]` | read | no | no | no | human.v1 | yes | sync.v1 | 0/2/10/11/30 | USAGE;NOT_INIT;INVALID_SCHEMA;GIT | G010 | tests/contracts/test_sync_device_backup_cli.py | RQ-014,RQ-012,AC-014,AC-012,G010 |
| CLI-067 | LOCK-067 | `watari sync pull` | `-` | `watari sync pull` | canonical-write | yes | yes | no | human.v1 | no | - | 0/2/10/11/12/20/30/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;AUTH;GIT;INTEGRITY;POLICY | G010 | tests/contracts/test_sync_device_backup_cli.py | RQ-014,AC-014,G006,G007,G010 |
| CLI-068 | LOCK-068 | `watari sync push` | `-` | `watari sync push` | canonical-write | yes | yes | no | human.v1 | no | - | 0/2/10/11/12/20/30/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;AUTH;GIT;INTEGRITY;POLICY | G010 | tests/contracts/test_sync_device_backup_cli.py | RQ-014,AC-014,G006,G007,G010 |
| CLI-069 | LOCK-069 | `watari conflict list` | `-` | `watari conflict list [--json]` | read | no | no | no | human.v1 | yes | conflict.v1 | 0/2/10/11/30 | USAGE;NOT_INIT;INVALID_SCHEMA;GIT | G010 | tests/contracts/test_sync_device_backup_cli.py | RQ-014,RQ-012,AC-014,G010 |
| CLI-070 | LOCK-070 | `watari conflict show` | `-` | `watari conflict show <id> [--json]` | read | no | no | no | human.v1 | yes | conflict.v1 | 0/2/10/11/30 | USAGE;NOT_INIT;INVALID_SCHEMA;GIT | G010 | tests/contracts/test_sync_device_backup_cli.py | RQ-014,RQ-012,AC-014,G010 |
| CLI-071 | LOCK-071 | `watari conflict resolve` | `-` | `watari conflict resolve <id> <decision>` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/30/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;GIT;INTEGRITY;POLICY | G010 | tests/contracts/test_sync_device_backup_cli.py | RQ-014,AC-014,G008,G010 |
| CLI-072 | LOCK-072 | `watari device list` | `-` | `watari device list [--json]` | read | no | no | no | human.v1 | yes | device.v1 | 0/2/10/11/30 | USAGE;NOT_INIT;INVALID_SCHEMA;GIT | G010 | tests/contracts/test_sync_device_backup_cli.py | RQ-014,RQ-012,AC-014,G010 |
| CLI-073 | LOCK-073 | `watari device register` | `-` | `watari device register <id>` | canonical-write | no | yes | no | human.v1 | no | - | 0/2/10/11/20/30/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;AUTH;GIT;INTEGRITY;POLICY | G010 | tests/contracts/test_sync_device_backup_cli.py | RQ-014,AC-014,G008,G010 |
| CLI-074 | LOCK-074 | `watari device trust` | `-` | `watari device trust <id>` | canonical-write | no | yes | no | human.v1 | no | - | 0/2/10/11/20/30/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;AUTH;GIT;INTEGRITY;POLICY | G010 | tests/contracts/test_sync_device_backup_cli.py | RQ-014,AC-014,G008,G010 |
| CLI-075 | LOCK-075 | `watari device revoke` | `-` | `watari device revoke <id>` | canonical-write | no | yes | no | human.v1 | no | - | 0/2/10/11/20/30/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;AUTH;GIT;INTEGRITY;POLICY | G010 | tests/contracts/test_sync_device_backup_cli.py | RQ-014,AC-014,G008,G010 |
| CLI-076 | LOCK-076 | `watari device set-coordinator` | `-` | `watari device set-coordinator <id>` | canonical-write | no | yes | no | human.v1 | no | - | 0/2/10/11/20/30/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;AUTH;GIT;INTEGRITY;POLICY | G010 | tests/contracts/test_sync_device_backup_cli.py | RQ-014,AC-014,G008,G010 |
| CLI-077 | LOCK-077 | `watari backup create` | `-` | `watari backup create <target>` | canonical-write | yes | yes | no | human.v1 | no | - | 0/2/10/11/12/20/30/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;AUTH;GIT;INTEGRITY;POLICY | G010 | tests/contracts/test_sync_device_backup_cli.py | RQ-010,RQ-014,AC-010,AC-014,G009,G010 |
| CLI-078 | LOCK-078 | `watari backup verify` | `-` | `watari backup verify <target>` | read | yes | yes | no | human.v1 | no | - | 0/2/10/12/20/30/40 | USAGE;NOT_INIT;UNSUPPORTED;AUTH;GIT;INTEGRITY | G010 | tests/contracts/test_sync_device_backup_cli.py | RQ-010,RQ-014,AC-010,AC-014,G009,G010 |
| CLI-079 | LOCK-079 | `watari backup restore` | `-` | `watari backup restore <target>` | canonical-write | yes | yes | no | human.v1 | no | - | 0/2/10/11/12/20/30/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;UNSUPPORTED;AUTH;GIT;INTEGRITY;POLICY | G010 | tests/contracts/test_sync_device_backup_cli.py | RQ-010,RQ-014,AC-010,AC-014,G009,G011,G010 |
| CLI-080 | LOCK-080 | `watari migrate claude inspect` | `-` | `watari migrate claude inspect [--json]` | read | no | no | no | human.v1 | yes | migration.v1 | 0/2/10/11/21 | USAGE;NOT_INIT;INVALID_SCHEMA;SOURCE | L007 | tests/contracts/test_migrate_cli.py | RQ-015,AC-015,L001,L007 |
| CLI-081 | LOCK-081 | `watari migrate claude snapshot` | `-` | `watari migrate claude snapshot` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/21/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;SOURCE;INTEGRITY;POLICY | L007 | tests/contracts/test_migrate_cli.py | RQ-015,AC-015,L002,L007 |
| CLI-082 | LOCK-082 | `watari migrate claude plan` | `-` | `watari migrate claude plan` | read | no | no | no | human.v1 | no | - | 0/2/10/11/21/40 | USAGE;NOT_INIT;INVALID_SCHEMA;SOURCE;INTEGRITY | L007 | tests/contracts/test_migrate_cli.py | RQ-015,AC-015,L003,L007 |
| CLI-083 | LOCK-083 | `watari migrate claude import --dry-run` | `-` | `watari migrate claude import --dry-run` | read | no | no | no | human.v1 | no | - | 0/2/10/11/21/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;SOURCE;INTEGRITY;POLICY;DRY_RUN | L007 | tests/contracts/test_migrate_cli.py | RQ-015,AC-015,L004,L005,L007 |
| CLI-084 | LOCK-084 | `watari migrate claude import --apply` | `-` | `watari migrate claude import --apply` | canonical-write | no | no | no | human.v1 | no | - | 0/2/10/11/21/30/40/50 | USAGE;NOT_INIT;INVALID_SCHEMA;SOURCE;GIT;INTEGRITY;POLICY | L007 | tests/contracts/test_migrate_cli.py | RQ-015,AC-015,L004,L005,L007 |
| CLI-085 | LOCK-085 | `watari migrate claude verify` | `-` | `watari migrate claude verify` | read | no | no | no | human.v1 | no | - | 0/2/10/11/21/40 | USAGE;NOT_INIT;INVALID_SCHEMA;SOURCE;INTEGRITY | L007 | tests/contracts/test_migrate_cli.py | RQ-015,AC-015,L006,L007 |

`watari`は`watari chat`のaliasであり、同じsession、auto-dream、context、retrieval、receipt
contractを使う。`watari doctor --deep`はcapabilityを読むだけで修復・login・network接続を
行わない。`--dry-run`のmanifest行は、canonical state、cache、checkpoint、Git ref、remoteを
含む全状態変更を0とする。D002のcommandはexternal writeを一切持たない。

## Stable exit codes

| code | token | meaning | required behavior |
| --- | --- | --- | --- |
| 0 | OK | success | requested operation completed |
| 2 | USAGE | CLI usage error | print usage/error; no state change |
| 10 | NOT_INIT | not initialized | identify required init; no fallback |
| 11 | INVALID_SCHEMA | config/schema invalid | fail closed; identify schema/version |
| 12 | UNSUPPORTED | dependency/runtime unavailable or unsupported | explicit unsupported status; no silent fallback |
| 20 | AUTH | connector auth/availability failure | redact secret; preserve prior state |
| 21 | SOURCE | source drift/unknown format/identity conflict | quarantine or pending; do not advance checkpoint |
| 30 | GIT | Git dirty/diverged/conflict | refuse unsafe sync/write; preserve prior revision |
| 40 | INTEGRITY | state integrity/verification failure | fail closed; no current pointer advance |
| 50 | POLICY | policy/security refusal | explain denied capability; no escalation |
| 60 | PARTIAL | partial dream; failed sources remain pending | report per-source result; checkpoint only successful atomic work |

Every command may return only the codes listed in its manifest row. Unknown commands return `2`.
Unsupported capabilities return `12` and are never represented as success or silently replaced.

## Failure tokens

| token | semantics |
| --- | --- |
| `USAGE` | malformed syntax, unknown command, unknown option, or alias mismatch; usage error `2` |
| `NOT_INIT` | state root is absent or not initialized; `10` |
| `INVALID_SCHEMA` | unknown/malformed schema, config, or output version; `11` |
| `UNSUPPORTED` | unqualified runtime, model, source, or dependency; `12` |
| `AUTH` | auth or connector availability failure; `20` |
| `SOURCE` | source drift, unknown format, or identity conflict; `21` |
| `GIT` | dirty/diverged/conflicted Git or failed sync precondition; `30` |
| `INTEGRITY` | verification, tamper, rollback, or state integrity failure; `40` |
| `POLICY` | visibility, sandbox, authorization, or security refusal; `50` |
| `PARTIAL` | one or more required sources failed and remain pending; `60` |
| `DRY_RUN` | operation is report-only and all state changes must be zero; command-specific success/failure code otherwise applies |
