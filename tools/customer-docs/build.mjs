// SPDX-License-Identifier: Apache-2.0
// Optional publication tool: render the Markdown source and Mermaid diagrams once.
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { marked, Renderer } from 'marked';
import { chromium } from 'playwright';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..');
const source = path.join(root, 'docs/customer-guide.md');
const out = path.join(root, 'output/pdf');
const stem = 'NTK-Core-v0.9.0-Customer-Guide-ja';
const args = process.argv.slice(2);
let executablePath;
let ref = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim();
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--browser' && args[i + 1]) executablePath = path.resolve(args[++i]);
  else if (args[i] === '--ref' && args[i + 1]) ref = args[++i];
  else throw new Error('Usage: node build.mjs [--browser PATH] [--ref COMMIT_OR_BRANCH]');
}
const require = createRequire(import.meta.url);
const mermaidRoot = path.dirname(require.resolve('mermaid/package.json'));
const vendor = path.join(mermaidRoot, 'dist');
const escape = s => s.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const renderer = new Renderer();
renderer.code = ({ text, lang }) => lang === 'mermaid'
  ? `<figure class="diagram"><pre class="mermaid">${escape(text)}</pre></figure>`
  : `<pre class="code"><code>${escape(text)}</code></pre>`;
renderer.link = ({ href, text }) => {
  let target = href;
  if (!/^(https?:|#)/.test(href)) {
    const relative = path.posix.normalize(path.posix.join('docs', href));
    if (relative.startsWith('../')) throw new Error(`Link outside repository: ${href}`);
    target = `https://github.com/Tao-pyth/nymph-toolkit/blob/${encodeURIComponent(ref)}/${relative}`;
  }
  return `<a href="${escape(target)}">${text}</a>`;
};
const raw = await fs.readFile(source, 'utf8');
const sections = raw.split(/\n<!-- pagebreak -->\n/);
const diagrams = (raw.match(/^```mermaid$/gm) || []).length;
const style = await fs.readFile(path.join(here, 'print.css'), 'utf8');
const pages = sections.map((s, i) => `<article class="sheet ${i === 0 ? 'cover' : ''}">
  <header><b>NYMPH TOOLKIT</b><span>CORE v0.9.0 · 契約・利用ガイド</span></header>
  <main>${marked.parse(s, { renderer, gfm: true })}</main>
  <footer><span>NTK / 2026.11.22 / Apache-2.0</span><b>${String(i + 1).padStart(2, '0')} / ${sections.length}</b></footer>
</article>`).join('\n');
const html = `<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>NTK Core 契約・利用ガイド v0.9.0</title><style>${style}</style></head><body>${pages}</body></html>`;
const server = http.createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    if (pathname === '/') {
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.end(html);
    } else if (pathname.startsWith('/vendor/')) {
      const file = path.resolve(vendor, pathname.slice('/vendor/'.length));
      const relative = path.relative(vendor, file);
      if (relative.startsWith('..') || path.isAbsolute(relative) || !/\.(m?js|json|map)$/.test(file)) {
        res.writeHead(404).end(); return;
      }
      res.setHeader('Content-Type', file.endsWith('.json') ? 'application/json' : 'text/javascript');
      res.end(await fs.readFile(file));
    } else res.writeHead(404).end();
  } catch { res.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
let browser;
try {
  browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
  const page = await browser.newPage({ viewport: { width: 1100, height: 1200 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.evaluate(async () => {
    const { default: mermaid } = await import('/vendor/mermaid.esm.min.mjs');
    mermaid.initialize({
      startOnLoad: false, securityLevel: 'strict', theme: 'base',
      fontFamily: '"Yu Gothic", Meiryo, "Noto Sans CJK JP", sans-serif',
      themeVariables: { fontSize: '16px', primaryColor: '#eaf4f4', primaryTextColor: '#172c3f',
        primaryBorderColor: '#468389', lineColor: '#527785', secondaryColor: '#f3f5fa',
        tertiaryColor: '#fff5e8', noteBkgColor: '#fff5e8', noteTextColor: '#172c3f',
        actorTextColor: '#172c3f', actorBkg: '#eaf4f4', actorBorder: '#468389' },
      flowchart: { htmlLabels: false, curve: 'linear', nodeSpacing: 22, rankSpacing: 30 },
      sequence: { actorMargin: 24, width: 105, height: 32, messageMargin: 12, noteMargin: 4, mirrorActors: false,
        diagramMarginX: 12, diagramMarginY: 10 },
    });
    await mermaid.run({ querySelector: '.mermaid' });
    document.querySelectorAll('.mermaidTooltip').forEach(el => el.remove());
    await document.fonts.ready;
  });
  await page.emulateMedia({ media: 'print' });
  const inspection = await page.evaluate(() => ({
    diagrams: document.querySelectorAll('.diagram svg').length,
    pages: [...document.querySelectorAll('.sheet')].map((sheet, i) => {
      const main = sheet.querySelector('main').getBoundingClientRect();
      const footer = sheet.querySelector('footer').getBoundingClientRect();
      const outside = [...sheet.querySelectorAll('main *')].filter(el => {
        if (el.closest('svg')) return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && (r.right > main.right + 2 || r.left < main.left - 2);
      }).map(el => el.tagName + ':' + el.textContent.slice(0, 50));
      return { page: i + 1, bottom: main.bottom, footerTop: footer.top,
        availableGap: Math.round(footer.top - main.bottom), outside };
    }),
  }));
  if (errors.length || inspection.diagrams !== diagrams || inspection.pages.some(p => p.availableGap < 10 || p.outside.length)) {
    throw new Error('Render/layout validation failed: ' + JSON.stringify({ errors, ...inspection }));
  }
  await fs.mkdir(out, { recursive: true });
  await page.pdf({ path: path.join(out, stem + '.pdf'), preferCSSPageSize: true,
    printBackground: true, tagged: true, outline: true });
  // Inline SVGs stay in this saved HTML; no Mermaid runtime or network is needed.
  await fs.writeFile(path.join(out, stem + '.html'), await page.content(), 'utf8');
  const manifest = { source: 'docs/customer-guide.md', reference: ref,
    source_sha256: createHash('sha256').update(raw).digest('hex'),
    pages: sections.length, diagrams, inspection, browser: browser.version() };
  await fs.writeFile(path.join(out, stem + '.json'), JSON.stringify(manifest, null, 2) + '\n');
  console.log(JSON.stringify({ pages: sections.length, diagrams, output: out, gaps: inspection.pages.map(p => p.availableGap) }));
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}
