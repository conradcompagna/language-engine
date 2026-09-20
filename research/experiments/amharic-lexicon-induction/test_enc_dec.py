from llama_cpp import (Llama, llama_model_has_encoder, llama_encode,
                       llama_decode, llama_batch_get_one, llama_batch_free,
                       llama_token_eos, llama_model_decoder_start_token,
                       llama_sampler_chain_init, llama_sampler_chain_default_params,
                       llama_sampler_init_greedy, llama_sampler_chain_add,
                       llama_sampler_sample, llama_sampler_free)
import os, ctypes

llm = Llama(model_path='madlad400-3b-mt-q2_k.gguf', n_ctx=512, n_threads=os.cpu_count(), verbose=False)

text = '<2en> Bonjour le monde'
tokens = llm.tokenize(text.encode())
print('input tokens:', len(tokens))

# Encode
arr = (ctypes.c_int32 * len(tokens))(*tokens)
batch = llama_batch_get_one(arr, len(tokens))
ret = llama_encode(llm._ctx.ctx, batch)
print('encode ret:', ret)
llama_batch_free(batch)

# Greedy decode
dec_start = llama_model_decoder_start_token(llm._model.model)
eos = llama_token_eos(llm._model.model)
print(f'decoder_start={dec_start}, eos={eos}')

sparams = llama_sampler_chain_default_params()
smplr = llama_sampler_chain_init(sparams)
llama_sampler_chain_add(smplr, llama_sampler_init_greedy())

cur_token = dec_start
output_tokens = []
for _ in range(256):
    arr2 = (ctypes.c_int32 * 1)(cur_token)
    batch2 = llama_batch_get_one(arr2, 1)
    ret2 = llama_decode(llm._ctx.ctx, batch2)
    llama_batch_free(batch2)
    if ret2 != 0:
        print('decode error:', ret2)
        break
    cur_token = llama_sampler_sample(smplr, llm._ctx.ctx, -1)
    if cur_token == eos:
        break
    output_tokens.append(cur_token)

llama_sampler_free(smplr)
result = llm.detokenize(output_tokens).decode('utf-8', errors='replace')
print('Translation:', result)
