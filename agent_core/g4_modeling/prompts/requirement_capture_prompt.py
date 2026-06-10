"""Prompt templates for G4 modeling LLM-driven nodes."""

REQUIREMENT_CAPTURE_PROMPT = """You are a Geant4 simulation requirements analyst.

Given the user's simulation request and task specification, extract structured
requirements for building a realistic Geant4 model. You MUST identify every
component the user mentions — do not simplify or merge layers.

User request:
{user_query}

Task specification:
{task_spec}

Respond with a JSON object containing:
{{
  "target_system": "Description of the system being modeled",
  "required_components": [
    {{
      "component_id": "unique_id",
      "display_name": "Human readable name",
      "component_type": "world|assembly|layer|volume|shielding|electrode|substrate",
      "geometry_type": "box|cylinder|sphere|tubs",
      "material": "Material name or composition",
      "role": "Purpose of this component",
      "source": "user_specified|inferred_from_context"
    }}
  ],
  "required_materials": [
    {{
      "name": "Material name",
      "classification": "nist|custom",
      "reason": "Why this material is needed"
    }}
  ],
  "required_sources": [
    {{
      "source_id": "unique source id when available",
      "particle_type": "proton|gamma|electron|...",
      "energy": "Energy with unit",
      "distribution": "mono|gaussian|spectrum",
      "spectrum_file": "path or null",
      "geometry": "pencil|broad_beam|isotropic",
      "direction": "[dx, dy, dz]",
      "angular_distribution": "mono|gaussian|isotropic|cosine|custom",
      "relative_weight": "relative source weight or null"
    }}
  ],
  "required_outputs": ["edep", "dose_3d", "event_table", ...],
  "forbidden_simplifications": [
    "Things that must NOT be simplified (e.g. 'Do not merge oxide layer')"
  ],
  "missing_information": [
    "Specific dimensions, materials, or parameters not provided by user"
  ]
}}

IMPORTANT RULES:
1. Extract EVERY component mentioned — layers, electrodes, substrates, shielding, housing, PCB
2. Do NOT merge multiple layers into one
3. Do NOT skip oxide layers, metal electrodes, or packaging
4. Mark information source as user_specified or inferred_from_context
5. List ALL missing dimensions and materials that need evidence lookup
6. For composite radiation fields, emit one required_sources item per source
   component and preserve source_id, spectrum_file, direction,
   angular_distribution, and relative_weight when provided
"""

GEOMETRY_DECOMPOSITION_PROMPT = """You are a Geant4 geometry decomposition specialist.

Given the structured requirements and available evidence, decompose the target
system into a complete component tree for Geant4 modeling.

Requirements:
{requirements}

Evidence:
{evidence}

Coordinate system:
{coordinate_system}

Create a JSON array of component specifications. Each component must have:
- component_id: unique string identifier (snake_case)
- display_name: human-readable description
- component_type: one of "world", "assembly", "layer", "volume",
  "shielding", "electrode", "substrate"
- geometry_type: one of "box", "cylinder", "sphere", "tubs", "cons", "polycone", "trapezoid"
- dimensions: dict with shape-specific keys (box: dx/dy/dz as half-lengths, cylinder: rmin/rmax/dz)
- material_id: reference to a material definition
- placement: {{position: [x,y,z], rotation: [rx,ry,rz]}} relative to mother volume
- mother_volume: parent component_id (null for world only)
- sensitive: true if this is a scoring region
- roles: list of functional roles
- source_evidence: list of evidence references for these dimensions
- open_issues: list of unresolved missing dimensions/material details
- requires_confirmation: true when any required field is missing evidence

RULES:
1. Exactly ONE world volume (component_type="world") — must be first
2. All dimensions MUST come from evidence — do NOT invent values
3. Use half-lengths for box (dx=half_width), consistent with Geant4 convention
4. Layer stacking: use z-axis for beam direction, place layers contiguously
5. Do NOT merge or skip any layer the user specified
6. Keep dimensions present, but include only evidence-backed numeric keys
7. If a dimension is unknown, leave that key out, add a precise open_issues entry,
   and set requires_confirmation=true
8. Never use 0.0, 1.0, TODO, "unknown", "default", or other placeholder values
   to satisfy missing dimensions
"""

PHYSICS_SELECTION_PROMPT = """You are a Geant4 physics list selection specialist.

Given the particle type or composite radiation field source summary, energy range,
target materials, and scoring requirements, select the most appropriate Geant4
physics list and explain your choice.

Particle/source components: {particle_type}
Energy: {energy} {energy_unit}
Target materials: {materials}
Scoring requirements: {scoring_requirements}
Evidence: {evidence}

Respond with a JSON object:
{{
  "physics_list": "FTFP_BERT|QGSP_BIC_HP|Shielding|Livermore|...",
  "selection_reasoning": (
    "Detailed explanation of why this physics list covers the "
    "required processes. Must reference particle type, energy "
    "range, and target output."
  ),
  "em_physics": "standard|livermore|penelope|option4 or null",
  "hadronic": "bertini|binary_cascade|qgsp or null",
  "decay": true,
  "cuts": {{"gamma": 0.1, "e-": 0.1, "e+": 0.1, "proton": 0.1}} or null,
  "hp_neutron": false,
  "source_evidence": ["evidence references"]
}}

RULES:
1. Do NOT default to FTFP_BERT without justification
2. For gamma/electron below 1 GeV, consider Livermore or Option4
3. For neutron transport, consider QGSP_BIC_HP with NeutronHP data
4. For proton therapy (10-250 MeV), QGSP_BIC is often better than FTFP_BERT
5. selection_reasoning must be at least 50 characters explaining the choice
6. Reference specific physics processes needed for the simulation
7. For a composite radiation field, consider all source components together,
   not only the first particle in the list
"""

MATERIAL_DEFINITION_PROMPT = """You are a Geant4 material definition specialist.

Given the required materials list and available evidence, define each material
with proper Geant4 parameters.

Required materials:
{materials}

Evidence:
{evidence}

For each material, determine:
- If it's a NIST standard material (G4_Si, G4_Al, etc.) — use G4NistManager
- If custom — define element composition and density

Respond with a JSON array of material specs:
[{{
  "material_id": "unique_id",
  "name": "Display name",
  "classification": "nist|custom",
  "nist_name": "G4_Si or null",
  "composition": [{{"element": "Si", "fraction": 0.467}}, ...] or null,
  "density_g_cm3": 2.33,
  "state": "solid|liquid|gas",
  "source_evidence": ["evidence references"]
}}]

RULES:
1. Use NIST materials whenever possible (G4_Si, G4_Al, G4_Cu, etc.)
2. For SiO2: custom material with Si (46.7% mass) and O (53.3% mass), density 2.65 g/cm³
3. For FR4: custom material with approximate composition, density ~1.85 g/cm³
4. ALL density and composition values must have source_evidence
5. Do NOT use "silicon" as a default for unknown materials
"""

SOURCE_DEFINITION_PROMPT = """You are a Geant4 particle source configuration specialist.

Given the source requirements and evidence, configure the particle source.

Requirements:
{requirements}

Evidence:
{evidence}

Respond with a JSON source spec:
{{
  "source_id": "primary_source",
  "particle_type": "proton",
  "energy": {{
    "value": 10.0,
    "unit": "MeV",
    "distribution": "mono|gaussian|uniform|spectrum",
    "sigma": null
  }},
  "beam": {{
    "position": [0, 0, -500],
    "direction": [0, 0, 1],
    "sigma_position_um": null,
    "sigma_direction_rad": null,
    "surface_shape": "point|circle|rectangle",
    "surface_size": null
  }},
  "generator_type": "gun|gps",
  "events": 1000,
  "source_evidence": ["evidence references"]
}}

RULES:
1. Simple mono-energetic pencil beam → use gun
2. Broad beam, spectrum, or angular spread → use gps
3. Position should place source outside the target
4. Direction should point toward the target center
5. All parameters must reference source_evidence
"""

SCORING_DESIGN_PROMPT = """You are a Geant4 scoring design specialist.

Given the scoring requirements, component tree, and evidence, design the
scoring mesh and region scoring configurations.

Requirements:
{requirements}

Components:
{components}

Evidence:
{evidence}

Respond with a JSON array of scoring specs:
[{{
  "scoring_id": "unique_id",
  "scoring_type": "voxel|region|mesh",
  "quantities": ["edep_MeV", "dose_Gy"],
  "voxel_grid": {{
    "target_component_id": "silicon_bulk",
    "voxel_size": [10.0, 10.0, 10.0]
  }} or null,
  "region_scores": [
    {{"region_component_id": "oxide_layer", "quantity": "dose_Gy"}}
  ],
  "output_format": "csv",
  "source_evidence": ["evidence references"]
}}]

RULES:
1. Voxel scoring for 3D dose maps — choose voxel size based on feature size
2. Region scoring for specific layers (oxide dose, electrode edep)
3. Output format must be "csv" for g4_output_package compatibility
4. Voxel size should resolve the smallest feature (at least 10 voxels across)
5. All scoring must reference source_evidence
"""
