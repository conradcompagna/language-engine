"""
Trankit multi-word token (MWT) adapter.

This module keeps UI-facing tokenization on the original surface tokens while
remapping expanded-word grammar back onto those tokens.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional, Tuple


# Languages where Trankit may emit MWT structures.
_MWT_LANGUAGE_KEYS = {
    "ar",
    "arabic",
    "ca",
    "catalan",
    "cs",
    "czech",
    "de",
    "german",
    "el",
    "greek",
    "es",
    "spanish",
    "fa",
    "persian",
    "fr",
    "french",
    "ga",
    "irish",
    "gl",
    "galician",
    "hbo",
    "ancient-hebrew-mwt",
    "he",
    "hebrew",
    "hr",
    "croatian",
    "hy",
    "armenian",
    "it",
    "italian",
    "lt",
    "lithuanian",
    "mr",
    "marathi",
    "nb",
    "norwegian-bokmaal",
    "norwegian_bokmaal",
    "norwegian bokmaal",
    "pt",
    "portuguese",
    "ro",
    "romanian",
    "sa",
    "sanskrit",
    "sanskrit-vedic",
    "sr",
    "serbian",
    "ta",
    "tamil",
    "tl",
    "tagalog",
    "filipino",
    "tagalog-custom",
    "tr",
    "turkish",
    "uk",
    "ukrainian",
}

_LANG_ALIAS = {
    "zh": "chinese",
    "ja": "japanese",
    "my": "myanmar",
    "nb": "norwegian-bokmaal",
}


def _normalize_lang_key(lang: Optional[str]) -> str:
    key = str(lang or "").strip().lower().replace("_", "-")
    if not key:
        return ""
    return _LANG_ALIAS.get(key, key)


def language_supports_mwt(lang: Optional[str]) -> bool:
    key = _normalize_lang_key(lang)
    return key in _MWT_LANGUAGE_KEYS


def _to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_int_pair(value: Any) -> bool:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return False
    return _to_int(value[0], None) is not None and _to_int(value[1], None) is not None


def _is_mwt_token(tok: Dict[str, Any]) -> bool:
    if not isinstance(tok, dict):
        return False
    if _is_int_pair(tok.get("id")):
        return True
    expanded = tok.get("expanded")
    return isinstance(expanded, list) and len(expanded) > 0


def _normalize_span(raw_span: Any) -> Optional[Tuple[int, int]]:
    if not isinstance(raw_span, (tuple, list)) or len(raw_span) < 2:
        return None
    start = _to_int(raw_span[0], None)
    end = _to_int(raw_span[1], None)
    if start is None or end is None:
        return None
    if end < start:
        end = start
    return (start, end)


def _derive_child_spans(
    parent_span: Optional[Tuple[int, int]],
    child_texts: List[str],
) -> List[Optional[Tuple[int, int]]]:
    n = len(child_texts)
    if n <= 0:
        return []
    if parent_span is None:
        return [None] * n

    start, end = parent_span
    width = max(0, end - start)
    if n == 1:
        return [(start, end)]
    if width <= 0:
        return [(start, start)] * n

    lengths = [max(1, len(t)) for t in child_texts]
    total = sum(lengths)
    spans: List[Tuple[int, int]] = []
    cursor = start
    consumed = 0
    for i in range(n):
        if i == n - 1:
            nxt = end
        else:
            consumed += lengths[i]
            frac = consumed / total
            nxt = start + int(round(frac * width))
            if nxt < cursor:
                nxt = cursor
            if nxt > end:
                nxt = end
        spans.append((cursor, nxt))
        cursor = nxt
    return spans


def _collect_unique_values(
    rows: List[Dict[str, Any]],
    key: str,
) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for row in rows:
        raw = row.get(key, "")
        text = str(raw or "").strip()
        if not text or text == "_":
            continue
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _collapse_value(
    rows: List[Dict[str, Any]],
    key: str,
    fallback: str = "",
    sep: str = "+",
) -> str:
    vals = _collect_unique_values(rows, key)
    if vals:
        return sep.join(vals)
    return str(fallback or "")


def _collapse_all_values(
    rows: List[Dict[str, Any]],
    key: str,
    fallback: str = "",
    sep: str = "+",
) -> str:
    """Like _collapse_value but preserves ALL values in order — no dedup,
    no skipping blanks.  Empty/missing values become *fallback* so that the
    +-split count always equals len(rows)."""
    parts: List[str] = []
    for row in rows:
        raw = row.get(key, "")
        text = str(raw or "").strip()
        if not text or text == "_":
            text = fallback
        parts.append(text)
    if parts:
        return sep.join(parts)
    return str(fallback or "")


def _choose_representative_word(
    rows: List[Dict[str, Any]],
    word_to_surface: Dict[int, int],
    surface_idx_1based: int,
) -> Optional[Dict[str, Any]]:
    # Prefer a child whose head exits the local token.
    for row in rows:
        head = _to_int(row.get("head"), 0) or 0
        if head == 0:
            return row
        mapped = word_to_surface.get(head)
        if mapped is not None and mapped != surface_idx_1based:
            return row
    return rows[0] if rows else None


def get_mwt_expanded_texts(token: Dict[str, Any]) -> List[str]:
    texts: List[str] = []
    seen: set[str] = set()
    rows = token.get("mwt_expanded_words", [])
    if isinstance(rows, list):
        for row in rows:
            text = str((row or {}).get("text", "") or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            texts.append(text)
    if texts:
        return texts
    # Fallback for pre-adapter tokens.
    expanded = token.get("expanded", [])
    if isinstance(expanded, list):
        for row in expanded:
            text = str((row or {}).get("text", "") or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            texts.append(text)
    return texts


def build_mwt_dict_fill_seed_entries(
    token: Dict[str, Any],
    lookup_all: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """
    Build dictionary-fill seed entries for a collapsed MWT parent token.

    The caller can pass its dictionary lookup callable (e.g. cedict.lookup_all).
    """
    out: List[Dict[str, Any]] = []
    texts = get_mwt_expanded_texts(token)
    for text in texts:
        entries = list(lookup_all(text) or []) if callable(lookup_all) else []
        if entries:
            first = entries[0] or {}
            out.append(
                {
                    "text": text,
                    "head": text,
                    "roman": str(first.get("pinyin", "") or ""),
                    "senses": list(first.get("flat_glosses") or first.get("senses", []) or []),
                    "source": "MWT_EXPANDED",
                }
            )
        else:
            out.append(
                {
                    "text": text,
                    "head": text,
                    "roman": "",
                    "pos": "unknown",
                    "senses": ["[no dictionary entry found for this segment]"],
                    "source": "MWT_EXPANDED",
                }
            )
    return out


def set_mwt_decoding_headroom(
    pipeline: Any,
    max_dec_len: int = 400,
    beam_size: Optional[int] = None,
) -> Dict[str, Any]:
    """Raise the MWT seq2seq decoder's hard step cap on a live Trankit pipeline.

    Trankit's MWT expander is a char-level LSTM seq2seq with a hardcoded
    `max_dec_len` loop bound (default 50) that truncates long Sanskrit
    compounds mid-decode. This helper bumps that cap in-place on every
    loaded MWT model. It is a pure runtime override — no trankit files
    are modified, and the change reverts on process restart.

    Safe because:
      - the decoder is an LSTM with no positional embeddings, so longer
        rollouts don't hit out-of-range weights;
      - no buffers are pre-sized to max_dec_len;
      - the value is only read as a loop bound in greedy/beam predict.

    Args:
      pipeline:     a trankit.Pipeline instance (post-init, after .add() calls)
      max_dec_len:  new per-step decoding cap (default 400)
      beam_size:    optional beam width override (None keeps existing value)

    Returns:
      dict of {lang: {"max_dec_len": int, "beam_size": int}} actually applied.
    """
    applied: Dict[str, Any] = {}
    mwt_models = getattr(pipeline, "_mwt_model", None)
    if not isinstance(mwt_models, dict):
        return applied

    for lang, wrapper in mwt_models.items():
        trainer = getattr(wrapper, "model", None)  # MWTWrapper.model is a Trainer
        if trainer is None:
            continue
        inner_model = getattr(trainer, "model", None)  # Trainer.model is Seq2SeqModel
        trainer_args = getattr(trainer, "args", None)

        if isinstance(trainer_args, dict):
            trainer_args["max_dec_len"] = int(max_dec_len)
            if beam_size is not None:
                trainer_args["beam_size"] = int(beam_size)
        if inner_model is not None and hasattr(inner_model, "max_dec_len"):
            inner_model.max_dec_len = int(max_dec_len)

        applied[str(lang)] = {
            "max_dec_len": int(max_dec_len),
            "beam_size": int(trainer_args.get("beam_size"))
            if isinstance(trainer_args, dict)
            else None,
        }
    return applied


def patch_lemma_predict_dict_first() -> bool:
    """Replace ``LemmaWrapper.predict`` with a version that consults the
    frequency lexicon before running the seq2seq decoder.

    Upstream's ``LemmaWrapper.predict`` decodes every token with seq2seq and
    then calls ``ensemble()`` which overrides the output with the dict lemma
    for any ``(word, pos)`` pair already in ``composite_dict``/``word_dict``.
    That wastes full beam-search decoding on tokens whose lemma will be
    thrown away. Trankit defines ``skip_seq2seq()`` for exactly this purpose
    but never calls it from the predict path.

    This patch:
      1. Builds the ``(text, pos)`` list the same way ``LemmaDataLoader.load_doc``
         does.
      2. Calls ``skip_seq2seq()`` to flag dict hits.
      3. If every token is a dict hit, skips seq2seq entirely.
      4. Otherwise constructs a minimal tagged_doc containing only the misses,
         runs seq2seq on those, then interleaves dict + seq2seq outputs in
         original order before passing through ``ensemble()``.

    Identity-mapping treebanks (``UD_Old_French-SRCMF``,
    ``UD_Vietnamese-VTB``, ``UD_Vietnamese-VLSP``) keep the upstream path.

    Class-level patch — one call patches every wrapper. Reversible on
    process restart.
    """
    try:
        from trankit.models.lemma_model import LemmaWrapper, set_lemma
        from trankit.iterators.lemmatizer_iterators import LemmaDataLoader
        from trankit.utils.conll import TOKENS, TEXT, UPOS, ID, EXPANDED
    except Exception:
        return False

    def _patched_predict(self, tagged_doc, obmit_tag):
        if self.treebank_name in [
            "UD_Old_French-SRCMF",
            "UD_Vietnamese-VTB",
            "UD_Vietnamese-VLSP",
        ]:
            preds = [
                t[TEXT]
                for sentence in tagged_doc
                for t in sentence[TOKENS]
                if type(t[ID]) == int or len(t[ID]) == 1
            ]
            return set_lemma(tagged_doc, preds, obmit_tag)

        # Build (text, pos) pairs in original document order, matching
        # LemmaDataLoader.load_doc's traversal exactly.
        predict_dict_input: List[List[Any]] = []
        for sentence in tagged_doc:
            for t in sentence[TOKENS]:
                if type(t[ID]) == int or len(t[ID]) == 1:
                    predict_dict_input.append([t[TEXT], t[UPOS] if UPOS in t else None])
                else:
                    for w in t.get(EXPANDED, []) or []:
                        predict_dict_input.append([w[TEXT], w[UPOS] if UPOS in w else None])

        # Dict-first: which tokens are answered by the lexicon?
        try:
            skip_flags = self.model.skip_seq2seq(predict_dict_input)
        except Exception:
            skip_flags = [False] * len(predict_dict_input)

        # Fast path: no tokens need the seq2seq at all.
        if not skip_flags or all(skip_flags):
            placeholder = [w[0] for w in predict_dict_input]
            preds = self.model.ensemble(predict_dict_input, placeholder)
            return set_lemma(tagged_doc, preds, obmit_tag)

        # Build a minimal tagged_doc containing only the dict-miss tokens.
        miss_tokens: List[Dict[str, Any]] = []
        miss_id = 1
        for (text, pos), skip in zip(predict_dict_input, skip_flags):
            if skip:
                continue
            tok: Dict[str, Any] = {ID: miss_id, TEXT: text}
            if pos is not None:
                tok[UPOS] = pos
            miss_tokens.append(tok)
            miss_id += 1

        miss_doc = [{TOKENS: miss_tokens}]
        batch = LemmaDataLoader(
            miss_doc,
            self.args["batch_size"],
            self.loaded_args,
            vocab=self.vocab,
            evaluation=True,
        )

        miss_preds: List[str] = []
        miss_edits: List[int] = []
        for b in batch:
            ps, es = self.model.predict(b, self.args["beam_size"])
            miss_preds += ps
            if es is not None:
                miss_edits += es

        miss_words = [tok[TEXT] for tok in miss_tokens]
        miss_preds = self.model.postprocess(
            miss_words,
            miss_preds,
            edits=(miss_edits if miss_edits else None),
        )

        # Stitch dict + seq2seq outputs back into one list in original order.
        full_preds: List[str] = []
        miss_iter = iter(miss_preds)
        for (text, _pos), skip in zip(predict_dict_input, skip_flags):
            if skip:
                full_preds.append(text)  # placeholder; ensemble will override
            else:
                full_preds.append(next(miss_iter))

        preds = self.model.ensemble(predict_dict_input, full_preds)
        return set_lemma(tagged_doc, preds, obmit_tag)

    LemmaWrapper.predict = _patched_predict
    return True


def maybe_expand_mwt_doc(
    doc: Dict[str, Any],
    lang: Optional[str],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Collapse MWT-expanded grammar back onto original surface tokens.

    Output sentences keep original token count/text (surface form). MWT children
    are stored on each parent token under:
      - mwt_expanded_words
      - mwt_expanded_texts
    """
    key = _normalize_lang_key(lang)
    supports = language_supports_mwt(key)
    meta = {
        "applied": False,
        "supports_mwt": supports,
        "language": key,
        "expanded_token_count": 0,
        "surface_token_count": 0,
    }

    if not isinstance(doc, dict):
        return doc, meta
    if not supports:
        return doc, meta

    sentences = doc.get("sentences")
    if not isinstance(sentences, list) or not sentences:
        return doc, meta

    out_doc = deepcopy(doc)
    out_sentences = out_doc.get("sentences", [])
    total_expanded = 0
    total_surface = 0

    for sent in out_sentences:
        if not isinstance(sent, dict):
            continue
        sent_tokens = sent.get("tokens")
        if not isinstance(sent_tokens, list) or not sent_tokens:
            continue

        has_mwt = any(_is_mwt_token(tok) for tok in sent_tokens if isinstance(tok, dict))
        if not has_mwt:
            total_surface += len(sent_tokens)
            continue

        surface_tokens: List[Dict[str, Any]] = []
        rows_by_surface: List[List[Dict[str, Any]]] = []
        word_to_surface: Dict[int, int] = {}
        word_to_surface_part: Dict[int, Tuple[int, int]] = {}

        # Pass 1: keep original surface tokens, attach MWT children, and build maps.
        for surface_idx_1based, tok in enumerate(sent_tokens, start=1):
            if not isinstance(tok, dict):
                continue
            parent = dict(tok)
            rows_for_surface: List[Dict[str, Any]] = []

            expanded = tok.get("expanded")
            if _is_mwt_token(tok) and isinstance(expanded, list) and expanded:
                parent_span = _normalize_span(tok.get("span"))
                parent_dspan = _normalize_span(tok.get("dspan"))
                child_texts = [str((c or {}).get("text", "") or "") for c in expanded]
                child_spans = _derive_child_spans(parent_span, child_texts)
                child_dspans = _derive_child_spans(parent_dspan, child_texts)

                mwt_id_start = None
                if _is_int_pair(tok.get("id")):
                    mwt_id_start = _to_int(tok.get("id")[0], None)

                children: List[Dict[str, Any]] = []
                for ci, child in enumerate(expanded):
                    row = dict(child or {})
                    if row.get("id") is None and mwt_id_start is not None:
                        row["id"] = mwt_id_start + ci
                    if _normalize_span(row.get("span")) is None and ci < len(child_spans):
                        if child_spans[ci] is not None:
                            row["span"] = child_spans[ci]
                    if _normalize_span(row.get("dspan")) is None and ci < len(child_dspans):
                        if child_dspans[ci] is not None:
                            row["dspan"] = child_dspans[ci]

                    child_id = _to_int(row.get("id"), None)
                    if child_id is not None:
                        word_to_surface[child_id] = surface_idx_1based
                        word_to_surface_part[child_id] = (
                            surface_idx_1based,
                            ci,
                        )
                    children.append(row)
                    rows_for_surface.append(row)

                parent["mwt_expanded_words"] = children
                parent["mwt_expanded_texts"] = get_mwt_expanded_texts(parent)
                total_expanded += len(children)
            else:
                tok_id = _to_int(tok.get("id"), None)
                if tok_id is not None:
                    word_to_surface[tok_id] = surface_idx_1based
                parent["mwt_expanded_words"] = []
                parent["mwt_expanded_texts"] = []
                rows_for_surface.append(tok)

            parent["id"] = surface_idx_1based
            surface_tokens.append(parent)
            rows_by_surface.append(rows_for_surface)

        # Pass 2: collapse word-level syntax back to surface tokens.
        for idx0, parent in enumerate(surface_tokens):
            surface_idx = idx0 + 1
            rows = rows_by_surface[idx0] if idx0 < len(rows_by_surface) else []
            rep = _choose_representative_word(rows, word_to_surface, surface_idx)

            if rep is not None:
                rep_head = _to_int(rep.get("head"), 0) or 0
                if rep_head == 0:
                    parent["head"] = 0
                else:
                    parent["head"] = int(word_to_surface.get(rep_head, surface_idx))
                    rep_head_part = word_to_surface_part.get(rep_head)
                    if rep_head_part is not None:
                        parent["mwt_head_part_index"] = int(rep_head_part[1])

                # Collect ALL subword edges so the UI can show every arc on hover.
                all_subword_edges = []
                for row_idx, row in enumerate(rows):
                    row_head = _to_int(row.get("head"), 0) or 0
                    head_part_index = None
                    if row_head == 0:
                        mapped = 0  # root
                    else:
                        mapped = word_to_surface.get(row_head, surface_idx)
                        head_part = word_to_surface_part.get(row_head)
                        if head_part is not None:
                            head_part_index = int(head_part[1])
                    all_subword_edges.append(
                        {
                            "head": int(mapped),
                            "part_index": int(row_idx),
                            "head_part_index": head_part_index,
                            "deprel": str(row.get("deprel", "dep") or "dep"),
                            "upos": str(row.get("upos", "X") or "X"),
                        }
                    )
                parent["mwt_subword_edges"] = all_subword_edges

            parent["deprel"] = _collapse_all_values(
                rows, "deprel", fallback=str(parent.get("deprel", "dep") or "dep"), sep="+"
            )
            parent["upos"] = _collapse_all_values(
                rows, "upos", fallback=str(parent.get("upos", "X") or "X"), sep="+"
            )
            parent["xpos"] = _collapse_all_values(
                rows, "xpos", fallback=str(parent.get("xpos", "") or ""), sep="+"
            )
            parent["lemma"] = _collapse_all_values(
                rows, "lemma", fallback=str(parent.get("lemma", "") or ""), sep="+"
            )
            parent["feats"] = _collapse_all_values(rows, "feats", fallback="", sep="+")

            if not str(parent.get("ner", "") or "").strip():
                ner_vals = _collect_unique_values(rows, "ner")
                if ner_vals:
                    parent["ner"] = ner_vals[0]

        sent["tokens"] = surface_tokens
        total_surface += len(surface_tokens)
        meta["applied"] = True

    meta["expanded_token_count"] = total_expanded
    meta["surface_token_count"] = total_surface
    return out_doc, meta
