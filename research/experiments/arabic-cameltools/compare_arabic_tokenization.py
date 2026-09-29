"""Compare CAMeL Tools morph segmentation vs live Arabic Trankit tokenization.
Both systems receive diacritic-stripped text for a fair comparison.
"""
from __future__ import annotations
import json, sys, os, re, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ── The text (original with diacritics) ──
TEXT_RAW = """أصل الحروب الصليبيَّة تكمن في التطورات في أوروبا الغربية في وقت سابق من العصور الوسطى، فضلًا عن تدهور حالة الإمبراطورية البيزنطية في الشرق الناجمة عن موجة جديدة من الهجمات التركية المسلمة.

انهيار الإمبراطورية الكارولانجية في أواخر القرن التاسع، جنبًا إلى جنب مع الاستقرار النسبي للحدود المحلية الأوروبية بعد تنصير كلٍ من الفايكنج، والسلاف، والمجريين، قد أنتجت الكثير من الطبقة المسلحة وبروز الطاقات التي كانت في غير محلها قتال بعضهم بعضًا، وإرهاب السكان المحليين. حاولت الكنيسة كبح هذا العنف مع حركات السلام والهدنة مع الله، والتي كانت ناجحة إلى حد ما، لكن طبقة المحاربين كانوا يسعون دائمًا لإيجاد منفذ لمهاراتهم، وأصبح فرض التوسع الإقليمي، أقل جاذبية بالنسبة لقطاعات كبيرة من النبلاء. وكان هناك استثناء واحد هو حروب الاسترداد في إسبانيا و\u200cالبرتغال، فرسان قلعة رباح وفرسان سانتياغو في إسبانيا و\u200cفرسان الهيكل في البرتغال وبعض المرتزقة من أماكن أخرى في أوروبا في مكافحة الوجود الإسلامي. أعطى البابا إسكندر الثاني بركته لمسيحيي إيبيريا الكاثوليك في حروبهم ضد المسلمين.

جردت الحملات الصليبية أيضًا غير محاربة الإسلام والمسلمين إذ كان هدفها في البداية أيضًا محاربة البابا لمخالفيه، فقد جاء الصليبيون من شمال بلدهم الأصلي فرنسا إلى جنوبها لكي يقاتلوا الهراطقة الألبيجنسيين. فمنذ نهاية القرن الحادي عشر بدأت بوادر المقاومة ضد الكنيسة البابوية في روما وسيطرتها على شؤون الحياة الأوروبية، وعند نهاية القرن الثاني عشر ذاعت الأفكار التي أخذ يواقيم الفلورى (Jouchim Flora) يدعو لها، وقد لاقت أفكاره الدينية الذيوع بسرعة ملحوظة. وسار يواقيم على نهج سان برنار الذي زعم أن العالم قد دخل عصر المسيح الدجال الذي يسبق قيام القيامة. وعلى حين اكتفى سان برنار بإدانة كبار الأساقفة على اعتبار أنهم أسرى الشيطان، فإن يواقيم جعل البابوية نفسها هي المسيح الدجال. وقلب بذلك حق وراثة بابا روما للمسيح رأساً على عقب. وحاز شعبية واسعة لدى جميع الفرق المخالفة، ونتج عن أفكاره هذه أن ظهرت عصبة جمعت حولها عدداً ضخماً من الأتباع في جنوب فرنسا تدعى الكارتاريون (Czthari) أي الأطهار أو الألبيجنسيون نسبة إلى بلدة Albi في مقاطعة تولوز والتي كانت معقلاً لهم. وعند نهاية القرن الثاني عشر كان سكان المدن الأثرياء ونبلاء تولوز وبروفانس إما أعضاء في الكنيسة الألبيجانسية وإما من المتعاطفين مع قادتها. وكانت البابوية في روما سنة 1200م ترى في السيطرة الألبيجنسية على جنوب فرنسا سرطان ينهش في جسد العالم المسيحي يجب استئصاله بأي ثمن، لأنها رأت فيها ديانة مختلفة. وتطورت الأحداث بالشكل الذي أدى إلى إعلان بابا روما قرار حرمان على ريموند السادس أمير تولوز، وإباحة أراضيه وأملاك الألبيجنسيين، فتحمس لذلك أمراء شمال فرنسا واندفعوا في حملة صليبية سنة 1209 قضت على الأمراء الأقطاعيين في جنوب فرنسا، واقتسموا إقطاعاتهم.كذلك يمكن أن نصور الغزو الجزئي الذي قام به الأنجلو ـ نورمان لأيرلندا على أنه نمط من أنماط الحروب الصليبية رغم أن ضحاياه كانوا من الكاثوليك.

جاءت بداية الحروب الصليبية في فترة كانت فيها أوروبا قد تنصرت بالكامل تقريبًا بعد اعتناق الفايكينج والسلاف والمجر للمسيحية. فكانت طبقة المحاربين الأوروبيين قد أصبحوا بلا عدو لقتاله، فأصبحوا ينشرون الرعب بين السكان، وتحولوا إلى السرقة وقطع الطرق والقتال في ما بينهم، فكان من الكنيسة أن حاولت التخفيف بمنع ذلك ضد جماعات معينة في فترات معينة من أجل السيطرة على حالة الفوضى القائمة. وفي ذات الوقت أفسح المجال للأوربيين للاهتمام بموضوع الأرض المقدسة التي فتحها المسلمون منذ عدة قرون ولم يتسن للأوربيين الالتفات لها لانشغالهم بالحروب ضد غير المسيحيين من الفايكنج والمجريين الذين كانوا يشكلون المشكلة الأقرب جغرافيًا سابقًا، وكذلك بدأت الكنيسة تلعب دورًا في الحرب الاستردادية في إسبانيا، حيث قام البابا إسكندر الثاني عام 1063 بمباركة المحاربين الذاهبين إلى الأندلس، الأمر الذي لعب دورًا كبيرًا في تكوين فكرة الحرب المقدسة."""


def strip_arabic_diacritics(text):
    """Remove Arabic diacritics (tashkeel): fathatan, dammatan, kasratan,
    fatha, damma, kasra, sukun, shadda, superscript alif, tatweel."""
    return re.sub(r"[\u064B-\u0652\u0670\u0640]", "", text)


# Stripped text used for both systems
TEXT = strip_arabic_diacritics(TEXT_RAW)


def run_camel_morph_only():
    """Run CAMeL Tools morphological tokenizer standalone (no Trankit)."""
    print("[1/2] Running CAMeL Tools morph segmentation …")
    from camel_tools_arabic_tokenizer import (
        _get_camel_tools_bundle,
        _iter_sentence_chunks,
        _normalize_morph_token,
    )
    bundle = _get_camel_tools_bundle()

    results = []
    for chunk in _iter_sentence_chunks(TEXT):
        base_tokens = list(bundle.simple_word_tokenize(chunk) or [])
        for bt in base_tokens:
            morph_group = list(bundle.morph_tokenizer.tokenize([bt]) or [])
            normalized = [_normalize_morph_token(t) for t in morph_group]
            normalized = [t for t in normalized if t]
            results.append({
                "word": bt,
                "morph_segments": normalized,
                "joined": "+".join(normalized),
            })
    return results


def run_trankit_arabic():
    """Run Trankit on Arabic text (native tokenizer, no CAMeL)."""
    print("[2/2] Running Trankit (native Arabic tokenizer + MWT) …")
    from language_registry import init_trankit, run_trankit

    # Force native tokenizer for this comparison
    os.environ.pop("LE_ARABIC_CAMELTOOLS_TOKENIZER", None)
    os.environ["LE_ARABIC_TOKENIZER_PATH"] = "native"

    init_trankit()
    doc = run_trankit(TEXT, "ar")
    results = []
    for sent in doc.get("sentences", []):
        for tok in sent.get("tokens", []):
            entry = {"text": tok.get("text", ""), "id": tok.get("id")}
            if "upos" in tok:
                entry["upos"] = tok["upos"]
            if "lemma" in tok:
                entry["lemma"] = tok["lemma"]
            if "expanded" in tok:
                entry["expanded"] = tok["expanded"]
            results.append(entry)
    return results


def main():
    print(f"Diacritics stripped. Sample: {TEXT[:80]}...")
    print()

    camel_results = run_camel_morph_only()
    trankit_results = run_trankit_arabic()

    output = {
        "note": "Both systems received diacritic-stripped text",
        "camel_tools_morph_segmentation": {
            "description": "CAMeL Tools morphological tokenizer (ATB scheme, MLE disambiguator)",
            "token_count": len(camel_results),
            "tokens": camel_results,
        },
        "trankit_native": {
            "description": "Trankit native Arabic tokenizer + MWT expansion",
            "token_count": len(trankit_results),
            "tokens": trankit_results,
        },
    }

    out_path = os.path.join(os.path.dirname(__file__), "arabic_tokenization_comparison.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nWritten to {out_path}")
    print(f"CAMeL tokens: {len(camel_results)}, Trankit tokens: {len(trankit_results)}")


if __name__ == "__main__":
    main()
