"""TCAD-to-SPICE mapping contract schema."""

from typing import Optional

from pydantic import BaseModel, Field


class TCADToSPICEContract(BaseModel):
    """Contract defining how TCAD simulation results map into SPICE circuit elements."""

    schema_version: str = Field(
        default="tcad_to_spice_v1",
        description="Contract schema identifier.",
    )
    simulation_id: str = Field(
        description="Unique identifier linking back to the TCAD simulation run.",
    )
    radiation_current_source: str = Field(
        description="File path to the .cir file containing the radiation-induced current source.",
    )
    degraded_device_model: Optional[str] = Field(
        default=None,
        description="File path to the .lib file with degraded device model parameters.",
    )
    mapping_method: str = Field(
        default="PWL_current_source",
        description="Method used to map TCAD data into SPICE (e.g., PWL_current_source).",
    )
    mapping_report: str = Field(
        description="File path to the mapping report documenting the transformation.",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Assumptions made during the TCAD-to-SPICE mapping.",
    )
