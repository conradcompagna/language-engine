"""
Convert KLUE NER character-level TSV to Trankit word-level BIO format.

Input: Character-level BIO tagging with KLUE tags (PS, LC, OG, DT, QT, TI)
Output: Word-level BIO tagging with standard tags (PERSON, LOC, ORG, DATE, QUANTITY, TIME)
"""

import sys
import os

TAG_MAP = {
    "PS": "PERSON",
    "LC": "LOC",
    "OG": "ORG",
    "DT": "DATE",
    "QT": "QUANTITY",
    "TI": "TIME",
}


def map_tag(tag):
    """Map KLUE tag to standard NER tag."""
    if tag == "O":
        return "O"
    prefix, label = tag.split("-", 1)
    mapped = TAG_MAP.get(label, label)
    return f"{prefix}-{mapped}"


def convert_file(input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    sentences = []
    current_chars = []  # list of (char, tag)
    header_done = False

    for line in lines:
        line = line.rstrip("\n")

        # Skip the first header comment lines (metadata)
        if not header_done:
            if line.startswith("## ") and "\t" not in line.split("##")[1].strip()[:20]:
                # Pure metadata comment like "## 토큰, 레이블 구분자 : \t"
                if any(k in line for k in ["구분자", "주석", "컬럼명"]):
                    continue
            header_done = True

        # Sentence comment line (## klue-ner-v1_train_XXXXX_...)
        if line.startswith("## "):
            # If we have accumulated characters, process them first
            if current_chars:
                sentence = chars_to_words(current_chars)
                if sentence:
                    sentences.append(sentence)
                current_chars = []
            continue

        # Blank line = sentence boundary
        if line.strip() == "":
            if current_chars:
                sentence = chars_to_words(current_chars)
                if sentence:
                    sentences.append(sentence)
                current_chars = []
            continue

        # Character-level token line: char\ttag
        parts = line.split("\t")
        if len(parts) == 2:
            char, tag = parts
            current_chars.append((char, tag.strip()))

    # Handle last sentence
    if current_chars:
        sentence = chars_to_words(current_chars)
        if sentence:
            sentences.append(sentence)

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        for i, sentence in enumerate(sentences):
            for word, tag in sentence:
                f.write(f"{word}\t{tag}\n")
            if i < len(sentences) - 1:
                f.write("\n")

    print(f"Converted {len(sentences)} sentences: {input_path} -> {output_path}")


def chars_to_words(chars):
    """Convert character-level tokens to word-level tokens."""
    words = []
    current_word = []
    current_tags = []

    for char, tag in chars:
        if char == " ":
            # Space = word boundary
            if current_word:
                word_text = "".join(current_word)
                word_tag = map_tag(current_tags[0])  # Use first char's tag
                words.append((word_text, word_tag))
                current_word = []
                current_tags = []
        else:
            current_word.append(char)
            current_tags.append(tag)

    # Last word
    if current_word:
        word_text = "".join(current_word)
        word_tag = map_tag(current_tags[0])
        words.append((word_text, word_tag))

    return words


if __name__ == "__main__":
    ner_dir = os.path.dirname(os.path.abspath(__file__))

    convert_file(
        os.path.join(ner_dir, "klue-ner-v1.1_train.tsv"), os.path.join(ner_dir, "train.bio")
    )
    convert_file(os.path.join(ner_dir, "klue-ner-v1.1_dev.tsv"), os.path.join(ner_dir, "dev.bio"))
