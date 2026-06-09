# Global Integration Agent

## Purpose

The global integration agent is the only cross-module writer in the Geant4
codegen flow. Module agents still own their individual files, and module repair
still fixes only one failed module at a time. The global integration agent runs
after all module layers pass and turns the module outputs into one coherent
project patch.

## Flow

```text
module agents
  -> module hard/LLM gates
  -> module repair if a single module fails
  -> integration_assembler
  -> global_integration_agent
  -> static semantic scan
  -> cross-file hard/LLM gates
  -> patch_subgraph
  -> gate_subgraph runtime gates
```

## Responsibilities

- Read the assembled project files from `proposed_patch.changed_files`.
- Read module contracts, module contexts, module gate results, interface
  contracts, and runtime failure context.
- Query the local database through the RAG client.
- Query the internet through the web search tool when available.
- Return a schema-preserving `proposed_patch`.
- Align constructors, includes, CMake wiring, main wiring, adapters, wrappers,
  and artifact-output wiring across modules.

## Boundaries

- It must not delete, simplify, or empty out module responsibilities.
- It must not introduce `content`; generated file bodies use `new_content`.
- Paths stay relative to `08_geant4`.
- It writes only through the returned patch; actual disk writes still go through
  `patch_subgraph`.
- The final runtime gate is outside codegen: `gate_subgraph` must pass build,
  ctest, data contract, and smoke simulation checks.

## Relationship To Module Repair

Module repair is local. It receives one module result and one module gate
failure, then returns a repaired version of that module's files.

The global integration agent is cross-module. It receives all module results and
can edit any generated project file to make the full program consistent.

## Runtime Gate

The codegen graph does not claim final runtime success. After the patch is
applied, `gate_subgraph` runs `Geant4Runner.smoke_test()`. Gates 6-9 require the
program to configure, build, run ctest, generate the required output files, and
complete a smoke simulation. Runtime gate failures route back to codegen with
failure context for another integration pass.
