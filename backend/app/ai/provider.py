"""Provider-neutral AI boundary. Implementations must return proposals, never approved facts."""
from typing import Any, Protocol


class VisionProvider(Protocol):
    async def analyze_sketch(self, image_bytes: bytes, *, language_hint: str = "fa,en") -> dict[str, Any]:
        """Return source-linked observations and ambiguities for human review."""
        ...


class AIUnavailableError(RuntimeError):
    pass
