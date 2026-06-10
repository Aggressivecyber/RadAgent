# Global Integration Agent

## Purpose

The global integration agent is the only cross-module writer in the Geant4
codegen flow. Coarse module agents own their initial file groups, while runtime
execution and physics review observations are routed back to the global
integration agent when the assembled project needs repair.

## Flow

```text
module agents
  -> layer consistency gates
  -> integration_assembler
  -> global_integration_agent
  -> runtime_execution_audit
  -> physics_quality_review
  -> persist_codegen_output
```

## Responsibilities

- Read the assembled project files from `proposed_patch.changed_files`.
- Read module contracts, module contexts, interface contracts, and runtime or
  physics failure observations.
- Query the local database through the RAG client.
- Query the internet through the web search tool when available.
- Return a schema-preserving `proposed_patch`.
- Align constructors, includes, CMake wiring, main wiring, adapters, wrappers,
  and artifact-output wiring across modules.

## Boundaries

- It must not delete, simplify, or empty out module responsibilities.
- It must not introduce `content`; generated file bodies use `new_content`.
- Paths stay relative to `geant4_project`.
- It writes only through the returned patch; actual disk writes still go through
  `patch_subgraph`.
- The runtime gate is part of codegen auditing: it must prove build, ctest,
  artifact contract, and smoke simulation actually ran.

## Relationship To Runtime Repair

There is no separate per-module repair loop. The global integration agent is
cross-module: it receives all module results plus runtime/physics observations
and can edit any generated project file to make the full program consistent.

## Runtime Gate

The codegen graph does not claim runtime success until
`runtime_execution_audit` accepts trustworthy artifacts. Runtime failures route
back to the global integration agent once with concrete cmake/build/ctest/smoke
and artifact evidence. Physics review runs only after runtime execution passes.
