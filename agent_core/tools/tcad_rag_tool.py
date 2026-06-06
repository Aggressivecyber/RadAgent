"""TCAD RAG tool — stub for MVP-1 (Geant4-only scope).

MVP-1 scope: Geant4 only. TCAD retrieval will be added in MVP-4+.
Source: knowledge_base/tcad/ (future)
"""


class TcadTool:
    """TCAD RAG tool — returns empty results until TCAD scope is implemented."""

    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = endpoint
        self.available = False

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        return []

    async def get_manual_snippets(self, topic: str) -> list[dict]:
        return []

    async def get_example_code(self, task_description: str) -> list[dict]:
        return []

    async def get_data_contract_info(self) -> list[dict]:
        return []

    async def build_context_pack(self, query: str, task_spec: dict) -> dict:
        return {
            "job_id": "",
            "target_module": "tcad",
            "retrieved_context": {
                "manual_snippets": [],
                "example_code": [],
                "data_contracts": [],
                "error_cases": [],
                "benchmark_cases": [],
            },
            "sufficiency": {
                "score": 0.0,
                "missing_items": ["TCAD RAG not yet implemented"],
                "decision": "block_no_context",
            },
            "query_used": query,
            "sources_queried": [],
        }
