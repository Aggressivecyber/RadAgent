"""TCAD simulation runner — stub for MVP-1."""


class TCADRunner:
    """TCAD simulation runner.

    MVP-1: Stub. Full implementation in MVP-4.
    """

    def __init__(self):
        self.available = False

    async def run(self, command_file: str, **kwargs) -> dict:
        """Execute a TCAD command file. Not yet implemented."""
        return {"success": False, "error": "TCAD runner not yet implemented"}

    async def smoke_test(self, project_dir: str) -> dict:
        """Run a minimal TCAD smoke test. Not yet implemented."""
        return {"success": False, "available": False, "error": "Not implemented"}
