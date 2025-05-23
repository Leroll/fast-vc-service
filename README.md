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
    - [x] 输出ouput转换为16k之后再输出，同时使用切片赋值
    - [x] 新增session类，用于流式推理过程中上下文存储
    - [x] 冗余代码清理，删去不必要的逻辑
    - [x] 完成各模块流水线重构
    - [x] session 部分的替换完善
    - [ ] 添加配置信息
    - [x] 完善log系统
    - [ ] 完成ws服务代码 / webRTC
    - [ ] 裁剪封面图
    - [ ] file_vc，针对最后一个block的问题
    - [ ] 针对 异常情况，比如某个chunk转换rta>1的时候，有没有什么处理方案？
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