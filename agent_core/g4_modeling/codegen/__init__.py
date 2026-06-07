"""G4 codegen nodes — structured C++ code generation.

8 codegen nodes, each strictly limited to its own domain.
Parameters come exclusively from G4ModelIR specs.
"""

from agent_core.g4_modeling.codegen.component_geometry_codegen import (
    component_geometry_codegen,
)
from agent_core.g4_modeling.codegen.material_registry_codegen import (
    material_registry_codegen,
)
from agent_core.g4_modeling.codegen.output_manager_codegen import (
    output_manager_codegen,
)
from agent_core.g4_modeling.codegen.physics_macro_codegen import (
    physics_macro_codegen,
)
from agent_core.g4_modeling.codegen.placement_codegen import placement_codegen
from agent_core.g4_modeling.codegen.scoring_codegen import scoring_codegen
from agent_core.g4_modeling.codegen.sensitive_detector_codegen import (
    sensitive_detector_codegen,
)
from agent_core.g4_modeling.codegen.source_codegen import source_codegen

__all__ = [
    "component_geometry_codegen",
    "material_registry_codegen",
    "output_manager_codegen",
    "physics_macro_codegen",
    "placement_codegen",
    "scoring_codegen",
    "sensitive_detector_codegen",
    "source_codegen",
]
