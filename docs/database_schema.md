# Database relationships

- Plant 1:N Meter.
- Plant 1:N Machine.
- Plant 1:N ProductionBatch, Shift, Tariff and WeatherObservation.
- Meter 1:N EnergyReading.
- Meter 1:1 MeterRegisterTotal in the generated snapshot (the source register table stores one reconciliation snapshot per meter).
- Machine 1:N MaintenanceEvent and Recommendation.
- Meter N:M Machine through `meter_machine` with effective dates.
- ProductionBatch N:M Machine through `batch_machine`.
- Machine 1:N StateEvent by application-level `(entity_type, entity_id)` reference. The event log stores lifecycle and operating-state transitions.
- Data-quality findings are computed from source rows at analysis time and are not stored in the database. Ground-truth labels are not loaded into the database.

Optional relationships: EnergyReading.machine_id is nullable for plant-level meters and `shift_id` may be null in imported data; generated readings populate both. Assignment `effective_to`, tariff/shift `effective_to`, and maintenance `end_utc` may be null for open-ended records. Batch-machine associations are required for batch-level machine analysis. MaintenanceEvent and Recommendation are optional for any machine.

Every table has an explicit primary key; bridge tables have their own primary keys and foreign keys. `state_events.entity_id` is polymorphic, so the validator checks the referenced machine, event type, state domain, transition chain and timestamp order. Lifecycle and operating-state changes are appended to StateEvent; source event history is not overwritten.
