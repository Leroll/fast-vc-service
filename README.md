<p align="center">
    <img src="https://raw.githubusercontent.com/Leroll/fast-vc-service/main/asserts/cover.PNG" alt="repo cover" width=80%>
</p>

**高性能流式换声服务，专为工业级部署打造，助力高效、稳定的语音交互体验。**  
目前基于 基于 [Seed-VC](https://github.com/Plachtaa/seed-vc) 换声模型开发  


# 🚧 施工中...TODO
- [ ] tag - v0.1 - 基础服务相关 - v2025-xx
    - [x] 完成初版流式推理代码 
    - [x] 新增.env用于存放源等相关变量
    - [x] 拆分流式推理各模块
    - [x] 新增性能追踪统计模块
    - [x] 增加opus编解码模块
    - [x] 新增asgi app服务和log日志系统，解决uvicorn与loguru的冲突问题
    - [ ] 输出ouput转换为16k之后再输出，同时使用切片赋值
    - [ ] 新增session类，用于流式推理过程中上下文存储
    - [ ] 冗余代码清理，删去不必要的逻辑
    - [ ] 完成各模块流水线重构
    - [ ] 添加配置信息
    - [ ] 完善log系统
    - [ ] 完成ws服务代码 / webRTC
    - [ ] 裁剪封面图
    - [ ] file_vc，针对最后一个block的问题
- [ ] tag - v0.2 - 音频质量相关 -  v2025-xx
    - [ ] 声音貌似有些抖动，待排查
    - [ ] 针对男性低沉嗓音转换效果不加的情况，添加流式场景下的音高提取功能
- [ ] tag - v0.3 - 服务灵活稳定相关 - v2025-xx
    - [ ] reference 使用torchaudio 直接读取到GPU中，省去转移的步骤。
    - [ ] 配置化启动不同的模型实例，配置为不同的微服务？
    - [ ] 制作AutoDL镜像，方便一键部署