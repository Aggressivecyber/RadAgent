"""SPICE RAG tool - stub implementation for MVP-1 with full interface."""


class SPICERAGTool:
    """SPICE RAG tool for retrieving SPICE-related context.

    MVP-1: Stub implementation that returns empty results.
    Full implementation will be added in MVP-6.
    """

    def __init__(self, endpoint: str | None = None):
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
            "target_module": "spice",
            "retrieved_context": {
                "manual_snippets": [],
                "example_code": [],
                "data_contracts": [],
                "error_cases": [],
                "benchmark_cases": [],
            },
            "sufficiency": {
                "score": 0.0,
                "missing_items": ["SPICE RAG not yet implemented"],
                "decision": "block",
            },
            "query_used": query,
            "sources_queried": [],
        }
