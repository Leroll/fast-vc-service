## 在vc转换过程中应该有这么几个 samplerate 需要注意和处理

- `in_sr` ： 待转换音频，或者说输入音频的采样率，音质差一点的 16k
- `sr` : 在 vc 的全流程中音频的采样率，比如16k，因为大部分模型 vad，semantic， denoise 的输入都是16k
- `dit_model_sr` : 换声模型 输出，在seed-vc里面是 22050 hz
- `out_sr` : 全流程结束后最终输出的 sr，这个和 In_sr 不一定相等，比如数字人系统中，可能就根据下游服务需要的 sr 来定
