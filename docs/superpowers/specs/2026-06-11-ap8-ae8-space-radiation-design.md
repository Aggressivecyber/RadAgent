# AP8/AE8 Space Radiation Extension Design

## Goal

Add a local AP8/AE8 trapped-radiation data extension that RadAgent can expose to the copilot and use when a user asks for Geant4 simulation of a space-orbit radiation environment.

## Scope

The implementation builds the production orbit-environment loop:

- download or verify the AP8/AE8 data files locally under `knowledge_base/space_radiation/data/ap8ae8/`;
- record source metadata, hashes, and model limits in a manifest;
- detect space-orbit radiation requests during briefing and ordinary copilot turns;
- require enough orbit/environment information before claiming a source is ready;
- resolve AP8/AE8 flux from geodetic orbit samples (`lat`, `lon`, `height`, `time`) or direct magnetic coordinates (`L-shell`, `B/B0`);
- support TLE-derived orbit samples through the runtime orbital stack;
- create a Geant4 source package that references a generated spectrum file through the existing `SourceSpec.energy.spectrum_file` path.

## Data Source

Default source is NASA `radbelt`:

- repository: `https://github.com/nasa/radbelt`
- data path: `radbelt/extern/aep8/`
- files: `ap8min.asc`, `ap8max.asc`, `ae8min.asc`, `ae8max.asc`, `trmfun.f`, `README.md`, `LICENSE.txt`

The implementation records the NASA CCMC provenance described by the upstream README and keeps the raw model files in gitignored `knowledge_base/**/data/`.

## Architecture

`knowledge_base.space_radiation` owns data paths and download/manifest code. `agent_core.space_radiation` owns request parsing, model selection, orbit sampling, flux evaluation, validation, and Geant4 source package generation.

Runtime dependencies:

- `aep8`: NASA AE8/AP8 model through IRBEM, including geomagnetic coordinate conversion and integral/differential flux.
- `astropy`: time, units, and Earth location objects.
- `skyfield` and `sgp4`: TLE orbit propagation and sampling support.

The briefing copilot gets explicit prompt instructions for orbit radiation. It must ask for missing orbit coordinates or L-shell/B/B0, particle type, solar period, flux mode, shielding/target, scoring, and event counts. It must not treat AP8/AE8 as a modern dynamic space-weather model.

The chat copilot gets read-only context explaining the local AP8/AE8 extension and limitations.

## Data Flow

1. User says they want space-orbit radiation simulation.
2. Briefing identifies an orbit radiation request.
3. If geodetic orbit samples are available, the provider resolves geomagnetic coordinates with `aep8`.
4. If a TLE and time range are available, the provider samples the trajectory with `skyfield`/`sgp4` and resolves AP8/AE8 flux at those samples.
5. If L-shell and B/B0 are available, the provider evaluates AP8/AE8 directly.
6. If particle type, solar period, flux mode, and geometry/scoring details are available, `agent_core.space_radiation` creates a source package.
5. The package maps into task particles with:
   - `type`: `proton` or `e-`
   - `energy_distribution`: `spectrum`
   - `spectrum_file`: generated CSV path
   - `generator_type`: `gps`
   - `source_evidence`: AP8/AE8 manifest reference and input coordinates
7. Existing G4 modeling/codegen uses `SourceSpec.energy.spectrum_file`.

## Limits

AP8/AE8 covers trapped proton/electron belt models, not solar proton events, GCR, or real-time space weather. Altitude/inclination alone are not enough to define a unique trajectory or exposure history; briefing must ask for a TLE, explicit geodetic samples, or direct magnetic coordinates.

## Testing

Tests cover:

- manifest creation from local AP8/AE8 files with hashes and model metadata;
- source package readiness and missing-field reporting;
- spectrum file generation using true AP8/AE8 flux through the runtime `aep8` model;
- geodetic and TLE orbit environment inputs;
- mapping a source package into a task particle and `SourceSpec`;
- briefing prompt requirements for orbit radiation;
- chat prompt/context mention of local AP8/AE8 and limitations.
