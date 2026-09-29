import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import test from 'node:test';
import {
  scriptHost,
  dictionaryContract,
  tagsContract,
  pronunciationContract,
  clientContract
} from './contracts.mjs';

const read = (name) => readFileSync(new URL('../../' + name, import.meta.url), 'utf8');

test('dictionary lookup, forms, compact references, fuzzy tiers and CRUD preserve the published contract', () => {
  const host = scriptHost({
    normalization: read('static/dictionary_normalization_layer.js'),
    engine: read('static/dictionary_engine_hybrid.js')
  });
  assert.deepEqual(dictionaryContract(host), JSON.parse(read('tests/fixtures/dictionary-contract.json')));
});

test('every published tag label and lookup alias survives modularization', () => {
  const host = scriptHost({ tags: read('static/TRANKIT_TAGS.js') });
  const digest = createHash('sha256')
    .update(JSON.stringify(tagsContract(host)))
    .digest('hex');
  assert.equal(digest, read('tests/fixtures/tags-contract.sha256').trim());
});

test('pronunciation rules retain results for every profile table key and span', () => {
  const host = scriptHost({ pronunciation: read('static/grapheme_pronunciation_profiles.js') });
  const digest = createHash('sha256')
    .update(JSON.stringify(pronunciationContract(host)))
    .digest('hex');
  assert.equal(digest, read('tests/fixtures/pronunciation-contract.sha256').trim());
});

test('client TSV parsing, public methods and Unicode lemma alignment preserve their contract', () => {
  const host = scriptHost({
    normalization: read('static/dictionary_normalization_layer.js'),
    engine: read('static/dictionary_engine_hybrid.js'),
    client: read('static/dictionary_client_hybrid.js')
  });
  assert.deepEqual(
    JSON.parse(JSON.stringify(clientContract(host))),
    JSON.parse(read('tests/fixtures/client-contract.json'))
  );
});
