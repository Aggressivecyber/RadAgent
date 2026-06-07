"""G4 Codegen nodes — modular C++ generation from Model IR.

Each node reads from the codegen subgraph state and produces exactly one
C++ module. The nodes delegate to the shared codegen implementations
in agent_core.g4_modeling.codegen where applicable.
"""
