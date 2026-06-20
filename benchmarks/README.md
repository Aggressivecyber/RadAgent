# RadAgent Benchmarks

This directory contains benchmark manifests and generated reports used to make
RadAgent validation claims auditable.

## NIST Photon Attenuation

`nist_photon_attenuation.json` is a reference benchmark for photon attenuation
through homogeneous slabs. It uses NIST mass attenuation coefficients for Pb,
Al, and liquid water at 0.5 MeV and 1.0 MeV, with three slab thicknesses per
material-energy pair.

The benchmark computes:

- `mu_ref = density_g_cm3 * mass_attenuation_cm2_g`
- `T_ref = exp(-mu_ref * thickness_cm)`
- `mu_observed = -ln(observed_transmission) / thickness_cm`
- `relative_error = abs(mu_observed - mu_ref) / mu_ref`

Acceptance criteria are stored in the manifest:

- observed fitted attenuation coefficient within 5% of the NIST reference
- repeated-run coefficient of variation at most 2%

Run the reference report:

```bash
python3 scripts/physics_benchmark.py \
  --manifest benchmarks/nist_photon_attenuation.json \
  --output benchmarks/reports/nist_photon_attenuation_reference_report.json
```

Render a Markdown table:

```bash
python3 scripts/physics_benchmark.py \
  --manifest benchmarks/nist_photon_attenuation.json \
  --format markdown \
  --output benchmarks/reports/nist_photon_attenuation_reference_report.md
```

The checked-in manifest is reference-only until RadAgent or laboratory
measurements add `observed_transmission` and `observed_cv` to each case.

One-command reproduction is available from the repository root:

```bash
./scripts/reproduce_nist_benchmark.sh --reference-only --output-dir benchmarks/reports
./scripts/reproduce_nist_benchmark.sh --events 100000 --repeats 1 --output-dir benchmarks/reports
```

Use `--geant4-required` when a missing Geant4 installation should fail the run
instead of producing only reference reports. Full environment and metric details
are documented in `docs/environment-and-nist-validation.md`.
