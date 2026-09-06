import json
from dataclasses import asdict, dataclass


# The wire contract every source emits to the readings topic.
@dataclass
class Reading:
    device_external_id: str
    device_kind: str
    metric: str
    value: float
    unit: str
    sampled_at: str  # ISO-8601, UTC
    location: str | None = None
    firmware: str | None = None

    def to_bytes(self) -> bytes:
        return json.dumps(asdict(self)).encode("utf-8")

    @staticmethod
    def from_bytes(raw: bytes) -> "Reading":
        return Reading(**json.loads(raw.decode("utf-8")))
