import csv
import json
import math
import os
import re
import shutil
import stat
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


BASE = Path(__file__).resolve().parent
SOURCE_ROOT = BASE / "datasets" / "finerweb_bucketed_fasttext_by_language_sorted_boundaries"
OUTPUT_ROOT = BASE / "datasets" / "finerweb_bucketed_fine_fasttext_by_language"
ZIP_PATH = OUTPUT_ROOT.with_suffix(".zip")
TOP500_MAP = BASE / "revamped_top500_coarse_tag_map.tsv"
LABEL_INVENTORY = BASE / "finerweb_label_inventory.tsv"
SOURCE_FILES = BASE / "finerweb_source_files.tsv"
FASTTEXT_ZIP = BASE / "embeddings" / "wiki-news-300d-1M.vec.zip"
CURRENT_VARIANT = "fine"
CURRENT_METHOD_DESCRIPTION = ""

SPLITS = ("train", "dev", "test", "all")
BIO_RE = re.compile(r"^(O|[BI]-.+)$")
LABEL_RE = re.compile(r"^(?:O|[BI]-[A-Z_]+)$")
TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)?|\d+")
EXPECTED_BUCKETS = {
    "PERSON",
    "ROLE_TITLE",
    "NORP",
    "ORG",
    "LOC",
    "FAC",
    "DATE_TIME",
    "NUMBER",
    "STATISTIC",
    "MONEY",
    "EVENT",
    "WORK_OF_ART",
    "LEGAL_POLITICAL",
    "LANGUAGE",
    "PRODUCT",
    "BIOMED",
    "NATURAL_OBJECT",
    "ACTIVITY_PROCESS",
    "SYMBOL_IDENTIFIER",
    "SYSTEM",
    "GENRE_FORM",
    "CULTURE_RELIGION",
    "CONCEPT",
    "MISC",
}


def remove_tree(path):
    def onexc(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if path.exists():
        shutil.rmtree(path, onexc=onexc)


def norm_label(text):
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*/\s*", " / ", text)
    return text.strip()


def split_original_label(label):
    if "/" in label:
        coarse, fine = label.split("/", 1)
        return norm_label(coarse), norm_label(fine), True
    return norm_label(label), "", False


def text_tokens(text):
    text = norm_label(text)
    text = text.replace("_", " ")
    return TOKEN_RE.findall(text)


def variants(token):
    yielded = set()
    for cand in (token,):
        if cand and cand not in yielded:
            yielded.add(cand)
            yield cand
    if token.endswith("ies") and len(token) > 4:
        cand = token[:-3] + "y"
        if cand not in yielded:
            yielded.add(cand)
            yield cand
    if token.endswith("es") and len(token) > 3:
        cand = token[:-2]
        if cand not in yielded:
            yielded.add(cand)
            yield cand
    if token.endswith("s") and len(token) > 3:
        cand = token[:-1]
        if cand not in yielded:
            yield cand


def load_top500():
    rows = []
    manual = {}
    manual_norm_to_label = {}
    with TOP500_MAP.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            bucket = row["new_main_bucket"].strip()
            label = norm_label(row["coarse_label"])
            freq = int(row["coarse_freq"])
            rows.append({"bucket": bucket, "label": label, "freq": freq})
            manual[label] = bucket
            manual_norm_to_label[label] = row["coarse_label"]
    return rows, manual, manual_norm_to_label


def load_inventory(mode):
    rows = []
    with LABEL_INVENTORY.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            original = row["original_label"]
            count = int(row["count"])
            coarse, fine, has_fine = split_original_label(original)
            if has_fine and mode == "fine":
                mapping_text = fine
                allow_manual_exact = True
            elif has_fine and mode == "fulltag":
                mapping_text = norm_label(f"{coarse} {fine}")
                allow_manual_exact = False
            else:
                mapping_text = coarse
                allow_manual_exact = True
            rows.append(
                {
                    "original_label": original,
                    "count": count,
                    "coarse_label": coarse,
                    "fine_label": fine,
                    "has_fine": has_fine,
                    "mapping_text": mapping_text,
                    "candidate_mode": mode,
                    "allow_manual_exact": allow_manual_exact,
                }
            )
    return rows


def collect_needed_words(top500_rows, inventory_rows):
    needed = set()
    for row in top500_rows:
        for tok in text_tokens(row["label"]):
            needed.update(variants(tok))
    for bucket in EXPECTED_BUCKETS:
        for tok in text_tokens(bucket.lower().replace("_", " ")):
            needed.update(variants(tok))
    for row in inventory_rows:
        for tok in text_tokens(row["mapping_text"]):
            needed.update(variants(tok))
    return needed


def load_needed_fasttext(needed):
    vectors = {}
    needed_bytes = {w.encode("utf-8") for w in needed}
    with zipfile.ZipFile(FASTTEXT_ZIP, "r") as zf:
        names = zf.namelist()
        vec_name = next(name for name in names if name.endswith(".vec"))
        with zf.open(vec_name, "r") as f:
            header = f.readline()
            for line in f:
                word, _, rest = line.partition(b" ")
                if word not in needed_bytes:
                    continue
                arr = np.fromstring(rest.decode("ascii"), sep=" ", dtype=np.float32)
                if arr.size:
                    norm = np.linalg.norm(arr)
                    if norm:
                        vectors[word.decode("utf-8")] = arr / norm
    return vectors


def phrase_vector(text, vectors):
    toks = text_tokens(text)
    found = []
    for tok in toks:
        vec = None
        for cand in variants(tok):
            vec = vectors.get(cand)
            if vec is not None:
                break
        if vec is not None:
            found.append(vec)
    if not found:
        return None, 0, len(toks)
    vec = np.mean(found, axis=0)
    norm = np.linalg.norm(vec)
    if not norm:
        return None, len(found), len(toks)
    return vec / norm, len(found), len(toks)


def build_bucket_centroids(top500_rows, vectors):
    weighted = defaultdict(list)
    anchor_summary = {}
    for row in top500_rows:
        vec, hits, toks = phrase_vector(row["label"], vectors)
        if vec is None:
            continue
        weight = math.log1p(row["freq"])
        weighted[row["bucket"]].append((vec, weight, row["label"], row["freq"], hits, toks))

    centroids = {}
    for bucket, items in weighted.items():
        total = sum(weight for _, weight, *_ in items)
        centroid = sum(vec * weight for vec, weight, *_ in items) / total
        norm = np.linalg.norm(centroid)
        if norm:
            centroids[bucket] = centroid / norm
        anchor_summary[bucket] = {
            "anchors_with_vectors": len(items),
            "anchor_freq_with_vectors": sum(freq for _, _, _, freq, _, _ in items),
        }
    return centroids, anchor_summary


def best_bucket(vec, centroids):
    scored = sorted(
        ((float(np.dot(vec, centroid)), bucket) for bucket, centroid in centroids.items()),
        reverse=True,
    )
    best_score, best = scored[0]
    second_score, second = scored[1] if len(scored) > 1 else (0.0, "")
    return best, best_score, second, second_score, best_score - second_score


def build_label_map(inventory_rows, manual_map, centroids, vectors):
    label_map = {}
    for row in inventory_rows:
        original = row["original_label"]
        mapping_text = row["mapping_text"]
        exact = manual_map.get(mapping_text) if row["allow_manual_exact"] else None
        if exact:
            vec, hits, toks = phrase_vector(mapping_text, vectors)
            label_map[original] = {
                **row,
                "new_main_bucket": exact,
                "assignment_source": "manual_top500_fine_exact"
                if row["has_fine"]
                else "manual_top500_no_fine",
                "vector_hits": hits,
                "vector_tokens": toks,
                "similarity": "",
                "second_bucket": "",
                "second_similarity": "",
                "margin": "",
            }
            continue

        vec, hits, toks = phrase_vector(mapping_text, vectors)
        if vec is None:
            label_map[original] = {
                **row,
                "new_main_bucket": "MISC",
                "assignment_source": "no_vector_misc",
                "vector_hits": hits,
                "vector_tokens": toks,
                "similarity": "",
                "second_bucket": "",
                "second_similarity": "",
                "margin": "",
            }
            continue

        bucket, score, second, second_score, margin = best_bucket(vec, centroids)
        if row["has_fine"] and row["candidate_mode"] == "fulltag":
            source = "fulltag_fasttext"
        elif row["has_fine"]:
            source = "fine_fasttext"
        else:
            source = "coarse_fasttext"
        label_map[original] = {
            **row,
            "new_main_bucket": bucket,
            "assignment_source": source,
            "vector_hits": hits,
            "vector_tokens": toks,
            "similarity": f"{score:.6f}",
            "second_bucket": second,
            "second_similarity": f"{second_score:.6f}",
            "margin": f"{margin:.6f}",
        }
    return label_map


def write_label_map(label_map):
    fields = [
        "new_main_bucket",
        "original_label",
        "count",
        "assignment_source",
        "candidate_mode",
        "mapping_text",
        "coarse_label",
        "fine_label",
        "has_fine",
        "vector_hits",
        "vector_tokens",
        "similarity",
        "second_bucket",
        "second_similarity",
        "margin",
    ]
    out = OUTPUT_ROOT / "fine_tag_fasttext_bucket_map.tsv"
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for row in sorted(label_map.values(), key=lambda r: (-r["count"], r["original_label"])):
            writer.writerow({field: row[field] for field in fields})
    return out


def write_anchor_summary(top500_rows, anchor_summary):
    totals = Counter()
    counts = Counter()
    for row in top500_rows:
        totals[row["bucket"]] += row["freq"]
        counts[row["bucket"]] += 1
    path = OUTPUT_ROOT / "bucket_anchor_summary.tsv"
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(
            [
                "bucket",
                "manual_anchor_count",
                "manual_anchor_freq",
                "anchors_with_vectors",
                "anchor_freq_with_vectors",
            ]
        )
        for bucket in sorted(counts):
            data = anchor_summary.get(bucket, {})
            writer.writerow(
                [
                    bucket,
                    counts[bucket],
                    totals[bucket],
                    data.get("anchors_with_vectors", 0),
                    data.get("anchor_freq_with_vectors", 0),
                ]
            )
    return path


def parse_original_bio(original_bio):
    if original_bio == "O":
        return "O", ""
    prefix, label = original_bio.split("-", 1)
    return prefix, label


def convert_split(lang_dir, out_lang_dir, lang, split, label_map):
    src = lang_dir / f"{split}.original_vs_bucket.tsv"
    bio_out = out_lang_dir / f"{split}.bio"
    side_out = out_lang_dir / f"{split}.original_vs_bucket.tsv"

    sentences = 0
    tokens = 0
    entity_tokens = Counter()
    entity_spans = Counter()
    original_bucket_counts = Counter()
    source_counts = Counter()

    with (
        src.open("r", encoding="utf-8", newline="") as fin,
        bio_out.open("w", encoding="utf-8", newline="") as fbio,
        side_out.open("w", encoding="utf-8", newline="") as fside,
    ):
        header = fin.readline().rstrip("\n").split("\t")
        if header[:2] != ["token", "original_bio"]:
            raise ValueError(f"Unexpected side-by-side header in {src}: {header}")
        side_writer = csv.writer(fside, delimiter="\t", lineterminator="\n")
        side_writer.writerow(
            ["token", "original_bio", "mapping_text", "assignment_source", "bucket_bio"]
        )
        last_blank = False
        for lineno, raw in enumerate(fin, 2):
            line = raw.rstrip("\n")
            if line == "":
                fbio.write("\n")
                fside.write("\n")
                sentences += 1
                last_blank = True
                continue
            parts = line.split("\t")
            if len(parts) != len(header):
                raise ValueError(
                    f"Bad TSV row in {src}:{lineno}: expected {len(header)} columns, got {len(parts)}"
                )
            row = dict(zip(header, parts))
            token = row["token"]
            original_bio = row["original_bio"]
            if not BIO_RE.match(original_bio):
                raise ValueError(f"Bad original BIO in {src}: {original_bio!r}")
            if original_bio == "O":
                bucket_bio = "O"
                mapping_text = "_"
                assignment_source = "_"
            else:
                prefix, original_label = parse_original_bio(original_bio)
                mapped = label_map.get(original_label)
                if mapped is None:
                    mapped = label_map.get(original_label.strip())
                if mapped is None:
                    mapped = label_map.get(norm_label(original_label))
                if mapped is None:
                    raise KeyError(f"Original label missing from map: {original_label}")
                bucket = mapped["new_main_bucket"]
                bucket_bio = f"{prefix}-{bucket}"
                mapping_text = mapped["mapping_text"]
                assignment_source = mapped["assignment_source"]
                entity_tokens[bucket] += 1
                if prefix == "B":
                    entity_spans[bucket] += 1
                    original_bucket_counts[
                        (mapped["original_label"], bucket, mapping_text, assignment_source)
                    ] += 1
                    source_counts[assignment_source] += 1
            fbio.write(f"{token}\t{bucket_bio}\n")
            side_writer.writerow([token, original_bio, mapping_text, assignment_source, bucket_bio])
            tokens += 1
            last_blank = False
        if not last_blank:
            sentences += 1

    return {
        "split": split,
        "sentences": sentences,
        "tokens": tokens,
        "entity_token_counts": dict(entity_tokens),
        "entity_span_counts": dict(entity_spans),
        "original_bucket_counts": original_bucket_counts,
        "source_counts": dict(source_counts),
    }


def convert_datasets(label_map, method_description):
    langs = sorted(p.name for p in SOURCE_ROOT.iterdir() if p.is_dir())
    root_report = {
        "method": method_description,
        "variant": CURRENT_VARIANT,
        "source_dataset": str(SOURCE_ROOT),
        "output_dataset": str(OUTPUT_ROOT),
        "languages": langs,
        "language_reports": {},
    }

    if SOURCE_FILES.exists():
        shutil.copy2(SOURCE_FILES, OUTPUT_ROOT / "source_files.tsv")

    global_original_counts = Counter()
    global_label_token_counts = Counter()
    global_label_span_counts = Counter()
    global_assignment_sources = Counter()

    for lang in langs:
        src_lang_dir = SOURCE_ROOT / lang
        out_lang_dir = OUTPUT_ROOT / lang
        out_lang_dir.mkdir(parents=True)
        split_reports = []
        lang_original_counts = Counter()
        lang_token_counts = Counter()
        lang_span_counts = Counter()
        lang_assignment_sources = Counter()

        for split in SPLITS:
            report = convert_split(src_lang_dir, out_lang_dir, lang, split, label_map)
            split_reports.append(report)
            if split == "all":
                lang_original_counts.update(report["original_bucket_counts"])
                lang_token_counts.update(report["entity_token_counts"])
                lang_span_counts.update(report["entity_span_counts"])
                lang_assignment_sources.update(report["source_counts"])
                global_original_counts.update(report["original_bucket_counts"])
                global_label_token_counts.update(report["entity_token_counts"])
                global_label_span_counts.update(report["entity_span_counts"])
                global_assignment_sources.update(report["source_counts"])

        write_lang_reports(
            out_lang_dir,
            lang,
            split_reports,
            lang_original_counts,
            lang_token_counts,
            lang_span_counts,
            lang_assignment_sources,
        )
        root_report["language_reports"][lang] = {
            "sentences": next(r["sentences"] for r in split_reports if r["split"] == "all"),
            "tokens": next(r["tokens"] for r in split_reports if r["split"] == "all"),
            "entity_spans": sum(lang_span_counts.values()),
            "entity_tokens": sum(lang_token_counts.values()),
            "assignment_sources": dict(lang_assignment_sources),
        }

    write_root_reports(
        root_report,
        global_original_counts,
        global_label_token_counts,
        global_label_span_counts,
        global_assignment_sources,
    )
    return root_report


def write_lang_reports(
    out_lang_dir, lang, split_reports, original_counts, token_counts, span_counts, source_counts
):
    with (out_lang_dir / "split_summary.tsv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["split", "sentences", "tokens", "entity_spans", "entity_tokens"])
        for report in split_reports:
            writer.writerow(
                [
                    report["split"],
                    report["sentences"],
                    report["tokens"],
                    sum(report["entity_span_counts"].values()),
                    sum(report["entity_token_counts"].values()),
                ]
            )

    with (out_lang_dir / "label_token_counts.tsv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["new_main_bucket", "entity_token_count", "entity_span_count"])
        for bucket in sorted(set(token_counts) | set(span_counts)):
            writer.writerow([bucket, token_counts[bucket], span_counts[bucket]])

    with (out_lang_dir / "original_label_bucket_counts.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(
            ["original_label", "new_main_bucket", "mapping_text", "assignment_source", "span_count"]
        )
        for (label, bucket, mapping_text, source), count in sorted(
            original_counts.items(), key=lambda x: (-x[1], x[0])
        ):
            writer.writerow([label, bucket, mapping_text, source, count])

    report = {
        "lang": lang,
        "splits": {
            r["split"]: {
                "sentences": r["sentences"],
                "tokens": r["tokens"],
                "entity_spans": sum(r["entity_span_counts"].values()),
                "entity_tokens": sum(r["entity_token_counts"].values()),
            }
            for r in split_reports
        },
        "assignment_sources_all": dict(source_counts),
    }
    (out_lang_dir / "dataset_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_lang_dir / "README.md").write_text(
        f"# fiNERweb fine-tag fastText NER BIO dataset: {lang}\n\n"
        "BIO labels use the final high-level bucket names. The side-by-side TSV keeps the original BIO label, "
        "the fine/coarse text used for remapping, the assignment source, and the new bucket BIO label.\n",
        encoding="utf-8",
    )


def write_root_reports(root_report, original_counts, token_counts, span_counts, source_counts):
    with (OUTPUT_ROOT / "label_token_counts.tsv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["new_main_bucket", "entity_token_count", "entity_span_count"])
        for bucket in sorted(set(token_counts) | set(span_counts)):
            writer.writerow([bucket, token_counts[bucket], span_counts[bucket]])

    with (OUTPUT_ROOT / "original_label_bucket_counts.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(
            ["original_label", "new_main_bucket", "mapping_text", "assignment_source", "span_count"]
        )
        for (label, bucket, mapping_text, source), count in sorted(
            original_counts.items(), key=lambda x: (-x[1], x[0])
        ):
            writer.writerow([label, bucket, mapping_text, source, count])

    with (OUTPUT_ROOT / "assignment_source_summary.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["assignment_source", "span_count"])
        for source, count in sorted(source_counts.items(), key=lambda x: (-x[1], x[0])):
            writer.writerow([source, count])

    totals = Counter()
    for lang_report in root_report["language_reports"].values():
        totals["sentences"] += lang_report["sentences"]
        totals["tokens"] += lang_report["tokens"]
        totals["entity_spans"] += lang_report["entity_spans"]
        totals["entity_tokens"] += lang_report["entity_tokens"]
    root_report["totals"] = dict(totals)
    root_report["assignment_sources_all"] = dict(source_counts)
    (OUTPUT_ROOT / "dataset_report.json").write_text(
        json.dumps(root_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_ROOT / "README.md").write_text(
        f"# fiNERweb {CURRENT_VARIANT} fastText bucketed Trankit NER BIO datasets by language\n\n"
        f"{CURRENT_METHOD_DESCRIPTION}\n\n"
        "BIO labels use the final high-level bucket names. Each language folder includes side-by-side TSV files "
        "with original BIO labels and new bucket BIO labels.\n",
        encoding="utf-8",
    )


def validate_dataset():
    issues = []
    langs = sorted(p.name for p in OUTPUT_ROOT.iterdir() if p.is_dir())
    for lang in langs:
        for split in SPLITS:
            bio = OUTPUT_ROOT / lang / f"{split}.bio"
            side = OUTPUT_ROOT / lang / f"{split}.original_vs_bucket.tsv"
            bio_rows = []
            with bio.open("r", encoding="utf-8", newline="") as f:
                for lineno, line in enumerate(f, 1):
                    line = line.rstrip("\n")
                    if not line:
                        bio_rows.append(("", ""))
                        continue
                    parts = line.split("\t")
                    if len(parts) != 2:
                        issues.append([lang, split, str(bio), lineno, "bad_bio_columns", line[:80]])
                        continue
                    if not LABEL_RE.match(parts[1]):
                        issues.append([lang, split, str(bio), lineno, "bad_bio_label", parts[1]])
                    if parts[1] != "O":
                        bucket = parts[1].split("-", 1)[1]
                        if bucket not in EXPECTED_BUCKETS:
                            issues.append(
                                [lang, split, str(bio), lineno, "unexpected_bucket", bucket]
                            )
                    bio_rows.append(tuple(parts))

            side_rows = []
            with side.open("r", encoding="utf-8", newline="") as f:
                reader = csv.reader(f, delimiter="\t")
                header = next(reader, [])
                if header != [
                    "token",
                    "original_bio",
                    "mapping_text",
                    "assignment_source",
                    "bucket_bio",
                ]:
                    issues.append([lang, split, str(side), 1, "bad_side_header", "\t".join(header)])
                for lineno, parts in enumerate(reader, 2):
                    if not parts:
                        side_rows.append(("", ""))
                        continue
                    if len(parts) != 5:
                        issues.append(
                            [
                                lang,
                                split,
                                str(side),
                                lineno,
                                "bad_side_columns",
                                "\t".join(parts)[:80],
                            ]
                        )
                        continue
                    token, original_bio, _, _, bucket_bio = parts
                    if not BIO_RE.match(original_bio):
                        issues.append(
                            [lang, split, str(side), lineno, "bad_original_bio", original_bio]
                        )
                    if not LABEL_RE.match(bucket_bio):
                        issues.append(
                            [lang, split, str(side), lineno, "bad_side_bucket", bucket_bio]
                        )
                    side_rows.append((token, bucket_bio))

            if bio_rows != side_rows:
                issues.append(
                    [
                        lang,
                        split,
                        str(side),
                        0,
                        "bio_side_sequence_mismatch",
                        f"{len(bio_rows)} vs {len(side_rows)}",
                    ]
                )

            prev = "O"
            for idx, (_, label) in enumerate(bio_rows, 1):
                if not label or label == "O":
                    prev = "O"
                    continue
                pref, bucket = label.split("-", 1)
                if pref == "I" and prev not in {f"B-{bucket}", f"I-{bucket}"}:
                    issues.append([lang, split, str(bio), idx, "invalid_i_transition", label])
                prev = label

    issue_path = OUTPUT_ROOT / "archive_health_issues.tsv"
    with issue_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["lang", "split", "file", "line", "issue", "detail"])
        writer.writerows(issues)
    report = {
        "languages": langs,
        "files_checked": len(langs) * len(SPLITS) * 2,
        "issue_count": len(issues),
        "issues_tsv": str(issue_path),
    }
    (OUTPUT_ROOT / "archive_health_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def make_zip():
    tmp = ZIP_PATH.with_suffix(".zip.tmp")
    if tmp.exists():
        tmp.unlink()
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(OUTPUT_ROOT.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(OUTPUT_ROOT.parent).as_posix())
    os.replace(tmp, ZIP_PATH)
    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        return {
            "zip": str(ZIP_PATH),
            "members": len(zf.namelist()),
            "size_bytes": ZIP_PATH.stat().st_size,
        }


def build_variant(mode, output_root, top500_rows, manual_map, centroids, anchor_summary, vectors):
    global OUTPUT_ROOT, ZIP_PATH, CURRENT_VARIANT, CURRENT_METHOD_DESCRIPTION

    OUTPUT_ROOT = output_root
    ZIP_PATH = OUTPUT_ROOT.with_suffix(".zip")
    CURRENT_VARIANT = mode
    if mode == "fine":
        CURRENT_METHOD_DESCRIPTION = (
            "This version remaps original labels by the fine-grained tag text. For labels containing `/`, "
            "the text after the first slash is embedded and compared with bucket centroids built from the top-500 "
            "manual coarse-tag map. Exact top-500 matches on the fine tag win before vector similarity. Labels "
            "without a fine tag use the manual top-500 bucket when present, otherwise fastText over the label text. "
            "Labels with no usable vector are assigned to MISC."
        )
    else:
        CURRENT_METHOD_DESCRIPTION = (
            "This version remaps original labels by the full concatenated tag text. For labels containing `/`, "
            "the coarse text before the first slash and the fine text after it are concatenated, embedded, and "
            "compared with bucket centroids built from the top-500 manual coarse-tag map. Labels without a fine tag "
            "use the manual top-500 bucket when present, otherwise fastText over the label text. Labels with no "
            "usable vector are assigned to MISC."
        )

    inventory_rows = load_inventory(mode)
    label_map = build_label_map(inventory_rows, manual_map, centroids, vectors)

    remove_tree(OUTPUT_ROOT)
    OUTPUT_ROOT.mkdir(parents=True)
    write_label_map(label_map)
    write_anchor_summary(top500_rows, anchor_summary)
    dataset_report = convert_datasets(label_map, CURRENT_METHOD_DESCRIPTION)
    health = validate_dataset()
    zip_info = make_zip()

    summary = {
        "variant": mode,
        "output_root": str(OUTPUT_ROOT),
        "zip": zip_info,
        "label_count": len(label_map),
        "assignment_source_counts_by_label": dict(
            Counter(row["assignment_source"] for row in label_map.values())
        ),
        "assignment_source_counts_by_span": dataset_report["assignment_sources_all"],
        "health": health,
    }
    (OUTPUT_ROOT / "build_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main():
    top500_rows, manual_map, _ = load_top500()
    fine_inventory = load_inventory("fine")
    fulltag_inventory = load_inventory("fulltag")
    needed = collect_needed_words(top500_rows, fine_inventory + fulltag_inventory)
    vectors = load_needed_fasttext(needed)
    centroids, anchor_summary = build_bucket_centroids(top500_rows, vectors)
    summaries = [
        build_variant(
            "fine",
            BASE / "datasets" / "finerweb_bucketed_fine_fasttext_by_language",
            top500_rows,
            manual_map,
            centroids,
            anchor_summary,
            vectors,
        ),
        build_variant(
            "fulltag",
            BASE / "datasets" / "finerweb_bucketed_fulltag_fasttext_by_language",
            top500_rows,
            manual_map,
            centroids,
            anchor_summary,
            vectors,
        ),
    ]
    print(json.dumps({"variants": summaries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
