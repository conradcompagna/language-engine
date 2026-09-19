"""
Compare CAMeL Tools tokenization vs custom Trankit tokenizer+MWT expander directly.
"""
import os, sys
from pathlib import Path

TRAINING_ROOT = Path(__file__).resolve().parents[2]
os.environ["CAMELTOOLS_DATA"] = str(TRAINING_ROOT / "camel_tools_bundle")
os.environ["TEMP"] = str(TRAINING_ROOT / "camel_tools_tmp")
os.environ["TMP"] = str(TRAINING_ROOT / "camel_tools_tmp")
os.environ["HOME"] = str(TRAINING_ROOT)
os.environ["USERPROFILE"] = str(TRAINING_ROOT)

from camel_tools.tokenizers.word import simple_word_tokenize
from camel_tools.tokenizers.morphological import MorphologicalTokenizer
from camel_tools.disambig.mle import MLEDisambiguator

TEXT = """أصل الحروب الصليبية تكمن في التطورات في أوروبا الغربية في وقت سابق من العصور الوسطى، فضلًا عن تدهور حالة الإمبراطورية البيزنطية في الشرق الناجمة عن موجة جديدة من الهجمات التركية المسلمة.

انهيار الإمبراطورية الكارولانجية في أواخر القرن التاسع، جنبًا إلى جنب مع الاستقرار النسبي للحدود المحلية الأوروبية بعد تنصير كلٍ من الفايكنج، والسلاف، والمجريين، قد أنتجت الكثير من الطبقة المسلحة وبروز الطاقات التي كانت في غير محلها قتال بعضهم بعضًا، وإرهاب السكان المحليين."""

SAVE_DIR = TRAINING_ROOT / "t_ar10k2"

# ── CAMeL Tools ───────────────────────────────────────────────────────────────
print("Loading CAMeL Tools MLE...")
mle = MLEDisambiguator.pretrained("calima-msa-r13")
cam_tokenizer = MorphologicalTokenizer(disambiguator=mle, scheme="atbtok", split=True, diac=False)

camel_results = []
for para in TEXT.strip().split("\n\n"):
    para = para.strip()
    if not para:
        continue
    words = simple_word_tokenize(para)
    toks = cam_tokenizer.tokenize(words)
    toks = [t.replace("+", "").strip() for t in toks if t.replace("+", "").strip()]
    camel_results.append((para, toks))

# ── Trankit directly ──────────────────────────────────────────────────────────
print("Loading Trankit with custom Arabic model...")
import trankit
pipeline = trankit.Pipeline(lang="arabic", cache_dir=str(SAVE_DIR))

trankit_results = []
for para, _ in camel_results:
    doc = pipeline(para)
    toks = []
    for sent in doc.get("sentences", []):
        for tok in sent.get("tokens", []):
            # MWT tokens have 'expanded' field
            expanded = tok.get("expanded")
            if expanded:
                for child in expanded:
                    toks.append(child.get("text", ""))
            else:
                toks.append(tok.get("text", ""))
    trankit_results.append(toks)

# ── Output ────────────────────────────────────────────────────────────────────
out = Path(__file__).parent / "tokenizer_comparison.txt"
with out.open("w", encoding="utf-8") as f:
    f.write("ARABIC TOKENIZATION: CAMeL Tools vs Trankit+MWT\n")
    f.write("=" * 80 + "\n\n")

    total_camel = 0
    total_trankit = 0

    for i, ((para, c_toks), t_toks) in enumerate(zip(camel_results, trankit_results)):
        f.write(f"── Paragraph {i+1} ──\n")
        f.write(f"CAMeL  ({len(c_toks)}): {' | '.join(c_toks)}\n\n")
        f.write(f"Trankit({len(t_toks)}): {' | '.join(t_toks)}\n\n")
        c_set, t_set = set(c_toks), set(t_toks)
        only_c = sorted(c_set - t_set)
        only_t = sorted(t_set - c_set)
        if only_c: f.write(f"  Only CAMeL:   {only_c}\n")
        if only_t: f.write(f"  Only Trankit: {only_t}\n")
        f.write("\n")
        total_camel += len(c_toks)
        total_trankit += len(t_toks)

    f.write("=" * 80 + "\n")
    f.write(f"Total CAMeL tokens:   {total_camel}\n")
    f.write(f"Total Trankit tokens: {total_trankit}\n")
    f.write(f"Ratio: {total_trankit/max(1,total_camel):.2f}\n\n")

    # Clitic coverage
    CLITICS = {"و", "ب", "ل", "ك", "ف", "ال", "س", "ها", "ه", "هم", "هن", "نا", "كم"}
    c_clitics = sum(1 for _, toks in camel_results for t in toks if t in CLITICS)
    t_clitics = sum(1 for toks in trankit_results for t in toks if t in CLITICS)
    f.write(f"CAMeL clitic tokens:   {c_clitics}\n")
    f.write(f"Trankit clitic tokens: {t_clitics}\n")
    f.write(f"Clitic coverage: {100*t_clitics/max(1,c_clitics):.1f}%\n")

print(f"Written to {out}")
