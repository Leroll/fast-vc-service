from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class ProtocolAdapter(ABC):
    """协议适配器基类"""
    
    @abstractmethod
    def parse_init_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """将初始化消息转换为标准格式"""
        pass
    
    @abstractmethod
    def should_send_ready(self) -> bool:
        """是否需要发送ready消息"""
        pass
    
    @abstractmethod
    def format_complete_message(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """格式化完成消息"""
        pass
    
    @abstractmethod
    def format_error_message(self, error_code: str, message: str, session_id: str = "", details: Dict = None) -> Dict[str, Any]:
        """格式化错误消息"""
        pass
    
    @abstractmethod
    def is_end_message(self, message: Dict[str, Any]) -> bool:
        """判断是否为结束消息"""
        pass

class StandardProtocolAdapter(ProtocolAdapter):
    """标准协议适配器"""
    
    def parse_init_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        # 直接返回，无需转换
        return message
    
    def should_send_ready(self) -> bool:
        return True
    
    def format_complete_message(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "complete",
            "stats": stats
        }
    
    def format_error_message(self, error_code: str, message: str, session_id: str = "", details: Dict = None) -> Dict[str, Any]:
        error_msg = {
            "type": "error",
            "error_code": error_code,
            "message": message
        }
        if details:
            error_msg["details"] = details
        return error_msg
    
    def is_end_message(self, message: Dict[str, Any]) -> bool:
        return message.get("type") == "end"

class SimpleProtocolAdapter(ProtocolAdapter):
    """简单协议适配器"""
    
    def parse_init_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if message.get("signal") == "start":
            # 转换为标准格式
            standard_config = {
                "type": "config",
                "session_id": message.get("stream_id", ""),
                "api_key": "simple_protocol",  # 为简单协议设置一个特殊的api_key
                "sample_rate": message.get("sample_rate", 16000),
                "sample_rate_out": message.get("sample_rate_out", 16000),
                "bit_depth": message.get("sample_bit", 16),
                "channels": 1,  # 默认单声道
                "encoding": message.get("encoding", "PCM")  # 支持encoding参数，默认PCM格式
            }
            
            # 如果原消息中有opus_frame_duration参数，传递给标准配置
            if "opus_frame_duration" in message:
                standard_config["opus_frame_duration"] = message["opus_frame_duration"]
                
            return standard_config
        return message
    
    def should_send_ready(self) -> bool:
        return False  # 简单协议不需要ready消息
    
    def format_complete_message(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "signal": "completed"
        }
    
    def format_error_message(self, error_code: str, message: str, session_id: str = "", details: Dict = None) -> Dict[str, Any]:
        return {
            "status": "failed",
            "stream_id": session_id,
            "error_msg": message
        }
    
    def is_end_message(self, message: Dict[str, Any]) -> bool:
        return message.get("signal") == "end"