from dataclasses import dataclass, asdict
from typing import Any, Optional
from datetime import datetime

@dataclass
class BasePacket:
    type: str
    timestamp: str
    data: Optional[Any] = None
    
    def to_dict(self) -> dict:
        return asdict(self)

class PacketFactory:
    @staticmethod
    def create(packet_type: str, data: Any = None) -> BasePacket:
        return BasePacket(
            type=packet_type,
            timestamp=datetime.now().isoformat(),
            data=data
        )
