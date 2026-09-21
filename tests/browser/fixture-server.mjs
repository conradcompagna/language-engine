/** Local, synthetic reader host. Never imports the production application. */
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const staticRoot = path.join(root, 'static');
const mime = {
  '.js': 'text/javascript',
  '.mjs': 'text/javascript',
  '.css': 'text/css',
  '.html': 'text/html',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.json': 'application/json'
};

function syntheticPdf() {
  const stream = 'BT /F1 20 Tf 20 60 Td (Read books.) Tj ET';
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 150] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`
  ];
  let pdf = '%PDF-1.4\n';
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets.push(Buffer.byteLength(pdf));
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = Buffer.byteLength(pdf);
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  pdf += offsets
    .slice(1)
    .map((offset) => String(offset).padStart(10, '0') + ' 00000 n \n')
    .join('');
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return pdf;
}
async function readerPage() {
  let page = await fs.readFile(path.join(root, 'templates/reader_jshybrid.html'), 'utf8');
  page = page.replace(
    '{% include "_top_nav.html" %}',
    await fs.readFile(path.join(root, 'templates/_top_nav.html'), 'utf8')
  );
  page = page
    .replace(/{{\s*url_for\('static', filename='([^']+)'\)\s*}}/g, (_, name) => '/static/' + name)
    .replace(/{{\s*mtime\('[^']+'\)\s*}}/g, 'fixture')
    .replace('{{ app_dict_version }}', 'fixture-v1')
    .replace('{{ js_index_urls|tojson }}', '{}')
    .replace('<head>', '<head><script>window.LE_READER_SHOWCASE_MODE=true;</script>');
  if (page.includes('{{') || page.includes('{%'))
    throw Error('Fixture template has unresolved Jinja expressions');
  return page;
}
const server = http.createServer(async (request, response) => {
  try {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    if (pathname === '/fixture.pdf') {
      response.setHeader('Content-Type', 'application/pdf');
      response.end(syntheticPdf());
      return;
    }
    if (pathname === '/' || pathname === '/reader') {
      response.setHeader('Content-Type', 'text/html; charset=utf-8');
      response.end(await readerPage());
      return;
    }
    if (pathname.startsWith('/static/')) {
      const file = path.resolve(staticRoot, decodeURIComponent(pathname.slice('/static/'.length)));
      if (!file.startsWith(staticRoot + path.sep)) throw Error('Invalid path');
      response.setHeader(
        'Content-Type',
        (mime[path.extname(file)] || 'application/octet-stream') + '; charset=utf-8'
      );
      response.end(await fs.readFile(file));
      return;
    }
    const fixtures = {
      '/auth/me': { ok: true, user: { id: 'fixture', email: 'fixture@example.invalid' } },
      '/payments/status': { ok: true, is_subscribed: false },
      '/api/lang_config': { ok: true, language: 'en', code: 'en' },
      '/api/languages': { ok: true, languages: [{ code: 'en', name: 'English' }] },
      '/languages': { ok: true, languages: [{ code: 'en', name: 'English' }] }
    };
    if (pathname in fixtures) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify(fixtures[pathname]));
      return;
    }
    response.writeHead(404, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify({ ok: false, error: 'no_fixture', path: pathname }));
  } catch (error) {
    response.writeHead(404, { 'Content-Type': 'text/plain' });
    response.end('Fixture resource unavailable');
  }
});
server.listen(8791, '127.0.0.1', () => console.log('Fixture reader: http://127.0.0.1:8791'));
