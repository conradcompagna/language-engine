"""Generate plain-text segmented versions of the Arabic text."""
import json, sys, io, re

with open("arabic_tokenization_comparison.json", encoding="utf-8") as f:
    data = json.load(f)

TEXT = """أصل الحروب الصليبية تكمن في التطورات في أوروبا الغربية في وقت سابق من العصور الوسطى، فضلًا عن تدهور حالة الإمبراطورية البيزنطية في الشرق الناجمة عن موجة جديدة من الهجمات التركية المسلمة.

انهيار الإمبراطورية الكارولانجية في أواخر القرن التاسع، جنبًا إلى جنب مع الاستقرار النسبي للحدود المحلية الأوروبية بعد تنصير كلٍ من الفايكنج، والسلاف، والمجريين، قد أنتجت الكثير من الطبقة المسلحة وبروز الطاقات التي كانت في غير محلها قتال بعضهم بعضًا، وإرهاب السكان المحليين. حاولت الكنيسة كبح هذا العنف مع حركات السلام والهدنة مع الله، والتي كانت ناجحة إلى حد ما، لكن طبقة المحاربين كانوا يسعون دائمًا لإيجاد منفذ لمهاراتهم، وأصبح فرض التوسع الإقليمي، أقل جاذبية بالنسبة لقطاعات كبيرة من النبلاء. وكان هناك استثناء واحد هو حروب الاسترداد في إسبانيا و\u200cالبرتغال، فرسان قلعة رباح وفرسان سانتياغو في إسبانيا و\u200cفرسان الهيكل في البرتغال وبعض المرتزقة من أماكن أخرى في أوروبا في مكافحة الوجود الإسلامي. أعطى البابا إسكندر الثاني بركته لمسيحيي إيبيريا الكاثوليك في حروبهم ضد المسلمين.

جردت الحملات الصليبية أيضًا غير محاربة الإسلام والمسلمين إذ كان هدفها في البداية أيضًا محاربة البابا لمخالفيه، فقد جاء الصليبيون من شمال بلدهم الأصلي فرنسا إلى جنوبها لكي يقاتلوا الهراطقة الألبيجنسيين. فمنذ نهاية القرن الحادي عشر بدأت بوادر المقاومة ضد الكنيسة البابوية في روما وسيطرتها على شؤون الحياة الأوروبية، وعند نهاية القرن الثاني عشر ذاعت الأفكار التي أخذ يواقيم الفلورى (Jouchim Flora) يدعو لها، وقد لاقت أفكاره الدينية الذيوع بسرعة ملحوظة. وسار يواقيم على نهج سان برنار الذي زعم أن العالم قد دخل عصر المسيح الدجال الذي يسبق قيام القيامة. وعلى حين اكتفى سان برنار بإدانة كبار الأساقفة على اعتبار أنهم أسرى الشيطان، فإن يواقيم جعل البابوية نفسها هي المسيح الدجال. وقلب بذلك حق وراثة بابا روما للمسيح رأساً على عقب. وحاز شعبية واسعة لدى جميع الفرق المخالفة، ونتج عن أفكاره هذه أن ظهرت عصبة جمعت حولها عدداً ضخماً من الأتباع في جنوب فرنسا تدعى الكارتاريون (Czthari) أي الأطهار أو الألبيجنسيون نسبة إلى بلدة Albi في مقاطعة تولوز والتي كانت معقلاً لهم. وعند نهاية القرن الثاني عشر كان سكان المدن الأثرياء ونبلاء تولوز وبروفانس إما أعضاء في الكنيسة الألبيجانسية وإما من المتعاطفين مع قادتها. وكانت البابوية في روما سنة 1200م ترى في السيطرة الألبيجنسية على جنوب فرنسا سرطان ينهش في جسد العالم المسيحي يجب استئصاله بأي ثمن، لأنها رأت فيها ديانة مختلفة. وتطورت الأحداث بالشكل الذي أدى إلى إعلان بابا روما قرار حرمان على ريموند السادس أمير تولوز، وإباحة أراضيه وأملاك الألبيجنسيين، فتحمس لذلك أمراء شمال فرنسا واندفعوا في حملة صليبية سنة 1209 قضت على الأمراء الأقطاعيين في جنوب فرنسا، واقتسموا إقطاعاتهم.كذلك يمكن أن نصور الغزو الجزئي الذي قام به الأنجلو ـ نورمان لأيرلندا على أنه نمط من أنماط الحروب الصليبية رغم أن ضحاياه كانوا من الكاثوليك.

جاءت بداية الحروب الصليبية في فترة كانت فيها أوروبا قد تنصرت بالكامل تقريبًا بعد اعتناق الفايكينج والسلاف والمجر للمسيحية. فكانت طبقة المحاربين الأوروبيين قد أصبحوا بلا عدو لقتاله، فأصبحوا ينشرون الرعب بين السكان، وتحولوا إلى السرقة وقطع الطرق والقتال في ما بينهم، فكان من الكنيسة أن حاولت التخفيف بمنع ذلك ضد جماعات معينة في فترات معينة من أجل السيطرة على حالة الفوضى القائمة. وفي ذات الوقت أفسح المجال للأوربيين للاهتمام بموضوع الأرض المقدسة التي فتحها المسلمون منذ عدة قرون ولم يتسن للأوربيين الالتفات لها لانشغالهم بالحروب ضد غير المسيحيين من الفايكنج والمجريين الذين كانوا يشكلون المشكلة الأقرب جغرافيًا سابقًا، وكذلك بدأت الكنيسة تلعب دورًا في الحرب الاستردادية في إسبانيا، حيث قام البابا إسكندر الثاني عام 1063 بمباركة المحاربين الذاهبين إلى الأندلس، الأمر الذي لعب دورًا كبيرًا في تكوين فكرة الحرب المقدسة."""

# Split text into paragraphs to preserve structure
paragraphs = [p.strip() for p in TEXT.strip().split("\n\n")]

camel = data["camel_tools_morph_segmentation"]["tokens"]
trankit = data["trankit_native"]["tokens"]

# For each token, produce its segmented form
def camel_segmented(tok):
    if len(tok["morph_segments"]) > 1:
        return "[" + "+".join(tok["morph_segments"]) + "]"
    return tok["word"]

def trankit_segmented(tok):
    if "expanded" in tok:
        parts = [t["text"] for t in tok["expanded"]]
        return "[" + "+".join(parts) + "]"
    return tok["text"]

# We need to map tokens back to paragraphs. Both systems tokenize
# left-to-right across the full text, so we just consume tokens
# and break on paragraph boundaries by checking if we've exhausted
# the words in each paragraph.

# Build word list per paragraph
para_words = []
for para in paragraphs:
    words = para.split()
    para_words.append(words)

lines = []
lines.append("ARABIC TEXT — SEGMENTED OUTPUT")
lines.append("Brackets show where each system split a word: [segment1+segment2]")
lines.append("Unsplit words appear as-is.")
lines.append("=" * 80)

# CAMeL output
lines.append("")
lines.append("╔══════════════════════════════════════════════════════════════╗")
lines.append("║  CAMeL Tools Morphological Segmentation (ATB scheme)       ║")
lines.append("╚══════════════════════════════════════════════════════════════╝")
lines.append("")

idx = 0
for pi, words in enumerate(para_words):
    seg_words = []
    for w in words:
        if idx < len(camel):
            seg_words.append(camel_segmented(camel[idx]))
            idx += 1
        else:
            seg_words.append(w)
    lines.append(" ".join(seg_words))
    lines.append("")

# Trankit output
lines.append("")
lines.append("╔══════════════════════════════════════════════════════════════╗")
lines.append("║  Trankit Native Arabic (tokenize + MWT expansion)          ║")
lines.append("╚══════════════════════════════════════════════════════════════╝")
lines.append("")

idx = 0
for pi, words in enumerate(para_words):
    seg_words = []
    for w in words:
        if idx < len(trankit):
            seg_words.append(trankit_segmented(trankit[idx]))
            idx += 1
        else:
            seg_words.append(w)
    lines.append(" ".join(seg_words))
    lines.append("")

out = "\n".join(lines)
with open("arabic_segmented_text.txt", "w", encoding="utf-8") as f:
    f.write(out)
print("Written to arabic_segmented_text.txt")
