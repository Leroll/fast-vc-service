<p align="center">
    <img src="https://raw.githubusercontent.com/Leroll/fast-vc-service/main/asserts/cover.PNG" alt="repo cover" width=80%>
</p>

<div align="center">
  <img alt="GitHub stars" src="https://img.shields.io/github/stars/Leroll/fast-vc-service?style=social">
  <a href="https://github.com/Leroll/fast-vc-service/commits/main">
    <img alt="GitHub last commit" src="https://img.shields.io/github/last-commit/Leroll/fast-vc-service">
  </a>
  <img alt="License" src="https://img.shields.io/badge/License-GPL%20v3-blue.svg">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10+-blue.svg">
</div>

<div align="center">
  <h3>基于 Seed-VC 的实时换声服务，提供 WebSocket 接口，支持 PCM 和 Opus 音频格式</h3>
</div> 

<div align="center">
  <a href="README.md">English</a> | 简体中文
</div>
<br>

> 功能持续迭代更新中。欢迎关注我们的最新进展... ✨

# 🚀 快速开始

## 环境配置

### 方式一：使用 Poetry（推荐）
```bash
git clone --recursive https://github.com/Leroll/fast-vc-service.git
cd fast-vc-service
cp .env.example .env  # 配置模型下载路径与下载源
poetry install  # 安装依赖
```

### 方式二：使用 pip
```bash
git clone --recursive https://github.com/Leroll/fast-vc-service.git
cd fast-vc-service
cp .env.example .env  # 配置模型下载路径与下载源
pip install -e .  # 以可编辑模式安装项目及其依赖
```

当第一次运行时，模型会自动下载到checkpoint文件夹下。  
如果有网络问题，可取消注 `.env` 文件中的 `HF_ENDPOINT` 变量，使用国内镜像源加速模型下载。


## 启动服务
```bash
# 启动服务
fast-vc serve  # 默认启动在 0.0.0.0:8042, 使用 2 workers
fast-vc serve --host 127.0.0.1 --port 8080 --workers 4 # 自定义

# 使用 Poetry
poetry run fast-vc serve
```

<!-- 添加服务启动演示 -->
<p align="center">
    <img src="https://github.com/Leroll/fast-vc-service/releases/download/v0.0.1/fast-vc-serve.gif" alt="服务启动演示" width="800">
    <br>
    <em>🚀 服务启动过程</em>
</p>

## 服务管理
```bash
# 查看服务状态
fast-vc status

# 停止服务（优雅关闭）
fast-vc stop
fast-vc stop --force   # 强制

# 清理日志文件
fast-vc clean
fast-vc clean -y  # 跳过确认

# 查看版本信息
fast-vc version
```

### 服务管理说明
- `serve`: 启动 FastAPI 服务器
- `status`: 检查服务运行状态和进程信息
- `stop`: 优雅关闭服务（发送 SIGINT 信号）
- `stop --force`: 强制关闭服务（发送 SIGTERM 信号）
- `clean`: 清理 logs/ 目录下的日志文件
- `clean -y`: 清理日志文件，跳过确认提示
- `version`: 显示服务版本信息

服务信息会自动保存到项目的 `temp/` 目录下，支持进程状态检查和自动清理。


<p align="center">
    <img src="https://github.com/Leroll/fast-vc-service/releases/download/v0.0.1/fast-vc-command.gif" alt="支持命令演示" width="800">
    <br>
    <em>🚀 命令演示</em>
</p>

# 📡 实时流式换声

## WebSocket 连接流程
```mermaid
sequenceDiagram
    participant C as 客户端
    participant S as 服务器
    
    C->>S: 配置连接请求
    S->>C: 就绪确认 ✅
    
    loop 实时音频流
        C->>S: 🎤 音频块
        S->>C: 🔊 转换音频
    end
    
    C->>S: 结束信号
    S->>C: 完成状态 ✨
```

**详细的WebSocket API规范请参考**: [WebSocket API规范](docs/%E6%8E%A5%E5%8F%A3%E6%96%87%E6%A1%A3/WebSocket%20API%E8%A7%84%E8%8C%83.md)  
**支持格式**: PCM | OPUS  

## 🔥 快速测试

### WebSocket 实时换声
```bash
python examples/ws_client.py \
    --source-wav-path "wavs/sources/low-pitched-male-24k.wav" \
    --encoding OPUS
```

### 批量文件测试, 用于验证换声效果
```bash
python examples/file_vc.py \
    --source-wav-path "wavs/sources/low-pitched-male-24k.wav" \
    --reference-wav-path "wavs/references/ref-24k.wav" \
    --block-time 0.5 \
    --diffusion-steps 10
```


# 🚧 施工中...TODO
- [ ] tag - v0.1 - 基础服务相关 - v2025-xx
    - [x] 完成初版流式推理代码 
    - [x] 新增.env用于存放源等相关变量
    - [x] 拆分流式推理各模块
    - [x] 新增性能追踪统计模块
    - [x] 增加opus编解码模块
    - [x] 新增asgi app服务和log日志系统，解决uvicorn与loguru的冲突问题
    - [x] 输出ouput转换为16k之后再输出，同时使用切片赋值
    - [x] 新增session类，用于流式推理过程中上下文存储
    - [x] 冗余代码清理，删去不必要的逻辑
    - [x] 完成各模块流水线重构
    - [x] session 部分的替换完善
    - [x] 完善log系统
    - [x] 完成ws服务代码 + PCM
    - [x] 完成ws + opus 服务代码
    - [x] Readme中添加websocket支持的描述，然后画出流程图
    - [x] 优化requirement包管理方式，更易用与稳定
    - [x] 新增clean命令，用于清理日志文件
    - [x] 新增多worker支持
    - [x] 抽取ws-server中音频处理逻辑至独立函数中
    - [x] 抽取ws-server中结尾残留音频处理逻辑至独立函数中
    - [ ] 新增ws超时关闭链接机制，触发回收
    - [ ] 添加配置信息
    - [ ] 增加性能测试模块
    - [ ] 在session中增加，单通录音的各种耗时统计，删去realtime-vc的相关代码
    - [x] 解决 ws_client 收到的音频缺少尾部片段的问题
    - [ ] 音频按天存储
    - [ ] ws_client 增加发送音频samplerate的设置
    - [ ] 支持webRTC
    - [ ] 裁剪封面图
    - [ ] file_vc，针对最后一个block的问题
    - [ ] 针对 异常情况，比如某个chunk转换rta>1的时候，有没有什么处理方案？
    - [ ] 解决 semaphore leak 的问题
- [ ] tag - v0.2 - 音频质量相关 -  v2025-xx
    - [ ] infer_wav 每个chunk大小问题排查，在经过vcmodel之后，为8781，不经过的话为9120【sola模块记录】
    - [ ] 声音貌似有些抖动，待排查
    - [ ] 针对男性低沉嗓音转换效果不加的情况，添加流式场景下的音高提取功能
    - [ ] 完成对seed-vc V2.0 模型支持
- [ ] tag - v0.3 - 服务灵活稳定相关 - v2025-xx
    - [ ] reference 使用torchaudio 直接读取到GPU中，省去转移的步骤。
    - [ ] 配置化启动不同的模型实例，配置为不同的微服务？
    - [ ] 制作AutoDL镜像，方便一键部署
    - [ ] 新增get请求返回加密wav
    - [ ] 新增wss支持
    - [ ] 鉴权部分更新为令牌（JWT）方式

# 🙏 致谢
- [Seed-VC](https://github.com/Plachtaa/seed-vc) - 提供了强大的底层变声模型
- [RVC](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) - 提供了基础的流式换声pipeline