## 测试环境 Test Environment

- **GPU**: NVIDIA RTX 4090D
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
|1     |6     |136.0      |143.0   |105.0       |0.21   |0.22    |0.24   |
|3     |6     |205.3      |168.0   |148.4       |0.32   |0.28    |0.55   |
|6     |6     |133.8      |241.2   |177.4       |0.36   |0.36    |0.43   |
|6     |12    |151.5      |232.3   |206.3       |0.42   |0.43    |0.50   | 
|8     |12    |159.8      |318.0   |232.9       |0.48   |0.48    |0.61   |
|10    |12    |144.8      |351.7   |217.1       |0.44   |0.45    |0.52   |
|12    |12    |140.1      |256.6   |216.6       |0.44   |0.45    |0.51   |


**时间单位**: 毫秒 (ms)   
**Time Unit**: Milliseconds (ms)   
**✅ 所有测试场景均达到实时处理要求 (RTF < 1.0)**   
**✅ All test scenarios meet real-time processing requirements (RTF < 1.0)**   


## 测试结论 Test Conclusions
- **1080ti 推荐生产配置**: 建议并发数为2-3个客户端，能够维持良好的实时处理性能。   
- **GTX 1080 Ti Recommended Production Configuration**: Recommended concurrency of 2-3 clients to maintain good real-time processing performance.   

### ps: 
- 你可以运行 `python examples/websocket/concurrent_ws_client.py` 来测试fast-vc在你本地的性能表现。
- You can run `python examples/websocket/concurrent_ws_client.py` to test the performance of fast-vc on your local machine.




