## 测试环境 Test Environment

- **GPU**: NVIDIA GTX 1080 Ti
- **fast-vc Version**: 0.1.0
- **Test Date**: 2025-06-14

## 测试参数 Test Parameters
- **采样率 Sample Rate**: 16000 Hz
- **音频格式 Audio Format**: 16-bit PCM
- **模型 Model**: seed-vc v1.0 tiny
- **Chunk Size**: 500ms
- **扩散步数 Diffusion Steps**: 10
- **并发数量 Concurrency**: 1, 2, 3

## 性能指标 Performance Metrics

| 并发数量 | 首token延迟(ms) | 端到端延迟(ms) | 平均chunk延迟(ms) | 平均RTF | 中位数RTF | P95 RTF |
|--------|----------------|---------------|-----------------|---------|----------|---------|
| Concurrency | First Token Latency(ms) | End-to-End Latency(ms) | Avg Chunk Latency(ms) | Avg RTF | Median RTF | P95 RTF |
| 1  | 157.0 | 272.0 | 252.2  | 0.50 | 0.51 | 0.61 | 
| 2  | 157.5 | 283.5 | 273.63 | 0.55 | 0.58 | 0.61 |
| 3  | 154.3 | 261.3 | 304.93 | 0.61 | 0.62 | 0.73 |

**✅ 所有测试场景均达到实时处理要求 (RTF < 1.0)**   
**✅ All test scenarios meet real-time processing requirements (RTF < 1.0)**   


## 测试结论 Test Conclusions
- **1080ti 推荐生产配置**: 建议并发数为2-3个客户端，能够维持良好的实时处理性能。   
- **GTX 1080 Ti Recommended Production Configuration**: Recommended concurrency of 2-3 clients to maintain good real-time processing performance.   

### ps: 
- 你可以运行 `python examples/websocket/concurrent_ws_client.py` 来测试fast-vc在你本地的性能表现。
- You can run `python examples/websocket/concurrent_ws_client.py` to test the performance of fast-vc on your local machine.




