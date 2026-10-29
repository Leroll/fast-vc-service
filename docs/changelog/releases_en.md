# Release history

These entries were moved from the original README.md on 2026-10-29, preserving their dates and text. They describe historical releases, not a new verification of current behavior. Follow the [current documentation](../README.md) for available commands and interfaces.

**2025-11-04 - v0.1.7**: Audio quality improvements and output sample-rate control

  - Quality
    - Added t_span_schedule (supports cosine reordering) to improve quality at the same step count
    - Unified realtime_vc output to 22 kHz for better fidelity
    - Preserve sufficient voiced context across long silences to improve coherence
  - Output sample rate
    - WebSocket adds sample_rate_out to return audio at the requested sample rate
  - Other
    - VAD settings moved into config for easier tuning and portability
    - time_records centralized under session management
    - Removed realtimevc perf tracing, file-vc scripts, and noise-gate module to reduce redundancy
    - Fixed audio not being persisted when upstream disconnects unexpectedly

**2025-10-16 - v0.1.6**: Multi-GPU/Multi-instance deployment, semantic feature retrieval, uv package management

  - Deployment & Concurrency
    - Support custom model and config file paths, enabling multiple instances with isolated configs and ports
    - Support single instance using multiple GPUs to improve concurrency
  - Quality & Effect
    - Added semantic feature retrieval module to improve voice similarity and robustness
    - Optimized VAD parameters to reduce noise and silence false triggers
  - Engineering
    - Migrated package management to uv for faster install and startup
    - Fixed send_slow false delay warning
    - Added VC evaluation tool tools/eval.py

**2025-07-24 - v0.1.5**: Pitch Adaptive Matching Support and Real-time Monitoring Optimization

  - Real-time monitoring optimization:
    - Optimized timeline_lognize, added delay items statistics for same event types
    - Added SLOW tags to logs for monitoring receive intervals, send intervals, and VC-E2E latency
  - Support for pitch adaptive matching with reference audio to improve conversion quality
    - Added pitch analysis script providing audio analysis tools
    - Added pitch adaptive matching functionality with corresponding toggle configuration
  - Other optimizations
    - Changed UID generation method to time-based generation for easier experimentation and testing
    - Optimized session tool's file naming mechanism
    - Added config and model path options, support NAS configuration files, enable simpler cloud host deployment


<details>
<summary>View Historical Versions</summary>

**2025-07-02 - v0.1.3**: Added Process and Instance Level Concurrency Monitoring  

  - Added PID record to logs for easier instance tracking
  - Added instance concurrency monitoring feature for real-time concurrency viewing
  - Optimized performance analysis interface to reduce impact on real-time performance

**2025-06-26 - v0.1.2**: Persistent Storage Optimization   

  - Optimized session persistent storage module with asynchronous processing
  - Separated time-consuming timeline statistical analysis module to improve response speed
  - Optimized timeline recording mechanism to reduce storage overhead

**2025-06-19 - v0.1.1**: First Packet Performance Optimization   

  - Added performance monitoring API endpoint /tools/performance-report for real-time performance metrics
  - Enhanced timing logs for better performance bottleneck analysis
  - Mitigated delay issue caused by first audio packet model invocation

**2025-06-15 - v0.1.0**: Basic Service Framework   

  Completed the core framework construction of real-time voice conversion service based on Seed-VC, implementing WebSocket streaming inference, performance monitoring, multi-format audio support and other complete basic functions.   

  - Real-time streaming voice conversion service
  - WebSocket API support for PCM and Opus formats
  - Complete performance monitoring and statistics system
  - Flexible configuration management and environment variable support 
  - Multi-Worker concurrent processing capability
  - Concurrent performance testing framework
  
</details>
