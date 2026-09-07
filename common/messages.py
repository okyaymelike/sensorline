import json
from dataclasses import asdict, dataclass, fields


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
        # Tolerant reader: ignore unknown keys (e.g. a producer's schema_version)
        # so the wire contract can gain fields without breaking this consumer.
        data = json.loads(raw.decode("utf-8"))
        known = {f.name for f in fields(Reading)}
        return Reading(**{k: v for k, v in data.items() if k in known})
