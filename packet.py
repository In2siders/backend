from dataclasses import dataclass, asdict
from typing import Any, Optional
from datetime import datetime

@dataclass
class BasePacket:
    type: str
    timestamp: str
    data: Optional[Any] = None

    def __hash__(self):
        return hash((self.type, self.timestamp))

    def to_json(self) -> str:
        import json
        return json.dumps(asdict(self))

    def to_dict(self) -> dict:
        return asdict(self)
    
    def validate(self) -> bool:
        # Basic validation example
        if not self.type or not self.timestamp:
            return False
        return True
    
    def is_type(self, packet_type: str) -> bool:
        return self.type.upper() == packet_type.upper()

class PacketFactory:
    @staticmethod
    def create(packet_type: str, data: Any = None) -> BasePacket:
        return BasePacket(
            type=packet_type,
            timestamp=datetime.now().isoformat(),
            data=data
        )

    @staticmethod
    def from_json(json_str: str) -> BasePacket:
        import json
        packet_dict = json.loads(json_str)
        return PacketFactory.from_dict(packet_dict)

    @staticmethod
    def from_dict(packet_dict: dict) -> BasePacket:
        return BasePacket(
            type=packet_dict.get('type', ''),
            timestamp=packet_dict.get('timestamp', ''),
            data=packet_dict.get('data', None)
        )