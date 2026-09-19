# ud_overlay.py
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional, Tuple


# ----------------------------
# Myanmar detection utilities
# ----------------------------

_MYANMAR_BLOCK_START = 0x1000
_MYANMAR_BLOCK_END   = 0x109F

# Common Myanmar punctuation in chronicle-style texts / OCR streams.
# (You can add more if needed.)
_MY_PUNCT = {
    "\u104a",  # Myanmar comma: "၊"
    "\u104b",  # Myanmar period: "။"
    "\u104c",  # Myanmar locative: "၌" (sometimes treated as punctuation)
    "\u104d",  # Myanmar "completed": "၍" (often treated as linker)
    "\u104e",  # Myanmar "aforementioned": "၎"
}

# ASCII punctuation (only if you decide to keep them)
_ASCII_PUNCT = set(".,;:!?()[]{}\"'—-…")

_WHITESPACE_BOUNDARY_JS = Path(__file__).with_name("whitespace_boundaries.js")

# ----------------------------
# POS/DEP scoring for island head selection
# ----------------------------

# Content POS ranked by "headworthiness" (higher = more likely to be head)
_CONTENT_POS_ORDER = [
    "VERB", "NOUN", "PROPN",
    "ADJ", "ADV", "NUM", "PRON",
    "SCONJ", "CCONJ",
    "ADP", "PART",
    "PUNCT", "SYM"
]

# Dependency relations ranked by "headworthiness"
_DEP_ORDER = [
    "root", "acl", "obl", "compound",
    "nmod", "amod", "advmod", "nummod",
    "aux", "mark", "case", "punct"
]

_CONTENT_POS_SCORE = {p: len(_CONTENT_POS_ORDER) - i for i, p in enumerate(_CONTENT_POS_ORDER)}
_DEP_SCORE = {d: len(_DEP_ORDER) - i for i, d in enumerate(_DEP_ORDER)}

# Function words should not be island heads
_FUNCTION_POS = {"ADP", "PART", "AUX", "CCONJ", "SCONJ", "PUNCT", "SYM"}

# NER label to UPOS mapping
_NER_TO_UPOS = {
    "PNAME": "PROPN",
    "LOC": "PROPN",
    "ORG": "PROPN",
    "RACE": "PROPN",
    "TIME": "NOUN",
    "NUM": "NUM",
    "NE": "PROPN",
}


def _extract_ner_spans_from_fills(
    dict_fills: Optional[List[Dict[str, Any]]],
    n_segments: int,
) -> List[Tuple[int, int, str]]:
    """
    Extract contiguous NER spans from dict_fills.

    Returns list of (start_idx, end_idx, label) tuples where indices are segment indices.
    Consecutive segments with the same ner_label are merged into one span.
    """
    if not dict_fills:
        return []

    spans: List[Tuple[int, int, str]] = []
    current_start: Optional[int] = None
    current_label: Optional[str] = None

    for i in range(n_segments):
        fill = dict_fills[i] if i < len(dict_fills) else None
        ner_label = (fill or {}).get("ner_label")

        if ner_label:
            if current_label == ner_label and current_start is not None:
                # Continue the current span
                pass
            else:
                # Start a new span (close previous if exists)
                if current_start is not None and current_label:
                    spans.append((current_start, i, current_label))
                current_start = i
                current_label = ner_label
        else:
            # Not an NER segment - close current span if exists
            if current_start is not None and current_label:
                spans.append((current_start, i, current_label))
            current_start = None
            current_label = None

    # Close final span if still open
    if current_start is not None and current_label:
        spans.append((current_start, n_segments, current_label))

    return spans


def _collapse_ner_spans_for_parsing(
    segments: List[str],
    dict_fills: Optional[List[Dict[str, Any]]],
    keep_fn,
    allow_ascii_punct: bool = False,
) -> Tuple[List[str], List[List[int]], List[Optional[str]]]:
    """
    Collapse NER spans into single tokens for dependency parsing.

    Returns:
        - collapsed_words: list of tokens where NER spans are joined
        - collapsed_to_seg: list mapping each collapsed token to its original segment indices
        - collapsed_ner_labels: list of NER labels (or None) for each collapsed token
    """
    ner_spans = _extract_ner_spans_from_fills(dict_fills, len(segments))

    # Build a set of segment indices that are inside NER spans
    ner_covered: Dict[int, Tuple[int, int, str]] = {}  # seg_idx -> (span_start, span_end, label)
    for start, end, label in ner_spans:
        for i in range(start, end):
            ner_covered[i] = (start, end, label)

    collapsed_words: List[str] = []
    collapsed_to_seg: List[List[int]] = []
    collapsed_ner_labels: List[Optional[str]] = []

    i = 0
    while i < len(segments):
        if i in ner_covered:
            span_start, span_end, label = ner_covered[i]
            if i == span_start:
                # Start of NER span - collapse all tokens in span
                span_tokens = segments[span_start:span_end]
                # Join tokens without spaces (Burmese doesn't use spaces)
                collapsed_text = "".join(span_tokens)
                collapsed_words.append(collapsed_text)
                collapsed_to_seg.append(list(range(span_start, span_end)))
                collapsed_ner_labels.append(label)
                i = span_end
            else:
                # Should not happen if we process in order, but skip
                i += 1
        else:
            # Regular token - keep as-is
            collapsed_words.append(segments[i])
            collapsed_to_seg.append([i])
            collapsed_ner_labels.append(None)
            i += 1

    return collapsed_words, collapsed_to_seg, collapsed_ner_labels


def _is_myanmar_char(ch: str) -> bool:
    o = ord(ch)
    return _MYANMAR_BLOCK_START <= o <= _MYANMAR_BLOCK_END


def is_myanmar_token(tok: str) -> bool:
    """
    True if token contains at least one Myanmar-block char.
    """
    for ch in tok:
        if _is_myanmar_char(ch):
            return True
    return False


def is_allowed_punct(tok: str, allow_ascii_punct: bool = False) -> bool:
    if tok in _MY_PUNCT:
        return True
    if allow_ascii_punct and tok in _ASCII_PUNCT:
        return True
    return False


def default_ud_keep_fn(tok: str) -> bool:
    """
    Default filter: keep tokens that are Myanmar-script OR Myanmar punctuation.
    """
    return is_myanmar_token(tok) or is_allowed_punct(tok, allow_ascii_punct=False)


# ----------------------------
# UD overlay core
# ----------------------------

@dataclass
class UDOverlay:
    ok: bool
    tokens: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    roots: List[int]
    ents: List[Dict[str, Any]]
    sentences: List[List[int]]
    # mapping from UD-doc token index -> original segment index
    doc2seg: List[int]
    # mapping from original segment index -> UD-doc token index, or -1 if dropped
    seg2doc: List[int]
    error: Optional[str] = None


class UDParser:
    """
    Wrap a spaCy model that contains a dependency parser.
    This module assumes you are supplying pre-segmented tokens (segments).

    Key design goal:
      - Parse only kept tokens (Myanmar + Myanmar punct).
      - Return edges/tokens indexed by ORIGINAL segment indices so the frontend can
        draw over spans without renumbering the paragraph.
    """

    def __init__(self, model_path: str):
        try:
            import spacy  # type: ignore
            from spacy.tokens import Doc  # type: ignore
        except Exception as e:
            raise RuntimeError(f"spaCy not available: {type(e).__name__}: {e}")

        self._spacy = spacy
        self._Doc = Doc
        self.model_path = model_path
        self.nlp = spacy.load(model_path)
        # allow long texts if you later feed paragraph-scale input
        self.nlp.max_length = max(getattr(self.nlp, "max_length", 1_000_000), 2_000_000)

        # Add dictionary POS constraint component after morphologizer
        try:
            import dict_pos_override  # registers the factory
            if "morphologizer" in self.nlp.pipe_names and "dict_pos_override" not in self.nlp.pipe_names:
                self.nlp.add_pipe("dict_pos_override", after="morphologizer")
                print("[INFO] dict_pos_override component added to pipeline")
        except Exception as e:
            print(f"[WARN] dict_pos_override not loaded: {e}")

    def build_overlay(
        self,
        segments: List[str],
        keep_fn=default_ud_keep_fn,
        allow_ascii_punct: bool = False,
        attach_dropped_to: str = "none",  # "none" | "nearest_left" | "nearest_right"
        dict_fills: Optional[List[Dict[str, Any]]] = None,  # Optional pre-computed dictionary fills per segment
        original_text: Optional[str] = None,  # Original text (preserved for compatibility, not used)
        pos_override: bool = True,  # Toggle for dictionary POS override (dict_pos_override pipe)
        precomputed_ner_ents: Optional[List[Dict[str, Any]]] = None,  # NER ents aligned to segments
        collapse_ner_spans: bool = False,  # Collapse NER spans into single tokens for parsing
    ) -> UDOverlay:
        """
        segments: original segmentation tokens from your pipeline

        keep_fn: token filter. Should return True for tokens included in UD parsing.
        allow_ascii_punct: if True, ASCII punctuation tokens may be kept by is_allowed_punct.
        attach_dropped_to:
          - "none": dropped tokens have no edges (frontend will simply see gaps)
          - "nearest_left": dropped token i gets a synthetic edge to nearest kept token to the left
          - "nearest_right": similarly to right
        dict_fills: Optional list of dictionary fill data (one per segment) from newserver.
                   Each element should be {"mode": "...", "fills": [...], ...} or None.
                   If provided, these will be set on token._.dict_fills before the pipeline runs,
                   allowing dict_pos_override to use pre-computed dictionary assignments.
        precomputed_ner_ents: Optional list of NER spans aligned to segments (start/end/label).
        collapse_ner_spans: If True, NER entity spans are collapsed into single tokens for parsing.
                          UI still maps back to original segment indices.
        """

        try:
            doc2seg: List[int] = []
            seg2doc: List[int] = [-1] * len(segments)

            def _keep(tok: str) -> bool:
                if is_allowed_punct(tok, allow_ascii_punct=allow_ascii_punct):
                    return True
                return bool(keep_fn(tok))

            tokens_out: List[Dict[str, Any]] = []
            edges_out: List[Dict[str, Any]] = []
            roots: List[int] = []
            ents_out: List[Dict[str, Any]] = []
            sentences_out: List[List[int]] = []

            sent_end = "\u104b"  # Myanmar period "။"
            sent_spans: List[Tuple[int, int]] = []
            start = 0
            for i, tok in enumerate(segments):
                if tok == sent_end:
                    sent_spans.append((start, i + 1))
                    start = i + 1
            if start < len(segments):
                sent_spans.append((start, len(segments)))

            ner_label_by_seg: Dict[int, str] = {}
            if precomputed_ner_ents:
                for ent in precomputed_ner_ents:
                    s = ent.get("start")
                    e = ent.get("end")
                    label = ent.get("label", "") or ""
                    if not isinstance(s, int) or not isinstance(e, int) or not label:
                        continue
                    s = max(0, s)
                    e = min(len(segments), e)
                    if e <= s:
                        continue
                    for i in range(s, e):
                        if i not in ner_label_by_seg:
                            ner_label_by_seg[i] = label

            elif dict_fills is not None:
                for i in range(min(len(dict_fills), len(segments))):
                    label = (dict_fills[i] or {}).get("ner_label")
                    if label and i not in ner_label_by_seg:
                        ner_label_by_seg[i] = label

            def _get_precomputed_ner_label(seg_indices: List[int]) -> Optional[str]:
                for seg_idx in seg_indices:
                    label = ner_label_by_seg.get(seg_idx)
                    if label:
                        return label
                return None

            ner_spans_in_doc: List[Tuple[int, int, str]] = []
            if precomputed_ner_ents:
                for ent in precomputed_ner_ents:
                    s = ent.get("start")
                    e = ent.get("end")
                    label = ent.get("label", "") or ""
                    if not label:
                        continue
                    if not isinstance(s, int) or not isinstance(e, int):
                        continue
                    s = max(0, s)
                    e = min(len(segments), e)
                    if e <= s:
                        continue
                    ner_spans_in_doc.append((s, e, label))
            elif dict_fills is not None:
                ner_spans_in_doc = _extract_ner_spans_from_fills(dict_fills, len(segments))

            kept_words: List[str] = []
            doc2seg_local: List[int] = []
            for si, tok in enumerate(segments):
                if _keep(tok):
                    doc2seg_local.append(si)
                    kept_words.append(tok)

            if not kept_words:
                return UDOverlay(
                    ok=True,
                    tokens=[],
                    edges=[],
                    roots=[],
                    ents=[],
                    sentences=[],
                    doc2seg=[],
                    seg2doc=seg2doc,
                    error=None,
                )

            # Optionally collapse NER spans for parsing
            collapsed_to_orig: List[List[int]] = [[si] for si in doc2seg_local]
            collapsed_ner_labels: List[Optional[str]] = [None] * len(kept_words)
            if collapse_ner_spans and ner_spans_in_doc:
                ner_covered: Dict[int, Tuple[int, int, str]] = {}
                for span_start, span_end, label in ner_spans_in_doc:
                    for idx in range(span_start, span_end):
                        ner_covered[idx] = (span_start, span_end, label)

                new_kept_words: List[str] = []
                new_collapsed_to_orig: List[List[int]] = []
                new_collapsed_ner_labels: List[Optional[str]] = []
                processed_spans: set = set()

                i = 0
                while i < len(kept_words):
                    seg_idx = doc2seg_local[i]
                    if seg_idx in ner_covered:
                        span_start, span_end, label = ner_covered[seg_idx]
                        span_key = (span_start, span_end)
                        if span_key not in processed_spans:
                            processed_spans.add(span_key)
                            span_seg_indices: List[int] = []
                            span_texts: List[str] = []
                            j = i
                            while j < len(kept_words):
                                sj = doc2seg_local[j]
                                if sj >= span_end:
                                    break
                                if sj in ner_covered and ner_covered[sj][0] == span_start:
                                    span_seg_indices.append(sj)
                                    span_texts.append(kept_words[j])
                                j += 1
                            collapsed_text = "".join(span_texts)
                            new_kept_words.append(collapsed_text)
                            new_collapsed_to_orig.append(span_seg_indices)
                            new_collapsed_ner_labels.append(label)
                            i = j
                        else:
                            i += 1
                    else:
                        new_kept_words.append(kept_words[i])
                        new_collapsed_to_orig.append([seg_idx])
                        new_collapsed_ner_labels.append(None)
                        i += 1

                kept_words = new_kept_words
                collapsed_to_orig = new_collapsed_to_orig
                collapsed_ner_labels = new_collapsed_ner_labels

            for doc_idx, seg_indices in enumerate(collapsed_to_orig):
                for si in seg_indices:
                    seg2doc[si] = doc_idx

            spaces = [True] * (len(kept_words) - 1) + [False]
            doc = self._Doc(self.nlp.vocab, words=kept_words, spaces=spaces)

            # Set pre-computed dictionary fills on tokens if provided
            if dict_fills is not None:
                for local_idx, seg_indices in enumerate(collapsed_to_orig):
                    first_seg_idx = seg_indices[0]
                    if first_seg_idx < len(dict_fills) and dict_fills[first_seg_idx] is not None:
                        doc[local_idx]._.dict_fills = dict_fills[first_seg_idx]
                    ner_label = collapsed_ner_labels[local_idx] or _get_precomputed_ner_label(seg_indices)
                    if ner_label:
                        doc[local_idx]._.ner_locked = True

            # Conditionally disable dict_pos_override if pos_override is False
            pos_override_disabled = False
            if not pos_override and self.nlp.has_pipe("dict_pos_override"):
                self.nlp.disable_pipe("dict_pos_override")
                pos_override_disabled = True

            try:
                doc = self.nlp(doc)
            finally:
                if pos_override_disabled:
                    self.nlp.enable_pipe("dict_pos_override")

            # Apply NER-based POS override for precomputed NER labels
            for local_idx, seg_indices in enumerate(collapsed_to_orig):
                ner_label = collapsed_ner_labels[local_idx] or _get_precomputed_ner_label(seg_indices)
                if ner_label:
                    upos_override = _NER_TO_UPOS.get(ner_label)
                    if upos_override and local_idx < len(doc):
                        doc[local_idx].pos_ = upos_override
                        doc[local_idx]._.ner_locked = True

            try:
                for sent in doc.sents:
                    start_doc = int(sent.start)
                    end_doc = int(sent.end)
                    if start_doc < 0 or end_doc <= start_doc:
                        continue
                    if start_doc >= len(collapsed_to_orig) or (end_doc - 1) >= len(collapsed_to_orig):
                        continue
                    start_seg = collapsed_to_orig[start_doc][0]
                    end_seg = collapsed_to_orig[end_doc - 1][-1] + 1
                    sentences_out.append([start_seg, end_seg])
            except Exception:
                pass

            # Also process any NEW entities found by spaCy/stanza NER during UD overlay
            for ent in getattr(doc, "ents", []):
                if ent is None or not ent.label_:
                    continue
                ner_label = ent.label_
                upos_override = _NER_TO_UPOS.get(ner_label)
                if upos_override:
                    for token in ent:
                        if not (token.has_extension("ner_locked") and token._.ner_locked):
                            token.pos_ = upos_override
                            token._.ner_locked = True

            for t in doc:
                doc_i = int(t.i)
                seg_indices = collapsed_to_orig[doc_i]
                seg_i = seg_indices[0]
                head_doc_i = int(t.head.i)
                head_seg_indices = collapsed_to_orig[head_doc_i]
                head_seg_i = head_seg_indices[0]

                dep = t.dep_
                upos = t.pos_
                tag = t.tag_

                token_entry = {
                    "i": seg_i,
                    "doc_i": doc_i,
                    "text": t.text,
                    "upos": upos,
                    "tag": tag,
                    "dep": dep,
                    "head": head_seg_i,
                }
                if len(seg_indices) > 1:
                    token_entry["seg_span"] = seg_indices
                    token_entry["ner_collapsed"] = True
                tokens_out.append(token_entry)

                if dep == "ROOT" or head_doc_i == doc_i:
                    roots.append(seg_i)
                else:
                    edges_out.append(
                        {
                            "from": head_seg_i,
                            "to": seg_i,
                            "dep": dep,
                            "upos": upos,
                        }
                    )

            for ent in getattr(doc, "ents", []):
                if ent is None:
                    continue
                start_doc = int(ent.start)
                end_doc = int(ent.end)
                if start_doc < 0 or end_doc <= start_doc:
                    continue
                if start_doc >= len(collapsed_to_orig) or (end_doc - 1) >= len(collapsed_to_orig):
                    continue
                start_seg_indices = collapsed_to_orig[start_doc]
                end_seg_indices = collapsed_to_orig[end_doc - 1]
                ents_out.append(
                    {
                        "start": start_seg_indices[0],
                        "end": end_seg_indices[-1] + 1,
                        "label": ent.label_ or "",
                        "text": ent.text or "",
                    }
                )

            doc2seg = [seg_indices[0] for seg_indices in collapsed_to_orig]

            if not sentences_out and sent_spans:
                for s_start, s_end in sent_spans:
                    if s_end > s_start:
                        sentences_out.append([s_start, s_end])

            # If nothing kept, fail soft
            if not doc2seg:
                return UDOverlay(
                    ok=True,
                    tokens=[],
                    edges=[],
                    roots=[],
                    ents=[],
                    sentences=sentences_out,
                    doc2seg=[],
                    seg2doc=seg2doc,
                    error=None,
                )

            # Optional: attach dropped tokens synthetically (rarely needed; default "none")
            if attach_dropped_to != "none":
                dropped = [i for i, di in enumerate(seg2doc) if di == -1]
                if dropped:
                    # Build lookup: for each dropped, find nearest kept token index
                    kept_seg_indices = set(doc2seg)
                    for si in dropped:
                        target = None
                        if attach_dropped_to == "nearest_left":
                            for j in range(si - 1, -1, -1):
                                if j in kept_seg_indices:
                                    target = j
                                    break
                        elif attach_dropped_to == "nearest_right":
                            for j in range(si + 1, len(segments)):
                                if j in kept_seg_indices:
                                    target = j
                                    break
                        if target is not None:
                            edges_out.append(
                                {
                                    "from": target,
                                    "to": si,
                                    "dep": "dep:SKIP_ATTACH",
                                    "upos": "X",
                                }
                            )
                            tokens_out.append(
                                {
                                    "i": si,
                                    "doc_i": -1,
                                    "text": segments[si],
                                    "upos": "X",
                                    "tag": "",
                                    "dep": "dep:SKIP_ATTACH",
                                    "head": target,
                                }
                            )

            return UDOverlay(
                ok=True,
                tokens=tokens_out,
                edges=edges_out,
                roots=roots,
                ents=ents_out,
                sentences=sentences_out,
                doc2seg=doc2seg,
                seg2doc=seg2doc,
                error=None,
            )

        except Exception as e:
            return UDOverlay(
                ok=False,
                tokens=[],
                edges=[],
                roots=[],
                ents=[],
                sentences=[],
                doc2seg=[],
                seg2doc=[-1] * len(segments),
                error=f"{type(e).__name__}: {e}",
            )


# ----------------------------
# Convenience wrapper
# ----------------------------

def build_ud_overlay(
    segments: List[str],
    model_path: str,
    keep_fn=default_ud_keep_fn,
    allow_ascii_punct: bool = False,
) -> Dict[str, Any]:
    """
    One-shot helper (loads model each call; slower).
    Prefer UDParser(...) once + build_overlay(...) repeatedly.
    """
    parser = UDParser(model_path)
    overlay = parser.build_overlay(
        segments=segments,
        keep_fn=keep_fn,
        allow_ascii_punct=allow_ascii_punct,
    )
    return overlay_to_json(overlay)


def overlay_to_json(overlay: UDOverlay) -> Dict[str, Any]:
    return {
        "ok": overlay.ok,
        "tokens": overlay.tokens,
        "edges": overlay.edges,
        "roots": overlay.roots,
        "ents": overlay.ents,
        "sentences": overlay.sentences,
        "doc2seg": overlay.doc2seg,
        "seg2doc": overlay.seg2doc,
        "error": overlay.error,
    }
