"""Language dispatch, model configuration, and shared Trankit lifecycle.

Dictionary indexes and hydration are handled by dict_lookup_sqlite. Language
display settings are loaded from wiktionary_general/lang_config_*.json.
"""

from __future__ import annotations

import threading
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

APP_ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Language hooks — each language module provides one of these
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Registry definition
# ---------------------------------------------------------------------------

LANGUAGE_REGISTRY: Dict[str, Dict[str, Any]] = {
    # ----- CJK & Vietnamese — now routed through Wiktionary pipeline -----
    # Trankit special handling (custom NER, pretokenization) preserved;
    # dictionaries switched from CEDICT/JMDict/KRDICT to Wiktionary TSVs.
    "zh": {
        "folder": "wiktionary_general",
        "trankit_name": "chinese",
        "aliases": ["chinese"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-chinese.tsv",
        "dict_kwargs": {"lang_code": "zh"},
        "lang_config_file": "wiktionary_general/lang_config_zh.json",
        "dict_sources": {
            "wiktionary": {
                "label": "Wiktionary",
                "dict_file": "wiktionary general pipeline/converted_tsv/dict-chinese.tsv",
            },
            "cc-cedict": {
                "label": "CC-CEDICT",
                "dict_file": "wiktionary general pipeline/converted_tsv/dict-chinese-cc-cedict.tsv",
            },
        },
    },
    "ja": {
        "folder": "wiktionary_general",
        "trankit_name": "customized-ner",
        "trankit_cache_dir": str(
            Path(__file__).resolve().parent / "training" / "trankit_save_ja_ner_v2"
        ),
        "trankit_treebank": "UD_Japanese-GSD",
        "has_ner": True,
        "aliases": ["japanese"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-japanese.tsv",
        "dict_kwargs": {"lang_code": "ja"},
        "lang_config_file": "wiktionary_general/lang_config_ja.json",
        "dict_sources": {
            "wiktionary": {
                "label": "Wiktionary",
                "dict_file": "wiktionary general pipeline/converted_tsv/dict-japanese.tsv",
            },
            "jmdict": {
                "label": "JMDict",
                "dict_file": "wiktionary general pipeline/converted_tsv/dict-japanese-jmdict.tsv",
            },
        },
    },
    "ko": {
        "folder": "wiktionary_general",
        "trankit_name": "korean-ner",
        "trankit_treebank": "UD_Korean-Kaist",
        "has_ner": True,
        "aliases": ["korean"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-korean.tsv",
        "dict_kwargs": {"lang_code": "ko"},
        "lang_config_file": "wiktionary_general/lang_config_ko.json",
        "dict_sources": {
            "wiktionary": {
                "label": "Wiktionary",
                "dict_file": "wiktionary general pipeline/converted_tsv/dict-korean.tsv",
            },
            "krdict": {
                "label": "KRDict",
                "dict_file": "wiktionary general pipeline/converted_tsv/dict-korean-krdict.tsv",
            },
        },
    },
    "vi": {
        "folder": "wiktionary_general",
        "trankit_name": "vietnamese",
        "has_ner": True,
        "aliases": ["vietnamese"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-vietnamese.tsv",
        "dict_kwargs": {"lang_code": "vi"},
        "lang_config_file": "wiktionary_general/lang_config_vi.json",
    },
    "lzh": {
        "folder": "wiktionary_general",
        "trankit_name": "classical-chinese",
        "has_ner": True,
        "aliases": ["classical"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-classical-chinese.tsv",
        "dict_kwargs": {"lang_code": "lzh"},
        "default_dict_source": "chinese-notes",
        "lang_config_file": "wiktionary_general/lang_config_lzh.json",
        "dict_sources": {
            "chinese-notes": {
                "label": "Chinese Notes",
                "dict_file": "wiktionary general pipeline/converted_tsv/dict-classical-chinese.tsv",
            },
        },
    },
    # ----- Wiktionary general pipeline languages (existing, now TSV) -----
    "tr": {
        "folder": "wiktionary_general",
        "trankit_name": "turkish",
        "has_ner": True,
        "aliases": ["turkish"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-turkish.tsv",
        "dict_kwargs": {"lang_code": "tr"},
        "lang_config_file": "wiktionary_general/lang_config_tr.json",
    },
    # "te": Telugu — temporarily excluded (no converted TSV yet)
    # "mr": Marathi — temporarily excluded (no converted TSV yet)
    "fa": {
        "folder": "wiktionary_general",
        "trankit_name": "persian",
        "has_ner": True,
        "aliases": ["persian"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-persian.tsv",
        "dict_kwargs": {"lang_code": "fa"},
        "lang_config_file": "wiktionary_general/lang_config_fa.json",
    },
    "id": {
        "folder": "wiktionary_general",
        "trankit_name": "indonesian",
        "has_ner": True,
        "aliases": ["indonesian"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-indonesian.tsv",
        "dict_kwargs": {"lang_code": "id"},
        "lang_config_file": "wiktionary_general/lang_config_id.json",
    },
    "hi": {
        "folder": "wiktionary_general",
        "trankit_name": "hindi",
        "has_ner": True,
        "aliases": ["hindi"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-hindi.tsv",
        "dict_kwargs": {"lang_code": "hi"},
        "lang_config_file": "wiktionary_general/lang_config_hi.json",
    },
    "ar": {
        "folder": "wiktionary_general",
        "trankit_name": "arabic",
        "trankit_treebank": "UD_Arabic-PADT",
        "has_mwt": True,
        "tokenizer_path": "native",
        "aliases": ["arabic"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-arabic.tsv",
        "dict_kwargs": {"lang_code": "ar"},
        "lang_config_file": "wiktionary_general/lang_config_ar.json",
    },
    "th": {
        "folder": "wiktionary_general",
        "trankit_name": "thai-ner",
        "trankit_treebank": "UD_Thai-TUD",
        "has_ner": True,
        "identity_lemma": True,
        "char_level_tokenize": True,
        "aliases": ["thai"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-thai.tsv",
        "dict_kwargs": {"lang_code": "th"},
        "lang_config_file": "wiktionary_general/lang_config_th.json",
    },
    "sa": {
        "folder": "wiktionary_general",
        "trankit_name": "sanskrit-vedic",
        "trankit_treebank": "UD_Vedic_Sanskrit-Vedic",
        "has_mwt": True,
        "has_ner": True,
        "aliases": ["sanskrit"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-sanskrit-dcs-compact.tsv",
        "dict_kwargs": {"lang_code": "sa"},
        "default_dict_source": "dcs",
        "lang_config_file": "wiktionary_general/lang_config_sa.json",
        "dict_sources": {
            "dcs": {
                "label": "DCS (Digital Corpus of Sanskrit)",
                "dict_file": "wiktionary general pipeline/converted_tsv/dict-sanskrit-dcs-compact.tsv",
            },
        },
    },
    "ang": {
        "folder": "wiktionary_general",
        "trankit_name": "customized",
        "trankit_treebank": "UD_Customized",
        "has_ner": True,
        "aliases": ["oldenglish", "old-english", "old english"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-oldenglish.tsv",
        "dict_kwargs": {"lang_code": "ang"},
        "default_dict_source": "wiktionary",
        "lang_config_file": "wiktionary_general/lang_config_ang.json",
        "dict_sources": {
            "wiktionary": {"label": "Wiktionary"},
        },
    },
    # ----- New Wiktionary languages -----
    "fr": {
        "folder": "wiktionary_general",
        "trankit_name": "french",  # UD_French-GSD (default, CC license)
        "aliases": ["french"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-french.tsv",
        "dict_kwargs": {"lang_code": "fr"},
        "lang_config_file": "wiktionary_general/lang_config_fr.json",
    },
    "it": {
        "folder": "wiktionary_general",
        "trankit_name": "italian-twittiro",  # UD_Italian-TWITTIRO (CC license)
        "trankit_treebank": "UD_Italian-TWITTIRO",
        "has_ner": True,
        "aliases": ["italian"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-italian.tsv",
        "dict_kwargs": {"lang_code": "it"},
        "lang_config_file": "wiktionary_general/lang_config_it.json",
    },
    "ru": {
        "folder": "wiktionary_general",
        "trankit_name": "russian-gsd",  # UD_Russian-GSD (CC license)
        "trankit_treebank": "UD_Russian-GSD",
        "aliases": ["russian"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-russian.tsv",
        "dict_kwargs": {"lang_code": "ru"},
        "lang_config_file": "wiktionary_general/lang_config_ru.json",
    },
    "es": {
        "folder": "wiktionary_general",
        "trankit_name": "spanish-gsd",  # UD_Spanish-GSD (CC license)
        "trankit_treebank": "UD_Spanish-GSD",
        "aliases": ["spanish"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-spanish.tsv",
        "dict_kwargs": {"lang_code": "es"},
        "lang_config_file": "wiktionary_general/lang_config_es.json",
    },
    "de": {
        "folder": "wiktionary_general",
        "trankit_name": "german",  # UD_German-GSD
        "aliases": ["german"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-german.tsv",
        "dict_kwargs": {"lang_code": "de"},
        "lang_config_file": "wiktionary_general/lang_config_de.json",
    },
    "nl": {
        "folder": "wiktionary_general",
        "trankit_name": "dutch",  # UD_Dutch-Alpino
        "aliases": ["dutch"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-dutch.tsv",
        "dict_kwargs": {"lang_code": "nl"},
        "lang_config_file": "wiktionary_general/lang_config_nl.json",
    },
    "pt": {
        "folder": "wiktionary_general",
        "trankit_name": "portuguese",  # UD_Portuguese-Bosque
        "has_ner": True,
        "aliases": ["portuguese"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-portuguese.tsv",
        "dict_kwargs": {"lang_code": "pt"},
        "lang_config_file": "wiktionary_general/lang_config_pt.json",
    },
    "la": {
        "folder": "wiktionary_general",
        "trankit_name": "latin",  # UD_Latin-ITTB
        "has_ner": True,
        "aliases": ["latin"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-latin.tsv",
        "dict_kwargs": {"lang_code": "la"},
        "lang_config_file": "wiktionary_general/lang_config_la.json",
    },
    "el": {
        "folder": "wiktionary_general",
        "trankit_name": "greek",  # UD_Greek-GDT
        "has_ner": True,
        "aliases": ["greek"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-greek.tsv",
        "dict_kwargs": {"lang_code": "el"},
        "lang_config_file": "wiktionary_general/lang_config_el.json",
    },
    "hy": {
        "folder": "wiktionary_general",
        "trankit_name": "armenian",  # UD_Armenian-ArmTDP
        "has_ner": True,
        "aliases": ["armenian"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-armenian.tsv",
        "dict_kwargs": {"lang_code": "hy"},
        "lang_config_file": "wiktionary_general/lang_config_hy.json",
    },
    "grc": {
        "folder": "wiktionary_general",
        "trankit_name": "ancient-greek",  # UD_Ancient_Greek-PROIEL
        "has_ner": True,
        "aliases": ["ancient-greek", "ancientgreek"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-ancientgreek.tsv",
        "dict_kwargs": {"lang_code": "grc"},
        "default_dict_source": "wiktionary",
        "lang_config_file": "wiktionary_general/lang_config_grc.json",
        "dict_sources": {
            "wiktionary": {
                "label": "Wiktionary",
                "dict_file": "wiktionary general pipeline/converted_tsv/dict-ancientgreek.tsv",
            },
        },
    },
    "he": {
        "folder": "wiktionary_general",
        "trankit_name": "hebrew",  # UD_Hebrew-HTB
        "has_ner": True,
        "aliases": ["hebrew"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-hebrew.tsv",
        "dict_kwargs": {"lang_code": "he"},
        "lang_config_file": "wiktionary_general/lang_config_he.json",
    },
    # ----- New custom-trained languages -----
    "tl": {
        "folder": "wiktionary_general",
        "trankit_name": "tagalog-custom",
        "trankit_treebank": "UD_Tagalog-Custom",
        "has_mwt": True,
        "has_ner": True,
        "aliases": ["tagalog", "filipino"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-tagalog.tsv",
        "dict_kwargs": {"lang_code": "tl"},
        "lang_config_file": "wiktionary_general/lang_config_tl.json",
    },
    "sw": {
        "folder": "wiktionary_general",
        "trankit_name": "swahili-custom",
        "trankit_treebank": "UD_Swahili-Custom",
        "has_ner": True,
        "aliases": ["swahili", "kiswahili"],
        "dict_file": "wiktionary general pipeline/converted_tsv/dict-swahili.tsv",
        "dict_kwargs": {"lang_code": "sw"},
        "lang_config_file": "wiktionary_general/lang_config_sw.json",
    },
}

# Build reverse alias map: "chinese" -> "zh", "japanese" -> "ja", etc.
_ALIAS_MAP: Dict[str, str] = {}
for _code, _info in LANGUAGE_REGISTRY.items():
    _ALIAS_MAP[_code.lower()] = _code
    for _alias in _info.get("aliases", []):
        _ALIAS_MAP[_alias.lower()] = _code


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def resolve_lang_code(raw: str) -> Optional[str]:
    """Normalize a raw language string to a registry code, or None."""
    if not raw:
        return None
    return _ALIAS_MAP.get(raw.strip().lower())


def get_folder_map() -> Dict[str, str]:
    """Return {code_or_alias: folder} for lang_config loading."""
    out: Dict[str, str] = {}
    for code, info in LANGUAGE_REGISTRY.items():
        out[code] = info["folder"]
        for alias in info.get("aliases", []):
            out[alias] = info["folder"]
    return out


def get_registered_lang_codes() -> List[str]:
    """Return all primary language codes."""
    return list(LANGUAGE_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Trankit — single pipeline, threading lock
# ---------------------------------------------------------------------------

_trankit_pipeline = None
_trankit_lock = threading.Lock()
_trankit_onnx_live_enabled = False
_trankit_onnx_live_report: Dict[str, Any] = {}


def _record_trankit_timing(lang_code: str, wait_ms: float, run_ms: float) -> None:
    try:
        from analytics import record_trankit_timing

        record_trankit_timing(lang_code, wait_ms, run_ms)
    except Exception:
        pass


def _newpipeline_enabled() -> bool:
    try:
        import config as le_config

        return int(getattr(le_config, "NEWPIPELINE", 0) or 0) == 1
    except Exception:
        return False


def _trankit_inference_context():
    if not _trankit_onnx_live_enabled:
        return nullcontext()
    import torch  # type: ignore

    return torch.inference_mode()


def init_trankit():
    """Initialize Trankit with all registered languages. Call once at startup."""
    global _trankit_pipeline, _trankit_onnx_live_enabled, _trankit_onnx_live_report

    newpipeline_enabled = _newpipeline_enabled()
    if newpipeline_enabled:
        from trankit_onnx_live_switch import prepare_newpipeline_environment

        prepare_newpipeline_environment()
        print("[INFO] NEWPIPELINE=1: forcing Trankit load onto CPU for ONNX runtime.")

    from trankit import Pipeline
    from trankit.utils.tbinfo import (
        lang2treebank,
        supported_langs,
        langwithner,
        tbname2training_id,
        treebank2lang,
    )

    def _registry_has_ner(info: Dict[str, Any]) -> bool:
        if info.get("has_ner", False):
            return True
        if not info.get("optional_ner", False):
            return False
        name = str(info.get("trankit_name", "") or "").strip()
        if not name:
            return False
        cache_root = Path(
            info.get("trankit_cache_dir") or (APP_ROOT / "training" / "trankit_save_ja_ner_v2")
        )
        model_dir = cache_root / "xlm-roberta-base" / name
        return (model_dir / f"{name}.ner-vocab.json").exists() and (
            model_dir / f"{name}.ner.mdl"
        ).exists()

    def _add_lang_with_ner(name: str) -> None:
        if not name:
            return
        if isinstance(langwithner, set):
            langwithner.add(name)
        elif name not in langwithner:
            langwithner.append(name)

    # Register any custom pipeline names that Trankit doesn't know about.
    # This lets us use unique identifiers (e.g. "korean-ner") so that
    # multiple languages can each have their own custom NER model without
    # colliding on the generic "customized-ner" name.
    for info in LANGUAGE_REGISTRY.values():
        name = info.get("trankit_name", "")
        treebank = info.get("trankit_treebank")
        if treebank and name and name not in supported_langs:
            supported_langs.add(name) if isinstance(
                supported_langs, set
            ) else supported_langs.append(name)
            # Only register for NER if this language has a trained NER model.
            if _registry_has_ner(info):
                _add_lang_with_ner(name)
            lang2treebank[name] = treebank
            # Only update treebank2lang for languages with their own
            # custom-trained model directory; otherwise the reverse map
            # would clobber the built-in language name that Trankit uses
            # to locate vocabs/model files.
            if treebank not in treebank2lang:
                treebank2lang[treebank] = name
            # For treebanks Trankit does not ship in tbinfo, register whether
            # the runtime should instantiate an MWT expander.
            if treebank not in tbname2training_id:
                tbname2training_id[treebank] = 1 if info.get("has_mwt", False) else 0

    for info in LANGUAGE_REGISTRY.values():
        if _registry_has_ner(info):
            _add_lang_with_ner(str(info.get("trankit_name", "") or ""))

    # Arabic uses a custom MWT expander trained on CAMeL-split data.
    arabic_treebank = LANGUAGE_REGISTRY.get("ar", {}).get("trankit_treebank")
    if arabic_treebank:
        tbname2training_id[arabic_treebank] = 1

    # Patch the LemmaWrapper to use identity lemmatizer for languages
    # that don't have a trained lemmatizer model (e.g. Thai).
    from trankit.models.lemma_model import LemmaWrapper
    from trankit.models.mwt_model import MWTWrapper
    from trankit.utils.conll import EXPANDED, ID, MISC, TEXT, TOKENS, UPOS

    _identity_treebanks = {
        info["trankit_treebank"]
        for info in LANGUAGE_REGISTRY.values()
        if info.get("identity_lemma") and info.get("trankit_treebank")
    }
    # Patch __init__: skip loading a model file for identity-lemma languages.
    _orig_lemma_init = LemmaWrapper.__init__

    def _patched_lemma_init(self, config, treebank_name, use_gpu, evaluate=True):
        self._identity_lemma_runtime = False
        if evaluate and treebank_name in _identity_treebanks:
            language = treebank2lang[treebank_name]
            model_path = (
                Path(config._cache_dir)
                / config.embedding_name
                / language
                / f"{language}_lemmatizer.pt"
            )
            # Fallback to identity lemma only when a trained lemmatizer is absent.
            if model_path.exists():
                self._identity_lemma_runtime = False
                return _orig_lemma_init(self, config, treebank_name, use_gpu, evaluate)
            from trankit.models.lemma_model import get_identity_lemma_model

            self.config = config
            self.treebank_name = treebank_name
            self.args = get_identity_lemma_model()
            self._identity_lemma_runtime = True
            print("Loading lemmatizer for {}".format(treebank2lang[treebank_name]))
            return
        self._identity_lemma_runtime = False
        _orig_lemma_init(self, config, treebank_name, use_gpu, evaluate)

    LemmaWrapper.__init__ = _patched_lemma_init
    # Patch predict: treat identity-lemma treebanks the same as Vietnamese.
    _orig_lemma_predict = LemmaWrapper.predict

    def _lemma_dict_lookup(trainer: Any, word: Any, pos: Any) -> Tuple[bool, Any]:
        composite = getattr(trainer, "composite_dict", {}) or {}
        word_dict = getattr(trainer, "word_dict", {}) or {}
        key = (word, pos)
        if key in composite:
            lemma = composite[key]
            return True, word if lemma is None else lemma
        if word in word_dict:
            lemma = word_dict[word]
            return True, word if lemma is None else lemma
        return False, None

    def _mwt_dict_lookup(trainer: Any, word: Any) -> Tuple[bool, Any]:
        expansion_dict = getattr(trainer, "expansion_dict", {}) or {}
        if word in expansion_dict:
            return True, expansion_dict[word]
        lowered = str(word).lower()
        if lowered in expansion_dict:
            return True, expansion_dict[lowered]
        return False, None

    def _patched_lemma_predict(self, tagged_doc, obmit_tag):
        if getattr(self, "_identity_lemma_runtime", False):
            from trankit.models.lemma_model import set_lemma

            preds = [
                t[TEXT]
                for sentence in tagged_doc
                for t in sentence[TOKENS]
                if type(t[ID]) == int or len(t[ID]) == 1
            ]
            return set_lemma(tagged_doc, preds, obmit_tag)
        try:
            from trankit.iterators.lemmatizer_iterators import LemmaDataLoader
            from trankit.models.lemma_model import set_lemma

            if self.treebank_name in [
                "UD_Old_French-SRCMF",
                "UD_Vietnamese-VTB",
                "UD_Vietnamese-VLSP",
            ]:
                return _orig_lemma_predict(self, tagged_doc, obmit_tag)

            batch = LemmaDataLoader(
                tagged_doc,
                self.args["batch_size"],
                self.loaded_args,
                vocab=self.vocab,
                evaluation=True,
            )
            if len(batch) == 0:
                return _orig_lemma_predict(self, tagged_doc, obmit_tag)

            predict_pairs: List[List[Any]] = []
            for sentence in batch.doc:
                for token in sentence[TOKENS]:
                    if type(token[ID]) == int or len(token[ID]) == 1:
                        predict_pairs.append([token[TEXT], token[UPOS] if UPOS in token else None])
                    else:
                        for word in token[EXPANDED]:
                            predict_pairs.append([word[TEXT], word[UPOS] if UPOS in word else None])

            final_preds: List[Any] = [None] * len(predict_pairs)
            miss_indices: List[int] = []
            miss_doc = [{ID: 1, TOKENS: []}]
            for idx, pair in enumerate(predict_pairs):
                hit, lemma = _lemma_dict_lookup(self.model, pair[0], pair[1])
                if hit:
                    final_preds[idx] = lemma
                    continue
                miss_indices.append(idx)
                token = {ID: len(miss_doc[0][TOKENS]) + 1, TEXT: pair[0]}
                if pair[1] is not None:
                    token[UPOS] = pair[1]
                miss_doc[0][TOKENS].append(token)

            if miss_indices:
                miss_batch = LemmaDataLoader(
                    miss_doc,
                    self.args["batch_size"],
                    self.loaded_args,
                    vocab=self.vocab,
                    evaluation=True,
                )
                miss_preds: List[Any] = []
                miss_edits: List[Any] = []
                for b in miss_batch:
                    preds, edits = self.model.predict(b, self.args["beam_size"])
                    miss_preds += preds
                    if edits is not None:
                        miss_edits += edits

                miss_words = [predict_pairs[i][0] for i in miss_indices]
                miss_pairs = [predict_pairs[i] for i in miss_indices]
                miss_preds = self.model.postprocess(
                    miss_words,
                    miss_preds,
                    edits=miss_edits if miss_edits else None,
                )
                miss_preds = self.model.ensemble(miss_pairs, miss_preds)
                for idx, pred in zip(miss_indices, miss_preds):
                    final_preds[idx] = pred

            for idx, pred in enumerate(final_preds):
                if pred is None:
                    final_preds[idx] = predict_pairs[idx][0]

            self._lemma_early_exit_last = {
                "total": len(predict_pairs),
                "dict_hits": len(predict_pairs) - len(miss_indices),
                "seq2seq": len(miss_indices),
            }
            return set_lemma(batch.doc, final_preds, obmit_tag)
        except Exception as exc:
            self._lemma_early_exit_last = {"error": str(exc)}
            return _orig_lemma_predict(self, tagged_doc, obmit_tag)
        return _orig_lemma_predict(self, tagged_doc, obmit_tag)

    LemmaWrapper.predict = _patched_lemma_predict

    _orig_mwt_predict = MWTWrapper.predict

    def _patched_mwt_predict(self, tokenized_doc):
        try:
            from copy import deepcopy as _mwt_deepcopy
            from trankit.iterators.mwt_iterators import MWTDataLoader
            from trankit.models.mwt_model import get_mwt_expansions, set_mwt_expansions

            batch = MWTDataLoader(
                tokenized_doc,
                self.args["batch_size"],
                self.loaded_args,
                vocab=self.vocab,
                evaluation=True,
            )
            if len(batch) == 0:
                self._mwt_early_exit_last = {"total": 0, "dict_hits": 0, "seq2seq": 0}
                return set_mwt_expansions(_mwt_deepcopy(batch.doc), [])

            candidates = get_mwt_expansions(batch.doc, evaluation=True, training_mode=False)
            final_preds: List[Any] = [None] * len(candidates)
            miss_indices: List[int] = []
            miss_doc = [{ID: 1, TOKENS: []}]
            for idx, candidate in enumerate(candidates):
                hit, expansion = _mwt_dict_lookup(self.model, candidate)
                if hit:
                    final_preds[idx] = expansion
                    continue
                miss_indices.append(idx)
                miss_doc[0][TOKENS].append(
                    {
                        ID: (len(miss_doc[0][TOKENS]) + 1, len(miss_doc[0][TOKENS]) + 1),
                        TEXT: candidate,
                        MISC: "MWT=Yes",
                    }
                )

            if miss_indices:
                miss_batch = MWTDataLoader(
                    miss_doc,
                    self.args["batch_size"],
                    self.loaded_args,
                    vocab=self.vocab,
                    evaluation=True,
                )
                miss_preds: List[Any] = []
                for b in miss_batch:
                    miss_preds += self.model.predict(b)
                miss_candidates = [candidates[i] for i in miss_indices]
                miss_preds = self.model.ensemble(miss_candidates, miss_preds)
                for idx, pred in zip(miss_indices, miss_preds):
                    final_preds[idx] = pred

            for idx, pred in enumerate(final_preds):
                if pred is None:
                    final_preds[idx] = candidates[idx]

            self._mwt_early_exit_last = {
                "total": len(candidates),
                "dict_hits": len(candidates) - len(miss_indices),
                "seq2seq": len(miss_indices),
            }
            return set_mwt_expansions(_mwt_deepcopy(batch.doc), final_preds)
        except Exception as exc:
            self._mwt_early_exit_last = {"error": str(exc)}
            return _orig_mwt_predict(self, tokenized_doc)

    MWTWrapper.predict = _patched_mwt_predict

    # Patch the tokenizer to:
    # (1) use character-level tokenization for whitespace-less scripts
    #     (Thai, via char_level_tokenize: True) — same pathway Trankit
    #     already uses for Chinese/Japanese.
    # (2) apply per-treebank sentence-final-marker replacements BEFORE the
    #     model sees the text, so XLM-R encounters the Latin punctuation
    #     it was pretrained on.
    #     1-for-1 character swaps keep sent_labels position-aligned.
    _char_level_treebanks = {
        info["trankit_treebank"]
        for info in LANGUAGE_REGISTRY.values()
        if info.get("char_level_tokenize") and info.get("trankit_treebank")
    }
    # Classical Chinese (Kyoto) and Vedic Sanskrit treebanks were annotated
    # without punctuation for "authenticity," so their tokenizers never learned
    # to break on the native marks at runtime. XLM-R's pretraining, however,
    # heavily biases sentence breaks on ASCII punctuation — so we translate
    # every native sentence/clause-level mark to its closest ASCII equivalent
    # before the model sees the text. This is a 1-for-1 char swap (position-
    # aligned with sent_labels) and massively improves sentence splitting.
    _cjk_punct_to_ascii = {
        "。": ".",  # U+3002 ideographic full stop
        "？": "?",  # U+FF1F fullwidth question mark
        "！": "!",  # U+FF01 fullwidth exclamation
        "；": ";",  # U+FF1B fullwidth semicolon
        "：": ":",  # U+FF1A fullwidth colon
        "，": ",",  # U+FF0C fullwidth comma
        "、": ",",  # U+3001 ideographic comma
        "｡": ".",  # U+FF61 halfwidth ideographic full stop
        "･": ",",  # U+FF65 halfwidth katakana middle dot (clause separator)
        "·": ",",  # U+00B7 middle dot (occasional clause separator)
    }
    # Devanagari/Indic marks that appear in Vedic/Sanskrit editions. The two
    # dandas are sentence-final; the others are clause/verse-level and also
    # help XLM-R segment. Mapped to ASCII to pull them into pretraining-space.
    _devanagari_punct_to_ascii = {
        "।": ".",  # U+0964 danda
        "॥": ".",  # U+0965 double danda
        "॰": ".",  # U+0970 abbreviation sign
    }
    _sentence_final_marker_map = {
        # Classical Chinese — UD_Classical_Chinese-Kyoto has no punctuation in
        # training, so the tokenizer ignores native CJK marks. Swap everything
        # to ASCII to trigger XLM-R's pretrained sentence-break bias.
        "UD_Classical_Chinese-Kyoto": dict(_cjk_punct_to_ascii),
        # Vedic Sanskrit — same story: UD_Vedic_Sanskrit-Vedic was stripped of
        # dandas/punctuation during annotation. Map dandas + any Latin-ish
        # punctuation that leaks in from editorial sources.
        "UD_Vedic_Sanskrit-Vedic": dict(_devanagari_punct_to_ascii),
        # Other Indic treebanks — danda → period only (they were trained with
        # punctuation intact, so we don't need the wider map).
        "UD_Hindi-HDTB": {"।": ".", "॥": "."},
        # Arabic-script question mark / full stop → ASCII
        "UD_Arabic-PADT": {"؟": "?"},
        "UD_Persian-Seraji": {"؟": "?"},
        # Hebrew sof pasuq / paseq → ASCII
        "UD_Hebrew-HTB": {"׃": "."},
    }
    if _char_level_treebanks or _sentence_final_marker_map:
        import trankit.utils.tokenizer_utils as _tok_utils

        _orig_wp_tokenize = _tok_utils.wordpiece_tokenize_from_raw_text

        def _patched_wp_tokenize(
            wordpiece_splitter, sent_text, sent_labels, sent_position_in_paragraph, treebank_name
        ):
            replacements = _sentence_final_marker_map.get(treebank_name)
            if replacements:
                for old, new in replacements.items():
                    if old != new:
                        sent_text = sent_text.replace(old, new)
            if treebank_name in _char_level_treebanks:
                # Force character-level pseudo-tokens, same as Chinese/Japanese
                treebank_name = "UD_Chinese-GSD"
            return _orig_wp_tokenize(
                wordpiece_splitter,
                sent_text,
                sent_labels,
                sent_position_in_paragraph,
                treebank_name,
            )

        _tok_utils.wordpiece_tokenize_from_raw_text = _patched_wp_tokenize

    # Bump the per-treebank tokenizer cap to XLM-R's actual 512 ceiling for
    # every registered treebank — languages that fell back to 400 no longer
    # get long paragraphs cut mid-sentence.
    import trankit.utils.tbinfo as _tbinfo

    for _info in LANGUAGE_REGISTRY.values():
        _tb = _info.get("trankit_treebank")
        if _tb:
            _tbinfo.tbname2max_input_length[_tb] = 512
    for _tb in list(lang2treebank.values()):
        _tbinfo.tbname2max_input_length[_tb] = 512

    # Patch the tagger's long-sentence chunk split to prefer sentence-final
    # punctuation over raw piece-count breaks, so long sentences don't get
    # torn mid-clause into disjoint dependency forests. Within the last 60
    # pieces of the cap we break at the first sentence-final punctuation
    # word encountered; at hard_cap (max_input_length - 10) we break
    # unconditionally (original behavior).
    import trankit.iterators.tagger_iterators as _tagger_iters

    _tagger_get_examples = _tagger_iters.get_examples_from_conllu
    from trankit.utils.conll import (
        LEMMA as _LEMMA,
        UPOS as _UPOS,
        XPOS as _XPOS,
        FEATS as _FEATS,
        HEAD as _HEAD,
        DEPREL as _DEPREL,
    )
    import json as _json
    from copy import deepcopy as _deepcopy

    _sentence_break_chars = set(".?!;।॥؟۔׃·。？！")

    def _is_sentence_break_word(w):
        if not w:
            return False
        s = w.strip()
        return bool(s) and all(ch in _sentence_break_chars for ch in s)

    def _patched_tagger_load_data(self):
        with open(self.vocabs_fpath) as _f:
            self.vocabs = _json.load(_f)
        self.data, self.conllu_doc = _tagger_get_examples(
            self.wordpiece_splitter,
            self.max_input_length,
            self.tokenized_doc,
        )
        _keys = ["words", "word_ids", _LEMMA, _UPOS, _XPOS, _FEATS, _HEAD, _DEPREL]
        hard_cap = self.max_input_length - 10
        soft_cap = self.max_input_length - 60
        new_data = []
        for inst in self.data:
            words = inst["words"]
            pieces = [[p for p in self.wordpiece_splitter.tokenize(w) if p != "▁"] for w in words]
            for ps in pieces:
                if len(ps) == 0:
                    ps += ["-"]
            flat_pieces = [p for ps in pieces for p in ps]
            if len(flat_pieces) <= self.max_input_length - 2:
                new_data.append(inst)
                continue
            sub_insts = []
            cur_inst = _deepcopy(inst)
            for _k in _keys + ["flat_pieces"]:
                cur_inst[_k] = []
            for i in range(len(words)):
                for _k in _keys:
                    cur_inst[_k].append(inst[_k][i])
                cur_inst["flat_pieces"].extend(pieces[i])
                pc = len(cur_inst["flat_pieces"])
                if pc >= hard_cap:
                    sub_insts.append(cur_inst)
                    cur_inst = _deepcopy(inst)
                    for _k in _keys + ["flat_pieces"]:
                        cur_inst[_k] = []
                elif pc >= soft_cap and _is_sentence_break_word(words[i]):
                    sub_insts.append(cur_inst)
                    cur_inst = _deepcopy(inst)
                    for _k in _keys + ["flat_pieces"]:
                        cur_inst[_k] = []
            if len(cur_inst["flat_pieces"]) > 0:
                sub_insts.append(cur_inst)
            new_data.extend(sub_insts)
        self.data = new_data

    _tagger_iters.TaggerDatasetLive.load_data = _patched_tagger_load_data

    # Sanskrit NER is trained on sandhi/compound-split MWT children. Trankit's
    # stock _ner_doc only sees top-level surface tokens, so it would classify
    # the unsplit parent compound and miss the child tokens the model learned.
    # Patch only the runtime Sanskrit NER path: build a temporary child-token
    # sentence for inference, then write the predicted labels back onto the
    # original expanded child rows. pipeline_common later flattens those rows
    # and attaches the synthetic child offsets/surface anchors.
    try:
        from copy import deepcopy as _ner_deepcopy
        from torch.utils.data import DataLoader as _NerDataLoader
        import torch as _ner_torch
        from trankit.iterators.ner_iterators import NERDatasetLive as _NERDatasetLive
        from trankit.pipeline import Pipeline as _TrankitPipeline
        from trankit.utils.conll import (
            DSPAN as _DSPAN,
            EXPANDED as _EXPANDED,
            ID as _ID,
            NER as _NER,
            TEXT as _TEXT,
            TOKENS as _TOKENS,
        )
        from trankit.utils.tbinfo import tbname2tagbatchsize as _tbname2tagbatchsize

        if not getattr(_TrankitPipeline, "_language_engine_sanskrit_child_ner", False):
            _orig_ner_doc = _TrankitPipeline._ner_doc
            _orig_ner_sent = _TrankitPipeline._ner_sent

            def _is_sanskrit_child_ner_runtime(self) -> bool:
                active = str(getattr(self._config, "active_lang", "") or "")
                treebank = str(getattr(self._config, "treebank_name", "") or "")
                if active not in getattr(self, "_ner_model", {}):
                    return False
                return (
                    active in {"sanskrit-vedic", "sanskrit", "sa"}
                    or treebank == "UD_Vedic_Sanskrit-Vedic"
                )

            def _ner_word_text(row: Dict[str, Any]) -> str:
                text = str((row or {}).get(_TEXT, "") or "").strip()
                if text:
                    return text
                lemma = str((row or {}).get("lemma", "") or "").strip()
                return "" if lemma == "_" else lemma

            def _build_sanskrit_child_ner_inputs(doc: List[Dict[str, Any]]):
                ner_sentences: List[List[str]] = []
                ner_maps: List[Tuple[int, List[Tuple[int, Optional[int]]]]] = []
                for sent_idx, sent in enumerate(doc):
                    if not isinstance(sent, dict):
                        continue
                    sent_tokens = sent.get(_TOKENS)
                    if not isinstance(sent_tokens, list):
                        continue
                    words: List[str] = []
                    word_map: List[Tuple[int, Optional[int]]] = []
                    for tok_idx, tok in enumerate(sent_tokens):
                        if not isinstance(tok, dict):
                            continue
                        expanded = tok.get(_EXPANDED)
                        if isinstance(expanded, list) and expanded:
                            tok.pop(_NER, None)
                            for child_idx, child in enumerate(expanded):
                                if not isinstance(child, dict):
                                    continue
                                child_text = _ner_word_text(child)
                                if not child_text:
                                    continue
                                words.append(child_text)
                                word_map.append((tok_idx, child_idx))
                            continue
                        tok_text = _ner_word_text(tok)
                        if not tok_text:
                            continue
                        words.append(tok_text)
                        word_map.append((tok_idx, None))
                    if words:
                        ner_maps.append((sent_idx, word_map))
                        ner_sentences.append(words)
                return ner_sentences, ner_maps

            def _run_sanskrit_child_ner_doc(self, in_doc):
                if type(in_doc) == str:
                    in_doc = self._tokenize_doc(in_doc)
                dner_doc = _ner_deepcopy(in_doc)
                ner_sentences, ner_maps = _build_sanskrit_child_ner_inputs(dner_doc)
                if not ner_sentences:
                    return dner_doc

                test_set = _NERDatasetLive(
                    config=self._config,
                    tokenized_sentences=ner_sentences,
                )
                test_set.numberize()
                self._load_adapter_weights(model_name="ner")
                eval_batch_size = _tbname2tagbatchsize.get(
                    self._config.treebank_name, self._tagbatchsize
                )
                if self._config.embedding_name == "xlm-roberta-large":
                    eval_batch_size = int(eval_batch_size / 3)
                if eval_batch_size < 1:
                    eval_batch_size = 1

                for batch in _NerDataLoader(
                    test_set,
                    batch_size=eval_batch_size,
                    shuffle=False,
                    collate_fn=test_set.collate_fn,
                ):
                    word_reprs, _cls_reprs = self._embedding_layers.get_tagger_inputs(batch)
                    pred_entity_labels = self._ner_model[self._config.active_lang].predict(
                        batch, word_reprs
                    )

                    batch_size = len(batch.word_num)
                    for bid in range(batch_size):
                        local_sentid = batch.sent_index[bid]
                        if local_sentid >= len(ner_maps):
                            continue
                        original_sentid, word_map = ner_maps[local_sentid]
                        sent_tokens = dner_doc[original_sentid].get(_TOKENS, [])
                        for i in range(batch.word_num[bid]):
                            wordid = batch.word_ids[bid][i]
                            if wordid >= len(word_map):
                                continue
                            tok_idx, child_idx = word_map[wordid]
                            if tok_idx >= len(sent_tokens):
                                continue
                            tag = pred_entity_labels[bid][i]
                            tok = sent_tokens[tok_idx]
                            if child_idx is None:
                                if isinstance(tok, dict):
                                    tok[_NER] = tag
                                continue
                            expanded = tok.get(_EXPANDED) if isinstance(tok, dict) else None
                            if isinstance(expanded, list) and child_idx < len(expanded):
                                child = expanded[child_idx]
                                if isinstance(child, dict):
                                    child[_NER] = tag

                _ner_torch.cuda.empty_cache()
                return dner_doc

            def _patched_ner_doc(self, in_doc):
                if _is_sanskrit_child_ner_runtime(self):
                    return _run_sanskrit_child_ner_doc(self, in_doc)
                return _orig_ner_doc(self, in_doc)

            def _patched_ner_sent(self, in_sent):
                if not _is_sanskrit_child_ner_runtime(self):
                    return _orig_ner_sent(self, in_sent)
                if type(in_sent) == str:
                    in_sent = self._tokenize_sent(in_sent)
                dner_doc = [
                    {
                        _ID: 1,
                        _TOKENS: _ner_deepcopy(in_sent),
                    }
                ]
                out_doc = _run_sanskrit_child_ner_doc(self, dner_doc)
                return out_doc[0].get(_TOKENS, []) if out_doc else []

            _TrankitPipeline._ner_doc = _patched_ner_doc
            _TrankitPipeline._ner_sent = _patched_ner_sent
            _TrankitPipeline._language_engine_sanskrit_child_ner = True
    except Exception as e:
        print(f"[WARN] Could not patch Sanskrit child-token NER: {e}")

    # Override treebank names for customized pipelines so that Trankit
    # applies the correct language-specific preprocessing (e.g. character-
    # level tokenization for Japanese/Chinese instead of whitespace splitting,
    # CJK token normalization, and max input length).
    for info in LANGUAGE_REGISTRY.values():
        treebank = info.get("trankit_treebank")
        if treebank and info.get("trankit_name"):
            lang2treebank[info["trankit_name"]] = treebank

    # Sort so that any language with a custom cache_dir comes first;
    # Pipeline() constructor accepts cache_dir, but .add() does not.
    codes = sorted(
        LANGUAGE_REGISTRY.keys(),
        key=lambda c: 0 if LANGUAGE_REGISTRY[c].get("trankit_cache_dir") else 1,
    )
    first_code = codes[0]
    first_info = LANGUAGE_REGISTRY[first_code]
    first_name = first_info["trankit_name"]
    first_cache = first_info.get("trankit_cache_dir")
    pipeline_kwargs = {"gpu": False} if newpipeline_enabled else {}

    print(f"[INFO] Initializing Trankit pipeline ({first_name})...")
    if first_cache:
        _trankit_pipeline = Pipeline(lang=first_name, cache_dir=first_cache, **pipeline_kwargs)
    else:
        _trankit_pipeline = Pipeline(first_name, **pipeline_kwargs)

    added_names = {first_name}
    for code in codes[1:]:
        info = LANGUAGE_REGISTRY[code]
        name = info["trankit_name"]
        if name not in added_names:
            print(f"[INFO] Adding Trankit language: {name}")
            _trankit_pipeline.add(name)
            added_names.add(name)

    # traditional-chinese is no longer a registry entry (zh-Hant was removed —
    # the dropdown passes trankit=traditional-chinese as an override instead),
    # but we still need it loaded in the pipeline.
    if "traditional-chinese" not in added_names:
        print("[INFO] Adding Trankit language: traditional-chinese")
        _trankit_pipeline.add("traditional-chinese")

    # Raise the MWT decoder's per-step cap while keeping the default greedy
    # decoder width (beam=1). Pure in-memory override — reverts on restart.
    try:
        from trankit_mwt_expansion import set_mwt_decoding_headroom

        applied = set_mwt_decoding_headroom(_trankit_pipeline, max_dec_len=400, beam_size=1)
        if applied:
            print(f"[INFO] MWT decoder: max_dec_len=400, beam_size=1 for {len(applied)} languages.")
    except Exception as e:
        print(f"[WARN] Could not raise MWT decoder headroom: {e}")

    if newpipeline_enabled:
        from trankit_onnx_live_switch import install_live_onnx_pipeline

        print("[INFO] NEWPIPELINE=1: installing compressed ONNX Trankit runtime...")
        _trankit_onnx_live_report = install_live_onnx_pipeline(_trankit_pipeline)
        _trankit_onnx_live_enabled = True
        print(
            "[INFO] NEWPIPELINE=1 ready: "
            f"profile={_trankit_onnx_live_report.get('profile')} "
            f"adapters={_trankit_onnx_live_report.get('adapter_pack_count')}/"
            f"{_trankit_onnx_live_report.get('task_count')} "
            f"ort={((_trankit_onnx_live_report.get('ort_tuning') or {}).get('profile') or {}).get('name') or ((_trankit_onnx_live_report.get('ort_tuning') or {}).get('profile_name') or 'applied')}"
        )

    print("[INFO] Trankit pipeline ready.")


_MANUAL_SENTENCE_STOP_CHARS: Dict[str, frozenset[str]] = {
    # Sanskrit sources may mark dandas as native Devanagari signs or ASCII
    # pipe characters; repeated stop chars are coalesced below, so "|" covers
    # both single and double danda pipe forms.
    "sa": frozenset(".!?;|\uff1b\u2026\u3002\uff1f\uff01\uff61\u0964\u0965"),
    # Classical Chinese Kyoto training data is effectively clause-segmented,
    # so we chunk lzh on clause punctuation as well as sentence-final marks.
    "lzh": frozenset(",.:;!?\uff0c\uff1a\uff1b\u2026\u3001\u3002\uff1f\uff01\uff61\ufe50\ufe51"),
}

_MANUAL_SENTENCE_TRAILING_CLOSERS = frozenset(
    "\"'\u201d\u2019\u00bb\u203a\uff09)]\uff5d}\u3009\u300b\u300d\u300f\u3011\u3015\u3017\u3019\u301b"
)


def _split_text_for_manual_sentence_segmentation(
    text: str, lang_code: str
) -> List[Tuple[int, int]]:
    stop_chars = _MANUAL_SENTENCE_STOP_CHARS.get(str(lang_code or "").strip().lower())
    if not stop_chars:
        return [(0, len(text))] if text and text.strip() else []

    spans: List[Tuple[int, int]] = []
    start = 0
    i = 0
    n = len(text)

    while i < n:
        while start < n and text[start].isspace():
            start += 1
        if i < start:
            i = start
        if start >= n:
            break

        if text[i] not in stop_chars:
            i += 1
            continue

        end = i + 1
        while end < n and text[end] in stop_chars:
            end += 1
        while end < n and text[end] in _MANUAL_SENTENCE_TRAILING_CLOSERS:
            end += 1
        sentence_end = end
        while end < n and text[end].isspace():
            end += 1

        if text[start:sentence_end].strip():
            spans.append((start, sentence_end))
        start = end
        i = end

    while start < n and text[start].isspace():
        start += 1
    if start < n and text[start:].strip():
        spans.append((start, n))

    if not spans and text.strip():
        spans.append((0, n))
    return spans


def _shift_trankit_span_value(value: Any, offset: int) -> Optional[List[Any]]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        start = int(value[0])
        end = int(value[1])
    except (TypeError, ValueError):
        return None
    shifted = list(value)
    shifted[0] = start + offset
    shifted[1] = end + offset
    return shifted


def _remap_trankit_span_value(value: Any, context: Any) -> Optional[List[Any]]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        start = int(value[0])
        end = int(value[1])
    except (TypeError, ValueError):
        return None

    from universal_normalization import map_model_range_to_original

    mapped = map_model_range_to_original(start, end, context)
    remapped = list(value)
    remapped[0] = int(mapped[0])
    remapped[1] = int(mapped[1])
    return remapped


def _shift_trankit_offsets(node: Any, offset: int) -> Any:
    if isinstance(node, dict):
        out: Dict[str, Any] = {}
        for key, value in node.items():
            if key in {"span", "dspan"}:
                shifted = _shift_trankit_span_value(value, offset)
                if shifted is not None:
                    out[key] = shifted
                    continue
            out[key] = _shift_trankit_offsets(value, offset)
        return out
    if isinstance(node, list):
        return [_shift_trankit_offsets(item, offset) for item in node]
    return node


def _remap_trankit_offsets_to_original(node: Any, context: Any) -> Any:
    if isinstance(node, dict):
        out: Dict[str, Any] = {}
        for key, value in node.items():
            if key in {"span", "dspan"}:
                remapped = _remap_trankit_span_value(value, context)
                if remapped is not None:
                    out[key] = remapped
                    continue
            out[key] = _remap_trankit_offsets_to_original(value, context)
        return out
    if isinstance(node, list):
        return [_remap_trankit_offsets_to_original(item, context) for item in node]
    return node


def _tokenize_manual_sentence_spans_batched(
    pipeline,
    text: str,
    lang_code: str,
    strip_punctuation_after_segmentation: bool = False,
) -> List[Dict[str, Any]]:
    spans = _split_text_for_manual_sentence_segmentation(text, lang_code)
    records: List[Dict[str, Any]] = []
    for start, end in spans:
        chunk = text[start:end]
        if not chunk.strip():
            continue

        chunk_model_text = chunk
        chunk_context = None
        if strip_punctuation_after_segmentation:
            from universal_normalization import build_preprocess_context

            chunk_context = build_preprocess_context(
                chunk,
                language=lang_code,
                strip_punctuation=True,
            )
            chunk_model_text = str(chunk_context.model_text or "")
            if not chunk_model_text.strip():
                continue

        chunk_model_text = chunk_model_text.rstrip()
        if not chunk_model_text.strip():
            continue
        records.append(
            {
                "start": start,
                "end": end,
                "chunk": chunk,
                "model_text": chunk_model_text,
                "context": chunk_context,
            }
        )

    if not records:
        return []

    from collections import defaultdict

    import torch
    from torch.utils.data import DataLoader
    from trankit.iterators.tokenizer_iterators import TokenizeDatasetLive
    from trankit.utils.conll import DSPAN, ID, SSPAN
    from trankit.utils.tbinfo import (
        lang2treebank,
        tbname2max_input_length,
        tbname2tokbatchsize,
        tbname2training_id,
    )
    from trankit.utils.tokenizer_utils import get_output_sentence, normalize_token

    config = pipeline._config
    eval_batch_size = tbname2tokbatchsize.get(
        lang2treebank[pipeline.active_lang], pipeline._tokbatchsize
    )
    if config.embedding_name == "xlm-roberta-large":
        eval_batch_size = int(eval_batch_size / 2)

    combined_parts: List[str] = []
    combined_spans: List[Tuple[int, int, Dict[str, Any]]] = []
    cursor = 0
    for record in records:
        if combined_parts:
            combined_parts.append(" ")
            cursor += 1
        model_text = str(record["model_text"])
        # Keep this as one tokenizer paragraph. Blank-line separators prevent
        # Trankit from packing manual sentences into shared XLM-R batches.
        model_text = "".join(" " if ch in "\r\n" else ch for ch in model_text)
        start = cursor
        combined_parts.append(model_text)
        cursor += len(model_text)
        combined_spans.append((start, cursor, record))
    combined_text = "".join(combined_parts)
    test_set = TokenizeDatasetLive(
        config,
        combined_text,
        max_input_length=tbname2max_input_length.get(lang2treebank[pipeline.active_lang], 400),
    )
    test_set.numberize(config.wordpiece_splitter)

    pipeline._load_adapter_weights(model_name="tokenizer")

    wordpiece_pred_labels = []
    wordpiece_ends = []
    paragraph_indexes = []
    for batch in DataLoader(
        test_set, batch_size=eval_batch_size, shuffle=False, collate_fn=test_set.collate_fn
    ):
        wordpiece_reprs = pipeline._embedding_layers.get_tokenizer_inputs(batch)
        predictions = pipeline._tokenizer[config.active_lang].predict(batch, wordpiece_reprs)
        wp_pred_labels, wp_ends, para_ids = predictions[0], predictions[1], predictions[2]
        wp_pred_labels = wp_pred_labels.data.cpu().numpy().tolist()

        for i in range(len(wp_pred_labels)):
            wordpiece_pred_labels.append(wp_pred_labels[i][: len(wp_ends[i])])

        wordpiece_ends.extend(wp_ends)
        paragraph_indexes.extend(para_ids)

    para_id_to_wp_pred_labels = defaultdict(list)
    for wp_pred_ls, wp_es, p_index in zip(wordpiece_pred_labels, wordpiece_ends, paragraph_indexes):
        para_id_to_wp_pred_labels[p_index].extend(
            (pred, char_position) for pred, char_position in zip(wp_pred_ls, wp_es)
        )

    combined_wp_preds = [0 for _ in combined_text]
    for wp_label, end_position in para_id_to_wp_pred_labels.get(0, []):
        if 0 <= int(end_position) < len(combined_wp_preds):
            combined_wp_preds[int(end_position)] = wp_label

    flat_tokens = []
    current_tok = ""
    current_sent = []
    local_position = 0
    for char, wp_label in zip(combined_text, combined_wp_preds):
        local_position += 1
        current_tok += char
        if wp_label >= 1:
            tok = normalize_token(test_set.treebank_name, current_tok, ud_eval=pipeline._ud_eval)
            if "\t" in tok:
                raise AssertionError(tok)
            if len(tok) <= 0:
                current_tok = ""
                continue
            additional_info = {
                "current_len": len(flat_tokens),
                DSPAN: (local_position - len(tok), local_position),
            }
            current_sent.append((tok, wp_label, additional_info))
            current_tok = ""
            if wp_label == 2 or wp_label == 4:
                flat_tokens += get_output_sentence(current_sent)
                current_sent = []

    if len(current_tok):
        tok = normalize_token(test_set.treebank_name, current_tok, ud_eval=pipeline._ud_eval)
        if "\t" in tok:
            raise AssertionError(tok)
        if len(tok) > 0:
            additional_info = {
                "current_len": len(flat_tokens),
                DSPAN: (local_position - len(tok), local_position),
            }
            current_sent.append((tok, 2, additional_info))

    if len(current_sent):
        flat_tokens += get_output_sentence(current_sent)

    grouped_tokens: List[List[Dict[str, Any]]] = [[] for _ in combined_spans]
    span_index = 0
    for token in flat_tokens:
        if not isinstance(token, dict):
            continue
        span_value = token.get(DSPAN) or token.get(SSPAN)
        if not isinstance(span_value, (list, tuple)) or len(span_value) < 2:
            continue
        try:
            token_start = int(span_value[0])
            token_end = int(span_value[1])
        except (TypeError, ValueError):
            continue
        while span_index < len(combined_spans) and token_start >= combined_spans[span_index][1]:
            span_index += 1
        if span_index >= len(combined_spans):
            break
        record_start, record_end, _record = combined_spans[span_index]
        if token_end <= record_start or token_start >= record_end:
            continue
        local_start = max(0, token_start - record_start)
        local_end = min(record_end - record_start, token_end - record_start)
        if local_end <= local_start:
            continue
        token_copy = dict(token)
        token_copy[DSPAN] = (local_start, local_end)
        token_copy[SSPAN] = (local_start, local_end)
        grouped_tokens[span_index].append(token_copy)

    tokenized_doc: List[Dict[str, Any]] = []
    for span_index, (_combined_start, _combined_end, record) in enumerate(combined_spans):
        tokens = grouped_tokens[span_index]
        if not tokens:
            continue
        for i, token in enumerate(tokens):
            token[ID] = i + 1
        context = record.get("context")
        if context is not None and getattr(context, "changed", False):
            tokens = _remap_trankit_offsets_to_original(tokens, context)
        tokens = _shift_trankit_offsets(tokens, int(record["start"]))
        if not isinstance(tokens, list) or not tokens:
            continue
        tokenized_doc.append(
            {
                "id": len(tokenized_doc) + 1,
                "text": record["chunk"],
                "tokens": tokens,
                "dspan": (record["start"], record["end"]),
            }
        )

    if tbname2training_id[config.treebank_name] % 2 == 1:
        tokenized_doc = pipeline._mwt_expand(tokenized_doc)
    torch.cuda.empty_cache()
    return tokenized_doc


def _coerce_chunk_offset(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _map_chunk_span_value(value: Any, offset_map: List[Optional[int]]) -> Optional[List[Any]]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        start = int(value[0])
        end = int(value[1])
    except (TypeError, ValueError):
        return None
    if end < start:
        end = start
    if not offset_map:
        return None

    n = len(offset_map)
    start = max(0, min(start, n))
    end = max(start, min(end, n))

    mapped_start: Optional[int] = None
    for i in range(start, n):
        mapped_start = _coerce_chunk_offset(offset_map[i])
        if mapped_start is not None:
            break

    mapped_end: Optional[int] = None
    for i in range(min(end, n) - 1, -1, -1):
        mapped_end = _coerce_chunk_offset(offset_map[i])
        if mapped_end is not None:
            mapped_end += 1
            break

    if mapped_start is None and mapped_end is None:
        return None
    if mapped_start is None:
        mapped_start = max(0, int(mapped_end or 0) - 1)
    if mapped_end is None:
        mapped_end = int(mapped_start) + 1
    if mapped_end < mapped_start:
        mapped_end = mapped_start

    mapped = list(value)
    mapped[0] = int(mapped_start)
    mapped[1] = int(mapped_end)
    return mapped


def _remap_trankit_offsets_with_offset_map(node: Any, offset_map: List[Optional[int]]) -> Any:
    if isinstance(node, dict):
        out: Dict[str, Any] = {}
        for key, value in node.items():
            if key in {"span", "dspan"}:
                mapped = _map_chunk_span_value(value, offset_map)
                if mapped is not None:
                    out[key] = mapped
                    continue
            out[key] = _remap_trankit_offsets_with_offset_map(value, offset_map)
        return out
    if isinstance(node, list):
        return [_remap_trankit_offsets_with_offset_map(item, offset_map) for item in node]
    return node


def _run_trankit_with_manual_sentence_segmentation(
    pipeline,
    text: str,
    lang_code: str,
    strip_punctuation_after_segmentation: bool = False,
) -> dict:
    if not text:
        return {"text": text, "sentences": []}

    tokenized_doc = _tokenize_manual_sentence_spans_batched(
        pipeline,
        text,
        lang_code,
        strip_punctuation_after_segmentation=strip_punctuation_after_segmentation,
    )

    if not tokenized_doc:
        return {"text": text, "sentences": []}

    tagged_doc = pipeline._posdep_doc(tokenized_doc)
    out = pipeline._lemmatize_doc(tagged_doc)
    if pipeline._config.active_lang in getattr(pipeline, "_ner_model", {}):
        out = pipeline._ner_doc(out)
    return {"text": text, "sentences": out, "lang": pipeline.active_lang}


def run_trankit(
    text: str,
    lang_code: str,
    trankit_name_override: str = "",
    manual_sentence_segmentation: bool = False,
    strip_punctuation_after_manual_sentence_segmentation: bool = False,
) -> dict:
    """Thread-safe Trankit call. Acquires lock, switches language, runs."""
    lang_info = LANGUAGE_REGISTRY[lang_code]
    trankit_name = trankit_name_override or lang_info["trankit_name"]
    wait_started = time.perf_counter()
    _trankit_lock.acquire()
    wait_ms = (time.perf_counter() - wait_started) * 1000.0
    run_started = time.perf_counter()
    try:
        _trankit_pipeline.set_active(trankit_name)
        with _trankit_inference_context():
            if manual_sentence_segmentation and lang_code in _MANUAL_SENTENCE_STOP_CHARS:
                return _run_trankit_with_manual_sentence_segmentation(
                    _trankit_pipeline,
                    text,
                    lang_code,
                    strip_punctuation_after_segmentation=strip_punctuation_after_manual_sentence_segmentation,
                )

            if lang_code == "lzh":
                return _run_trankit_lzh_sentencewise(_trankit_pipeline, text)

            if lang_code == "ar":
                tokenizer_path = get_tokenizer_path(lang_code)
                if tokenizer_path == "cameltools":
                    from camel_tools_arabic_tokenizer import (
                        run_trankit_with_camel_tools_tokenization,
                    )

                    return run_trankit_with_camel_tools_tokenization(_trankit_pipeline, text)
                if tokenizer_path != "native":
                    raise RuntimeError(f"Unsupported Arabic tokenizer_path: {tokenizer_path!r}")

            return _trankit_pipeline(text)
    finally:
        run_ms = (time.perf_counter() - run_started) * 1000.0
        _trankit_lock.release()
        _record_trankit_timing(lang_code, wait_ms, run_ms)


def _run_trankit_chunk_locked(
    pipeline,
    text: str,
    lang_code: str,
    manual_sentence_segmentation: bool,
    strip_punctuation_after_manual_sentence_segmentation: bool,
) -> dict:
    if manual_sentence_segmentation and lang_code in _MANUAL_SENTENCE_STOP_CHARS:
        return _run_trankit_with_manual_sentence_segmentation(
            pipeline,
            text,
            lang_code,
            strip_punctuation_after_segmentation=strip_punctuation_after_manual_sentence_segmentation,
        )

    if lang_code == "lzh":
        return _run_trankit_lzh_sentencewise(pipeline, text)

    if lang_code == "ar":
        tokenizer_path = get_tokenizer_path(lang_code)
        if tokenizer_path == "cameltools":
            from camel_tools_arabic_tokenizer import run_trankit_with_camel_tools_tokenization

            return run_trankit_with_camel_tools_tokenization(pipeline, text)
        if tokenizer_path != "native":
            raise RuntimeError(f"Unsupported Arabic tokenizer_path: {tokenizer_path!r}")

    return pipeline(text)


def _tokenized_sentences_from_doc(tokenized_doc: Any, fallback_text: str) -> List[Dict[str, Any]]:
    if not isinstance(tokenized_doc, dict):
        return []
    sentences = tokenized_doc.get("sentences")
    if isinstance(sentences, list):
        return [sent for sent in sentences if isinstance(sent, dict)]
    tokens = tokenized_doc.get("tokens")
    if isinstance(tokens, list) and tokens:
        return [
            {
                "id": 1,
                "text": fallback_text,
                "tokens": tokens,
                "dspan": (0, len(fallback_text)),
            }
        ]
    return []


def _tokenize_trankit_chunk_locked(
    pipeline,
    text: str,
    lang_code: str,
    manual_sentence_segmentation: bool,
    strip_punctuation_after_manual_sentence_segmentation: bool,
) -> List[Dict[str, Any]]:
    if not text or not text.strip():
        return []

    if manual_sentence_segmentation and lang_code in _MANUAL_SENTENCE_STOP_CHARS:
        return _tokenize_manual_sentence_spans_batched(
            pipeline,
            text,
            lang_code,
            strip_punctuation_after_segmentation=strip_punctuation_after_manual_sentence_segmentation,
        )

    if lang_code == "ar":
        tokenizer_path = get_tokenizer_path(lang_code)
        if tokenizer_path != "native":
            raise RuntimeError(
                "Geometry chunk boundaries require Trankit's native tokenizer; "
                f"unsupported Arabic tokenizer_path: {tokenizer_path!r}"
            )

    return _tokenized_sentences_from_doc(pipeline.tokenize(text), text)


def run_trankit_chunk_boundaries(
    full_text: str,
    chunks: List[Dict[str, Any]],
    lang_code: str,
    trankit_name_override: str = "",
    manual_sentence_segmentation: bool = False,
    strip_punctuation_after_manual_sentence_segmentation: bool = False,
) -> dict:
    """
    Run one document with geometry-imposed chunk boundaries.

    This keeps boundary hints out of the source text: each geometry chunk is
    tokenized independently, the tokenized sentences are merged, and the heavy
    POS/dependency/lemma/NER stages run once over that merged document.
    """
    lang_info = LANGUAGE_REGISTRY[lang_code]
    trankit_name = trankit_name_override or lang_info["trankit_name"]
    tokenized_doc: List[Dict[str, Any]] = []

    wait_started = time.perf_counter()
    _trankit_lock.acquire()
    wait_ms = (time.perf_counter() - wait_started) * 1000.0
    run_started = time.perf_counter()
    try:
        _trankit_pipeline.set_active(trankit_name)
        with _trankit_inference_context():
            for raw_chunk in chunks or []:
                chunk_text = str((raw_chunk or {}).get("text") or "")
                if not chunk_text.strip():
                    continue

                offset_map = [
                    _coerce_chunk_offset(v) for v in list((raw_chunk or {}).get("offset_map") or [])
                ]
                if not offset_map:
                    start = _coerce_chunk_offset((raw_chunk or {}).get("start")) or 0
                    offset_map = [start + i for i in range(len(chunk_text))]
                if len(offset_map) < len(chunk_text):
                    offset_map.extend([None] * (len(chunk_text) - len(offset_map)))
                elif len(offset_map) > len(chunk_text):
                    offset_map = offset_map[: len(chunk_text)]

                chunk_sentences = _tokenize_trankit_chunk_locked(
                    _trankit_pipeline,
                    chunk_text,
                    lang_code,
                    manual_sentence_segmentation,
                    strip_punctuation_after_manual_sentence_segmentation,
                )
                remapped_doc = _remap_trankit_offsets_with_offset_map(
                    {"sentences": chunk_sentences},
                    offset_map,
                )
                sentences = remapped_doc.get("sentences") if isinstance(remapped_doc, dict) else []
                if not isinstance(sentences, list):
                    continue
                for sent in sentences:
                    if not isinstance(sent, dict):
                        continue
                    merged = dict(sent)
                    merged["id"] = len(tokenized_doc) + 1
                    tokenized_doc.append(merged)

            if not tokenized_doc:
                return {"text": full_text, "sentences": [], "lang": trankit_name, "chunked": True}

            tagged_doc = _trankit_pipeline._posdep_doc(tokenized_doc)
            out = _trankit_pipeline._lemmatize_doc(tagged_doc)
            if _trankit_pipeline._config.active_lang in getattr(
                _trankit_pipeline, "_ner_model", {}
            ):
                out = _trankit_pipeline._ner_doc(out)
    finally:
        run_ms = (time.perf_counter() - run_started) * 1000.0
        _trankit_lock.release()
        _record_trankit_timing(lang_code, wait_ms, run_ms)

    return {
        "text": full_text,
        "sentences": out,
        "lang": trankit_name,
        "chunked": True,
        "chunk_mode": "boundary_tokenized",
    }


def run_trankit_chunked(
    full_text: str,
    chunks: List[Dict[str, Any]],
    lang_code: str,
    trankit_name_override: str = "",
    manual_sentence_segmentation: bool = False,
    strip_punctuation_after_manual_sentence_segmentation: bool = False,
) -> dict:
    """
    RETIRED reference path.

    This runs a full Trankit pass per geometry chunk and merges the finished
    documents. The active lookup path now uses run_trankit_chunk_boundaries()
    so chunk boundaries are applied before POS/dependency/lemma/NER.
    """
    lang_info = LANGUAGE_REGISTRY[lang_code]
    trankit_name = trankit_name_override or lang_info["trankit_name"]
    merged_sentences: List[Dict[str, Any]] = []

    with _trankit_lock:
        _trankit_pipeline.set_active(trankit_name)
        for raw_chunk in chunks or []:
            chunk_text = str((raw_chunk or {}).get("text") or "")
            if not chunk_text.strip():
                continue
            offset_map = [
                _coerce_chunk_offset(v) for v in list((raw_chunk or {}).get("offset_map") or [])
            ]
            if not offset_map:
                start = _coerce_chunk_offset((raw_chunk or {}).get("start")) or 0
                offset_map = [start + i for i in range(len(chunk_text))]
            if len(offset_map) < len(chunk_text):
                offset_map.extend([None] * (len(chunk_text) - len(offset_map)))
            elif len(offset_map) > len(chunk_text):
                offset_map = offset_map[: len(chunk_text)]

            chunk_doc = _run_trankit_chunk_locked(
                _trankit_pipeline,
                chunk_text,
                lang_code,
                manual_sentence_segmentation,
                strip_punctuation_after_manual_sentence_segmentation,
            )
            remapped_doc = _remap_trankit_offsets_with_offset_map(chunk_doc, offset_map)
            sentences = remapped_doc.get("sentences") if isinstance(remapped_doc, dict) else []
            if not isinstance(sentences, list):
                continue
            for sent in sentences:
                if not isinstance(sent, dict):
                    continue
                merged = dict(sent)
                merged["id"] = len(merged_sentences) + 1
                merged_sentences.append(merged)

    return {
        "text": full_text,
        "sentences": merged_sentences,
        "lang": trankit_name,
        "chunked": True,
    }


def _run_trankit_lzh_sentencewise(pipeline, text: str) -> dict:
    """Run Classical Chinese with Trankit's native sentence segmentation."""
    if not text:
        return {"text": text, "sentences": []}
    return pipeline(text)


# ---------------------------------------------------------------------------
# Dictionaries — one per language, loaded at startup
# ---------------------------------------------------------------------------


def get_tsv_path(lang_code: str) -> Optional[Path]:
    """Return the TSV dictionary path for a language, or None."""
    info = LANGUAGE_REGISTRY.get(lang_code)
    if not info:
        return None
    dict_file = info.get("dict_file", "")
    if not dict_file or not dict_file.endswith(".tsv"):
        return None
    p = APP_ROOT / dict_file
    return p if p.exists() else None


def get_tokenizer_path(lang_code: str) -> str:
    """Return the active tokenizer path for a language."""
    info = LANGUAGE_REGISTRY.get(lang_code)
    if not info:
        return "native"
    return str(info.get("tokenizer_path", "native") or "native").strip().lower()


# ---------------------------------------------------------------------------
# Hooks — one per language, loaded at startup
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Master init — call once at startup
# ---------------------------------------------------------------------------


def init_all():
    """Initialize the shared NLP pipeline."""
    init_trankit()
