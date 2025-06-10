from enum import Enum
from typing import Dict, Type
from .protocol_adapter import ProtocolAdapter, StandardProtocolAdapter, SimpleProtocolAdapter

class ProtocolType(Enum):
    STANDARD = "standard"
    SIMPLE = "simple"

PROTOCOL_ADAPTERS: Dict[ProtocolType, Type[ProtocolAdapter]] = {
    ProtocolType.STANDARD: StandardProtocolAdapter,
    ProtocolType.SIMPLE: SimpleProtocolAdapter,
}

class ProtocolDetector:
    """协议检测器"""
    
    @staticmethod
    def detect(message: dict) -> ProtocolType:
        """检测消息协议类型"""
        if message.get("signal") == "start":
            return ProtocolType.SIMPLE
        elif message.get("type") == "config":
            return ProtocolType.STANDARD
        else:
            return ProtocolType.STANDARD
    
    @staticmethod
    def get_adapter(protocol_type: ProtocolType) -> ProtocolAdapter:
        """获取对应的适配器实例"""
        adapter_class = PROTOCOL_ADAPTERS.get(protocol_type, StandardProtocolAdapter)
        return adapter_class()