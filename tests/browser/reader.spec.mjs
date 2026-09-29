import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/*', (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== '127.0.0.1' && url.protocol !== 'data:') return route.abort();
    return route.continue();
  });
});

test('reader boots with its real template and renders a synthetic lookup', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/reader');
  await page.waitForFunction(() => !!window.LEReaderShowcaseApi);
  const result = await page.evaluate(async () => {
    const payload = {
      ok: true,
      language: 'en',
      q: 'Read books.',
      display_text: 'Read books.',
      segments: ['Read', 'books', '.'],
      results_by_seg: [
        { text: 'Read', entries: [], upos: 'VERB' },
        { text: 'books', entries: [], upos: 'NOUN' },
        { text: '.', entries: [], upos: 'PUNCT' }
      ],
      entry_store: {},
      offsets: [
        [0, 4],
        [5, 10],
        [10, 11]
      ],
      ud_overlay: {
        sentences: [[0, 3]],
        tokens: [
          { id: 1, head: 0, deprel: 'root', upos: 'VERB' },
          { id: 2, head: 1, deprel: 'obj', upos: 'NOUN' },
          { id: 3, head: 1, deprel: 'punct', upos: 'PUNCT' }
        ]
      }
    };
    return window.LEReaderShowcaseApi.renderPayload(payload, { lang: 'en', text: payload.q });
  });
  expect(result).toBe(true);
  await expect(page.locator('#renderedText')).toContainText('Read');
  await expect(page.locator('#renderedText')).toContainText('books');
  expect(errors).toEqual([]);
});

test('snapshot text remains selectable inside an inert iframe', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/reader');
  const result = await page.evaluate(async () => {
    const host = document.createElement('div');
    document.body.append(host);
    const renderer = window.DocRenderWebSnapshotRenderer;
    const state = renderer.render(
      host,
      {
        kind: 'webSnapshot',
        html: '<!doctype html><html><body><p id="sample">Synthetic snapshot text</p><script>parent.__escaped=true<\/script></body></html>'
      },
      { width: 640, height: 480, inspectorEnabled: true }
    );
    await state.ready;
    const range = state.doc.createRange();
    range.selectNodeContents(state.doc.querySelector('#sample'));
    const selection = state.win.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    return {
      text: renderer.getSelectedText(state),
      escaped: !!window.__escaped,
      sandbox: state.iframe.getAttribute('sandbox')
    };
  });
  expect(result.text).toContain('Synthetic snapshot text');
  expect(result.escaped).toBe(false);
  expect(result.sandbox).not.toContain('allow-scripts');
  expect(errors).toEqual([]);
});

test('dictionary bundles support classic worker imports and correlated queries', async ({ page }) => {
  await page.goto('/reader');
  const result = await page.evaluate(async () => {
    const base = location.origin;
    const code = `self.window=self;
      importScripts(${JSON.stringify(base + '/static/dictionary_normalization_layer.js')}, ${JSON.stringify(base + '/static/dictionary_engine_hybrid.js')}, ${JSON.stringify(base + '/static/dictionary_client_hybrid.js')});
      const engine=new DictionaryEngine('en');
      engine.loadFromRows([{headword:'book',pos:'noun',glosses:'bound pages'}]);
      self._workerEngines={'en|fixture':engine};
      self.postMessage({type:'ready'});`;
    const url = URL.createObjectURL(new Blob([code], { type: 'text/javascript' }));
    const worker = new Worker(url);
    try {
      return await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(Error('Worker query timed out')), 8000);
        worker.onerror = (error) => {
          clearTimeout(timer);
          reject(Error(error.message));
        };
        worker.onmessage = ({ data }) => {
          if (data.type === 'ready')
            worker.postMessage({
              type: 'has_word',
              requestId: 41,
              engineKey: 'en|fixture',
              langCode: 'en',
              word: 'book'
            });
          if (data.type === 'query_result') {
            clearTimeout(timer);
            resolve(data);
          }
        };
      });
    } finally {
      worker.terminate();
      URL.revokeObjectURL(url);
    }
  });
  expect(result.requestId).toBe(41);
  expect(result.payload.found).toBe(true);
  expect(result.error).toBeUndefined();
});

test('PDF viewer loads a synthetic document, publishes readiness and finds text', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.addInitScript(() => {
    window.fixtureMessages = [];
    window.addEventListener('message', (event) => {
      if (event.data?.source === 'pdfjs-iframe') window.fixtureMessages.push(event.data);
    });
  });
  await page.goto('/static/pdfjs_iframe_viewer.html?pdf_url=%2Ffixture.pdf&session_id=fixture');
  await page.waitForFunction(() => window.fixtureMessages.some((message) => message.type === 'pdfjs-ready'));
  await expect(page.locator('#pageCornerBadge')).toContainText('1 / 1');
  await page.locator('#pdfSearchInput').fill('books');
  await page.locator('#pdfSearchInput').press('Enter');
  await expect(page.locator('#pdfSearchCount')).toContainText('1');
  const messages = await page.evaluate(() => window.fixtureMessages);
  expect(messages.find((message) => message.type === 'pdfjs-ready')).toMatchObject({
    sessionId: 'fixture',
    numPages: 1
  });
  expect(errors).toEqual([]);
});
