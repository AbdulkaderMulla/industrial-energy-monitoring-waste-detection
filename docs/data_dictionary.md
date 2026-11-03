# Data dictionary

CSV values use UTF-8. IDs are immutable strings. Timestamps use ISO-8601 UTC (`Z`); empty optional dates are blank. `Unique` identifies a primary or business key. `—` means no separate unit, enum, or uniqueness constraint. Energy and demand are not interchangeable: interval `energy_kwh` is kWh over 15 minutes; `avg_power_kw` is the interval-average kW.

## Plant

| Field | Type | Required | Allowed values | Unit | Unique | Validation |
|---|---|---:|---|---|---|---|
| `plant_id` | string | yes | `PLANT-<nnn>` | — | PK | Nonblank and referenced by every plant-owned row. |
| `name` | string | yes | — | — | — | Nonblank display name. |
| `location` | string | yes | — | — | — | Nonblank location; synthetic profile uses a synthetic site. |
| `timezone` | IANA timezone string | yes | Valid IANA zone | — | — | Must resolve as a timezone; tariff matching uses the plant zone. |
| `status` | enum string | yes | `ACTIVE`, `INACTIVE` | — | — | Must be a supported lifecycle state. |

## Meter

| Field | Type | Required | Allowed values | Unit | Unique | Validation |
|---|---|---:|---|---|---|---|
| `meter_id` | string | yes | `MTR-<plant-id>-<nnn>` | — | PK | Immutable and referenced by readings, assignments and register totals. |
| `plant_id` | string | yes | Existing `plant_id` | — | FK | Parent plant must exist. |
| `meter_name` | string | yes | — | — | — | Nonblank. |
| `unit` | enum string | yes | `kWh_interval` | — | — | Canonical unit; noncanonical reading-unit cases are reported as exceptions. |
| `cadence_minutes` | integer | yes | Positive integer | minutes | — | Greater than zero; reading timestamps follow the declared cadence. |
| `status` | enum string | yes | `ACTIVE`, `INACTIVE` | — | — | Must be a supported lifecycle state. |

## Machine

| Field | Type | Required | Allowed values | Unit | Unique | Validation |
|---|---|---:|---|---|---|---|
| `machine_id` | string | yes | `MCH-<nnn>` | — | PK | Immutable. |
| `plant_id` | string | yes | Existing `plant_id` | — | FK | Parent plant must exist. |
| `machine_name` | string | yes | — | — | — | Nonblank. |
| `machine_type` | string | yes | `CNC`, `COMPRESSOR`, `PUMP`, `CONVEYOR` in generated data | — | — | Nonblank; generated profile uses the listed types. |
| `rated_power_kw` | decimal | yes | Nonnegative; generated values are positive | kW | — | Finite numeric value greater than zero. |
| `status` | enum string | yes | `ACTIVE`, `INACTIVE` | — | — | Lifecycle state; operating states are recorded separately in telemetry and `StateEvent`. |

## MeterMachine assignment (bridge)

| Field | Type | Required | Allowed values | Unit | Unique | Validation |
|---|---|---:|---|---|---|---|
| `assignment_id` | string | yes | `MM-<nnn>` | — | PK | Nonblank. |
| `meter_id` | string | yes | Existing `meter_id` | — | FK | Meter and machine must belong to the same plant. |
| `machine_id` | string | yes | Existing `machine_id` | — | FK | Meter/machine/time assignment is checked against each reading timestamp. |
| `effective_from` | timestamp string | yes | ISO-8601 UTC | — | — | Valid timestamp; unique assignment start per meter/machine pair. |
| `effective_to` | timestamp string | no | ISO-8601 UTC or blank | — | — | If present, later than `effective_from`; same-pair windows may not overlap. |

## EnergyReading

| Field | Type | Required | Allowed values | Unit | Unique | Validation |
|---|---|---:|---|---|---|---|
| `row_id` | string | yes | Reading ID or `EXC-*` fixture ID | — | PK | Unique source-row key, including deliberate duplicate-reading fixture. |
| `reading_id` | string | yes | `ENG-<meter-id>-<UTC timestamp>` or `EXC-*` fixture ID | — | Business key | Unique in baseline; duplicate values are retained only as labeled exceptions. |
| `meter_id` | string | yes | Existing `meter_id` | — | FK | Parent meter must exist. |
| `machine_id` | string | no | Existing `machine_id` or blank | — | FK | If present, same plant and effective meter assignment are checked; plant-level meters may omit it. |
| `shift_id` | string | no | Existing `shift_id` or blank | — | FK | When present, must match the effective shift calendar. Generated readings always have a shift. |
| `timestamp_utc` | timestamp string | yes | ISO-8601 UTC | — | — | Must lie on the meter's sampling grid. Timestamp denotes the interval start. |
| `energy_kwh` | decimal | yes | Finite, nonnegative | kWh / interval | — | Must equal `avg_power_kw × cadence_minutes / 60`; a 15-minute interval uses `0.25 h`. |
| `avg_power_kw` | decimal | yes | Finite, nonnegative | kW | — | Interval-average demand; reconcile against interval energy. |
| `unit` | string | yes | `kWh_interval`; `kW` in the labeled unit-confusion fixture | — | — | Canonical rows are included; noncanonical rows are excluded and reported, not silently converted. |
| `state` | enum string | yes | `RUNNING`, `IDLE`, `MAINTENANCE` | — | — | Must match the machine's operating state at that interval. |

## ProductionBatch

| Field | Type | Required | Allowed values | Unit | Unique | Validation |
|---|---|---:|---|---|---|---|
| `batch_id` | string | yes | `BATCH-2026-<nnnnnn>` | — | PK | Immutable. |
| `plant_id` | string | yes | Existing `plant_id` | — | FK | Parent plant must exist. |
| `shift_id` | string | yes | Existing `shift_id` | — | FK | Shift must belong to the plant and match `start_utc`. |
| `start_utc` | timestamp string | yes | ISO-8601 UTC | — | — | Valid batch start. |
| `end_utc` | timestamp string | yes | ISO-8601 UTC | — | — | Must be after `start_utc`. |
| `planned_output_units` | integer | yes | Nonnegative integer | units | — | Finite nonnegative value. |
| `actual_output_units` | integer | yes | Nonnegative integer | units | — | Must equal the sum of bridge `output_units`. |
| `status` | enum string | yes | `PLANNED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED` | — | — | Must be a supported lifecycle state. |

## BatchMachine assignment (bridge)

| Field | Type | Required | Allowed values | Unit | Unique | Validation |
|---|---|---:|---|---|---|---|
| `batch_machine_id` | string | yes | `BM-<nnnnnn>` | — | PK | Nonblank. |
| `batch_id` | string | yes | Existing `batch_id` | — | FK | Parent batch must exist. |
| `machine_id` | string | yes | Existing `machine_id` | — | FK | Machine must share the batch's plant. Pair is unique within a batch. |
| `output_units` | integer | yes | Nonnegative integer | units | — | Bridge output must reconcile to batch actual output. |

## Shift

| Field | Type | Required | Allowed values | Unit | Unique | Validation |
|---|---|---:|---|---|---|---|
| `shift_id` | string | yes | `SH-<nnn>` | — | PK | Immutable. |
| `plant_id` | string | yes | Existing `plant_id` | — | FK | Parent plant must exist. |
| `shift_name` | string | yes | `DAY`, `EVENING`, `NIGHT` in generated data | — | — | Nonblank. |
| `start_time` | `HH:MM` string | yes | Local clock time in plant timezone | — | — | Valid 24-hour time. |
| `end_time` | `HH:MM` string | yes | Local clock time in plant timezone | — | — | Valid 24-hour time; may cross midnight. |
| `effective_from` | timestamp string | yes | ISO-8601 UTC | — | — | Valid timestamp. |
| `effective_to` | timestamp string | no | ISO-8601 UTC or blank | — | — | If present, later than `effective_from`. |

## Tariff

| Field | Type | Required | Allowed values | Unit | Unique | Validation |
|---|---|---:|---|---|---|---|
| `tariff_id` | string | yes | `TAR-2026-<nnn>` | — | PK | Immutable. |
| `plant_id` | string | yes | Existing `plant_id` | — | FK | Parent plant must exist. |
| `tariff_name` | string | yes | `OFF_PEAK`, `NORMAL`, `PEAK` in generated data | — | — | Nonblank. |
| `start_hour_utc` | integer | yes | 0–23 | hour | — | Earlier than `end_hour_utc`; each covered interval uses its start hour. |
| `end_hour_utc` | integer | yes | 1–24 | hour | — | Later than start and no greater than 24. |
| `rate_inr_per_kwh` | decimal | yes | Finite, nonnegative | INR/kWh | — | Used only when tariff timezone matches plant timezone. |
| `effective_from` | timestamp string | yes | ISO-8601 UTC | — | — | Valid timestamp. |
| `effective_to` | timestamp string | no | ISO-8601 UTC or blank | — | — | If present, later than `effective_from`. |
| `timezone` | IANA timezone string | yes | Valid IANA zone | — | — | Must match plant timezone for pricing; mismatch is reported. |

## WeatherObservation

| Field | Type | Required | Allowed values | Unit | Unique | Validation |
|---|---|---:|---|---|---|---|
| `weather_id` | string | yes | `WTH-<nnnnn>` | — | PK | Immutable. |
| `plant_id` | string | yes | Existing `plant_id` | — | FK | Parent plant must exist. |
| `timestamp_utc` | timestamp string | yes | ISO-8601 UTC | — | — | Valid timestamp; generated every six hours. |
| `temperature_c` | decimal | yes | Finite numeric | °C | — | Descriptive environmental measure. |
| `humidity_pct` | decimal | yes | 0–100 | % | — | Must be within physical percentage range. |
| `condition` | enum string | yes | `CLEAR`, `CLOUDY`, `RAINY` | — | — | Must be a supported synthetic weather condition. |

## MaintenanceEvent

| Field | Type | Required | Allowed values | Unit | Unique | Validation |
|---|---|---:|---|---|---|---|
| `event_id` | string | yes | `MAINT-<nnnn>` | — | PK | Immutable. |
| `machine_id` | string | yes | Existing `machine_id` | — | FK | Parent machine must exist. |
| `event_type` | string | yes | `PREVENTIVE_INSPECTION` in generated data | — | — | Nonblank. |
| `start_utc` | timestamp string | yes | ISO-8601 UTC | — | — | Valid timestamp. |
| `end_utc` | timestamp string | no | ISO-8601 UTC or blank | — | — | If present, later than start. |
| `status` | enum string | yes | `PLANNED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED` | — | — | Must be a supported lifecycle state. |
| `notes` | string | no | — | — | — | Free-text synthetic note; blank is allowed. |

## Recommendation

| Field | Type | Required | Allowed values | Unit | Unique | Validation |
|---|---|---:|---|---|---|---|
| `recommendation_id` | string | yes | `REC-2026-<nnnnnn>` | — | PK | Immutable. |
| `machine_id` | string | yes | Existing `machine_id` | — | FK | Parent machine must exist. |
| `created_utc` | timestamp string | yes | ISO-8601 UTC | — | — | Valid timestamp. |
| `reason` | string | yes | — | — | — | Must cite the decision rule and baseline. |
| `baseline_kwh` | decimal | yes | Finite, nonnegative | kWh | — | Derived from valid idle readings in the observation window. |
| `expected_savings_kwh` | decimal | yes | Finite, nonnegative | kWh | — | 25% scenario estimate of baseline idle energy. |
| `expected_savings_inr` | decimal | yes | Finite, nonnegative | INR | — | Scenario savings priced only where a matching tariff is available. |
| `priority` | enum string | yes | `LOW`, `MEDIUM`, `HIGH` | — | — | Must be a supported priority. |
| `status` | enum string | yes | `OPEN`, `ACCEPTED`, `REJECTED`, `COMPLETED` | — | — | Must be a supported recommendation lifecycle state. |

## StateEvent (append-only)

| Field | Type | Required | Allowed values | Unit | Unique | Validation |
|---|---|---:|---|---|---|---|
| `state_event_id` | string | yes | `EVT-<16 uppercase hex chars>` | — | PK | Deterministic hash of event type, entity ID and event timestamp. |
| `entity_type` | enum string | yes | `MACHINE_STATUS`, `MACHINE_OPERATING_STATE` | — | — | Supported event stream type. |
| `entity_id` | string | yes | Existing `machine_id` | — | FK by event type | Parent machine must exist. |
| `old_state` | string | no | Previous state or blank for first event | — | — | Must equal prior event's `new_state` in that stream. |
| `new_state` | enum string | yes | `ACTIVE`/`INACTIVE` for status; `RUNNING`/`IDLE`/`MAINTENANCE` for operating state | — | — | Must be valid for `entity_type`. |
| `event_utc` | timestamp string | yes | ISO-8601 UTC | — | — | Strictly increasing within each entity stream. |
| `actor` | string | yes | `SYSTEM` in generated data | — | — | Nonblank source/actor identifier. |
| `reason` | string | yes | — | — | — | Records why the transition exists. |

## MeterRegisterTotal (support table)

| Field | Type | Required | Allowed values | Unit | Unique | Validation |
|---|---|---:|---|---|---|---|
| `meter_id` | string | yes | Existing `meter_id` | — | PK, FK | One snapshot per meter in this generated profile. |
| `register_total_kwh` | decimal | yes | Finite, nonnegative | kWh | — | Compared with valid interval sums; a deliberate mismatch is reported as an exception. |

## Ground-truth label (separate evaluation file; never an input feature)

| Field | Type | Required | Allowed values | Unit | Unique | Validation |
|---|---|---:|---|---|---|---|
| `ground_truth_id` | string | yes | `GT-<nnnn>` | — | PK | Unique label key. |
| `issue_type` | enum string | yes | The issue names in `generator/generate_data.py` | — | — | Must be a documented synthetic label type. |
| `entity_id` | string | yes | Source row or entity key | — | — | Must identify the affected reading, meter, tariff or machine. |
| `expected_detection` | boolean | yes | `true`, `false` | — | — | Evaluation target only. |
| `expected_decision` | string | yes | Documented decision rule | — | — | Nonblank expected action. |
| `rule` | string | yes | Documented business rule | — | — | Nonblank label explanation. |
| `label_source` | enum string | yes | `INJECTED_DEFECT`, `INJECTED_SHIFT_CONFIG`, `DOCUMENTED_RULE_ON_SOURCE` | — | — | States how the label was created; not read by detector. |
