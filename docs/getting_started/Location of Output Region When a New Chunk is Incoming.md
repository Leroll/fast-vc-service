1. structure of `input_wav` :
    [ extra + crossfade + sola_search + block + extra_right ]
  
2. processing new chunk:  
    ``` 
    input_wav[: -block] = input_wav[block: ].clone()  # shift left by block size 
    input_wav[-chunk_size: ] = chunk  # append new chunk to the end 
    ```

3. input_wav 
    -> s_alt
    -> s_alt = s_alt[ce_dit_difference: ]
    -> cond = length_regulator(s_alt)
    -> (prompt_cond + cond)
        + prompt_mel
        + prompt_style  => [ dit_model ]  
    -> vc_target => [ vocoder_model ]
    -> output_wav
    -> output_wav[ ( - sola_buffer - sola_search - block ) - extra_right: -extra_right]
    -> that is the final output

4. so, 
    - new chunk is appended to the end of input_wav
    - however, the final output is derived from a region before the end of input_wav, adjusted by extra_right

    Therefore, extra_right introduces unavoidable latency in the system.

5. ps:
    - sola_buffer = min(crossfade, 4*zc)
    - when sola_buffer exceeds crossfade:
        - the region [ skip_head + return_length + skip_tail ] will exceed the input size
        - when it is reduced by ce_dit_difference, the extra part is actually stolen from ce_dit_difference.
