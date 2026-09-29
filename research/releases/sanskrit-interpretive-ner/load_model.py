"""CPU inference for native Trankit components (Python 3.10, Trankit 1.1.1)."""
from pathlib import Path
import json
import shutil

import torch
from trankit import Pipeline
from trankit.adapter_transformers import XLMRobertaTokenizer
from trankit.adapter_transformers import configuration_utils, modeling_utils
from trankit.config import Config
from trankit.models.base_models import Multilingual_Embedding
from trankit.models.classifiers import NERClassifier, TokenizerClassifier
from trankit.models.mwt_model import MWTWrapper
from trankit.utils.base_utils import langwithner
from trankit.utils.tbinfo import lang2treebank, treebank2lang, tbname2training_id, supported_langs


def _hub_url(model_id, filename, **_):
    """Replace Trankit's retired Transformers CDN resolver with the HF Hub."""
    return f'https://huggingface.co/{model_id}/resolve/main/{filename}'


def load_model(release_dir=None, cache_dir=None):
    """Return a CPU callable: text for segmentation, list[str] for sentence NER.

    Downloads the upstream XLM-R base encoder on first use. The task checkpoint
    files themselves are read from this release, never from upstream task models.
    """
    release = Path(release_dir or Path(__file__).resolve().parent)
    manifest = json.loads((release / 'artifact-manifest.json').read_text('utf-8'))
    alias = manifest['runtime_alias']
    task = manifest['task']
    if task not in {'tokenize', 'ner'}:
        raise ValueError(f'Unsupported component task: {task}')
    # Sanskrit is an application-trained alias absent from stock Trankit 1.1.1.
    treebank = manifest.get('treebank') or {
        'arabic': 'UD_Arabic-PADT',
        'sanskrit-vedic': 'UD_Vedic_Sanskrit-Vedic',
    }[alias]
    lang2treebank[alias] = treebank
    treebank2lang[treebank] = alias
    if isinstance(supported_langs, set):
        supported_langs.add(alias)
    elif alias not in supported_langs:
        supported_langs.append(alias)
    tbname2training_id[treebank] = 1
    # Keep legacy hashed cache filenames within Windows path-length limits.
    cache = Path(cache_dir or Path.home() / '.cache/conrad-trankit').resolve()
    for item in manifest['files']:
        source = release / item['path']
        target = cache / Path(item['path']).relative_to('weights')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    config = Config()
    config.training = False
    config._cache_dir = str(cache)
    config.device = torch.device('cpu')
    config.active_lang = alias
    config.treebank_name = treebank
    config.max_input_length = 400
    configuration_utils.hf_bucket_url = modeling_utils.hf_bucket_url = _hub_url
    XLMRobertaTokenizer.pretrained_vocab_files_map['vocab_file']['xlm-roberta-base'] = (
        _hub_url('FacebookAI/xlm-roberta-base', 'sentencepiece.bpe.model'))
    config.wordpiece_splitter = XLMRobertaTokenizer.from_pretrained(
        'xlm-roberta-base', cache_dir=str(cache / 'xlm-roberta-base'))

    pipeline = Pipeline.__new__(Pipeline)
    pipeline._config = config
    pipeline._gpu = pipeline._use_gpu = pipeline.auto_mode = pipeline._ud_eval = False
    pipeline.active_lang = alias
    pipeline.added_langs = [alias]
    pipeline._tokbatchsize = 2
    pipeline._tagbatchsize = 12
    pipeline._embedding_layers = Multilingual_Embedding(config).to(config.device).eval()
    pipeline._embedding_weights = pipeline._embedding_layers.state_dict()

    if task == 'tokenize':
        # The trained tokenizer predicts MWT markers for both release languages.
        tbname2training_id[config.treebank_name] |= 1
        pipeline._tokenizer = {alias: TokenizerClassifier(config, config.treebank_name).eval()}
        pipeline._mwt_model = {alias: MWTWrapper(config, config.treebank_name, use_gpu=False)}
        # Match the application's decoding headroom for long compound expansions.
        wrapper = pipeline._mwt_model[alias]
        wrapper.model.args['max_dec_len'] = 400
        wrapper.model.model.max_dec_len = 400

        def predict(text):
            if not isinstance(text, str) or not text.strip():
                raise ValueError('Supply nonempty text in the model training orthography.')
            with torch.inference_mode():
                return pipeline.tokenize(text)
    else:
        vocab = cache / 'xlm-roberta-base' / alias / f'{alias}.ner-vocab.json'
        config.ner_vocabs = {alias: json.loads(vocab.read_text('utf-8'))}
        if isinstance(langwithner, set):
            langwithner.add(alias)
        elif alias not in langwithner:
            langwithner.append(alias)
        pipeline._ner_model = {alias: NERClassifier(config, alias).eval()}

        def predict(tokens):
            if not isinstance(tokens, list) or not tokens or not all(isinstance(t, str) and t for t in tokens):
                raise ValueError('Supply a pretokenized sentence as a nonempty list of strings.')
            with torch.inference_mode():
                return pipeline.ner(tokens, is_sent=True)
    return predict
