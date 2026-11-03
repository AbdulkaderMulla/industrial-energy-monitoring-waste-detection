# Business rules and assumptions

1. A meter belongs to one plant. A meter can serve one or more machines over effective-dated assignments; a machine can be associated with multiple meters. `MeterMachine` is the bridge.
2. Energy readings are interval measurements. Valid interval energy is kWh; interval-average power is kW.
3. For 15-minute intervals, average kW = interval kWh / 0.25 hours.
4. A batch can involve multiple machines and a machine can participate in multiple batches; `BatchMachine` is the bridge.
5. Shift and tariff windows use UTC in this synthetic baseline. Tariff matching uses the reading interval start. Tariff records include effective dates and a time window.
6. Production output is allocated across a batch's active machines. Energy intensity is reported only where output is positive.
7. High idle consumption is flagged when the machine is marked idle and interval-average demand exceeds 30% of its rated power.
8. Peak demand is the maximum valid interval-average kW. Demand spikes are not discarded merely for being unusual.
9. Weather relationships are exploratory correlation only; they are not causal claims.
10. Weather observations join valid energy readings and production output by plant and matching 6-hour UTC bucket. Batch output is prorated by duration where a batch crosses a bucket boundary. Pearson coefficients report sample counts and are suppressed when fewer than three usable points or no variation exists.
11. Anomaly labels are generated from the explicit injection manifest and stored separately. Detection operates on source records and rules, not ground truth.
12. Meter-total reconciliation compares an independent meter register total to summed interval energy.
13. The kW/kWh confusion fixture stores a declared unit mismatch; detection flags it rather than silently converting source values.
14. Tariff timezone mismatch is recorded as an issue fixture; baseline tariff evaluation remains in UTC.
15. Duplicate reading fixtures have their own distinct source row identifier while retaining a duplicate business reading identity.
16. Cross-hierarchy assignment fixtures reference a machine outside the meter's effective assignment and are flagged as relationship exceptions.
17. State changes are append-only records. Master status events use `MACHINE_STATUS`; telemetry transitions use `MACHINE_OPERATING_STATE`. Each transition's old state must equal the previous event's new state, with strictly increasing UTC event times.
18. Recommendation savings are estimates based on observed valid idle energy and applicable time-of-use tariff rates where available. They are not measured post-intervention savings.
