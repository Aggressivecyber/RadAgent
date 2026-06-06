"""SPICE simulation runner.

MVP-1: Stub. Full implementation in MVP-6.
"""


class SPICERunner:
    """SPICE simulation runner.

    MVP-1: Stub. Full implementation in MVP-6.
    """

    def __init__(self) -> None:
        self.available = False

    async def run(self, netlist_path: str, **kwargs: object) -> dict[str, object]:
        return {"success": False, "error": "SPICE runner not yet implemented"}

    async def smoke_test(self, netlist_path: str) -> dict[str, object]:
        return {"success": False, "available": False, "error": "Not implemented"}
