import os, statistics
p = r"C:\Users\conra\Desktop\universal - js hybrid\training\perseus\grc_trankit_sampled_10000\splits\train.conllu"
lens = []
spaceafter_no = 0
punct_attached = 0
total_tokens = 0
with open(p, "r", encoding="utf-8") as f:
    cur = None
    for ln in f:
        if ln.startswith("# text = "):
            cur = ln[len("# text = "):].rstrip("\n")
            lens.append(len(cur))
        elif ln.startswith("#") or ln.strip() == "":
            continue
        else:
            parts = ln.rstrip("\n").split("\t")
            if len(parts) >= 10:
                total_tokens += 1
                if "SpaceAfter=No" in parts[9]:
                    spaceafter_no += 1
print(f"sentences: {len(lens)}")
print(f"char-length mean={statistics.mean(lens):.1f} median={statistics.median(lens)} max={max(lens)} min={min(lens)}")
print(f">512 chars: {sum(1 for l in lens if l>512)} ({100*sum(1 for l in lens if l>512)/len(lens):.1f}%)")
print(f">256 chars: {sum(1 for l in lens if l>256)} ({100*sum(1 for l in lens if l>256)/len(lens):.1f}%)")
print(f"tokens total: {total_tokens}, SpaceAfter=No: {spaceafter_no} ({100*spaceafter_no/total_tokens:.1f}%)")
# para4 paragraph length
sents4 = [lens[i:i+4] for i in range(0, len(lens), 4)]
para4_lens = [sum(s) + 3 for s in sents4]  # +3 for 3 newlines
print(f"para4: max paragraph chars = {max(para4_lens)}, >512: {sum(1 for l in para4_lens if l>512)} / {len(para4_lens)}")
sents10 = [lens[i:i+10] for i in range(0, len(lens), 10)]
para10_lens = [sum(s) + 9 for s in sents10]
print(f"para10: max paragraph chars = {max(para10_lens)}, >512: {sum(1 for l in para10_lens if l>512)} / {len(para10_lens)}")
