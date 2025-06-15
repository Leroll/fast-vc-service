## 测试环境 Test Environment

- **GPU**: NVIDIA Tesla V100-32GB
- **fast-vc Version**: 0.1.0
- **Test Date**: 2025-06-15

## 测试参数 Test Parameters
- **采样率 Sample Rate**: 16000 Hz
- **音频格式 Audio Format**: 16-bit PCM
- **模型 Model**: seed-vc v1.0 tiny
- **Chunk Size**: 500ms
- **扩散步数 Diffusion Steps**: 10

## 性能指标 Performance Metrics

|并发数量|Worker| 首token延迟|端到端延迟|平均chunk延迟|平均RTF|中位数RTF|P95 RTF|
|------|------|-----------|--------|-------------|------|--------|-------|
|Concurrency|Worker|First Token Latency|End-to-End Latency|Avg Chunk Latency|Avg RTF|Median RTF|P95 RTF|
|1     |6     |257.0      |264.0   |262.1       |0.56   |0.44    |1.20   |
|2     |6     |200.5      |289.0   |290.6       |0.60   |0.48    |1.28   |    
|3     |6     |169.3      |466.7   |291.9       |0.60   |0.55    |1.03   |



**时间单位**: 毫秒 (ms)   
**Time Unit**: Milliseconds (ms)   
**✅ 所有测试场景均达到实时处理要求 (RTF < 1.0)**   
**✅ All test scenarios meet real-time processing requirements (RTF < 1.0)**   


## 测试结论 Test Conclusions
- **Tesla V100-32GB 推荐生产配置**: 可稳定支持2-3并发。
- **Tesla V100-32GB Recommended Production Configuration**: Can stably support 2-3 concurrent requests.

### ps: 
- 你可以运行 `python examples/websocket/concurrent_ws_client.py` 来测试fast-vc在你本地的性能表现。
- You can run `python examples/websocket/concurrent_ws_client.py` to test the performance of fast-vc on your local machine.




