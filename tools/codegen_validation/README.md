# Codegen generality validation

Drive the `g4_codegen` subgraph directly against diverse G4ModelIR inputs to
test that the agentic codegen + repair loop converges across geometries,
particles, and physics lists — without the flaky textual TUI harness.

## Usage

```bash
# 1. Generate diverse IR variants from a known-good base IR.
python tools/codegen_validation/gen_variant_irs.py   # -> /tmp/variant_irs/*.json

# 2. Run codegen on one scenario (writes /tmp/codegen_validate_result_<name>.json).
python tools/codegen_validation/run_codegen_scenario.py /tmp/variant_irs/gamma.json gamma

# 3. Or run several in parallel and monitor.
for s in multi_layer gamma cylinder; do
  setsid bash -c "python tools/codegen_validation/run_codegen_scenario.py /tmp/variant_irs/$s.json $s > /tmp/cv_$s.log 2>&1" &
done
./tools/codegen_validation/monitor_scenarios.sh
```

The audit reads `runtime_attempt_N/g4_output_package/smoke_simulation_result.json`
(the canonical gate output, not the transient agent-loop `smoke_output/`).

## Interpreting results

- `any_smoke_passed` + non-zero `total_edep_MeV` = the scenario converged.
- `g4_codegen_status=failed` with a passing smoke usually means the
  `physics_quality_reviewer` flagged an internally-inconsistent IR (e.g.
  `source_evidence` strings don't match the declared source). Fix the IR's
  evidence fields, not the codegen.

When a NEW runtime error pattern surfaces, add a deterministic known-fix hint
to `agent_core/dev_tools/shell.py::_KNOWN_GEANT4_FIXES` and/or a prevention
note to `module_context_examples.py` — that is the lever that keeps expanding
coverage.
