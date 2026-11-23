// SPDX-License-Identifier: Apache-2.0
// Required customer-document build: render the reviewed Markdown and diagrams.
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
const args = process.argv.slice(2);
let executablePath;
let python = process.env.NTK_DOCS_PYTHON || 'python';
let ref = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim();
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--browser' && args[i + 1]) executablePath = path.resolve(args[++i]);
  else if (args[i] === '--ref' && args[i + 1]) ref = args[++i];
  else if (args[i] === '--python' && args[i + 1]) python = args[++i];
  else throw new Error('Usage: node build.mjs [--browser PATH] [--ref CURRENT_COMMIT] [--python PATH]');
}
execFileSync(python, ['tools/check_customer_docs.py'], { cwd: root, stdio: 'inherit' });
const reviewPath = path.join(root, 'docs/customer-guide.sources.json');
const review = JSON.parse(await fs.readFile(reviewPath, 'utf8'));
const stem = `NTK-v${review.version}-Customer-Guide-ja`;
const head = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim();
ref = execFileSync('git', ['rev-parse', '--verify', '--end-of-options', `${ref}^{commit}`], { cwd: root, encoding: 'utf8' }).trim();
if (ref !== head) throw new Error('Customer artifacts must reference the checked-out commit');
const dirty = Boolean(execFileSync('git', ['status', '--porcelain'], { cwd: root, encoding: 'utf8' }).trim());
const status = review.status === 'development' ? '開発候補' : '公開済み';
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
const sourceHash = createHash('sha256').update(raw).digest('hex');
const sections = raw.split(/\n<!-- pagebreak -->\n/);
const diagrams = (raw.match(/^```mermaid$/gm) || []).length;
const style = await fs.readFile(path.join(here, 'print.css'), 'utf8');
const pages = sections.map((s, i) => `<article class="sheet ${i === 0 ? 'cover' : ''}">
  <header><b>NYMPH TOOLKIT</b><span>v${escape(review.version)} ${status} · 契約・利用ガイド</span></header>
  <main>${marked.parse(s, { renderer, gfm: true })}</main>
  <footer><span>NTK / ${escape(review.reviewed_on)} / Apache-2.0</span><b>${String(i + 1).padStart(2, '0')} / ${sections.length}</b></footer>
</article>`).join('\n');
const html = `<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="ntk-source-sha256" content="${sourceHash}"><meta name="ntk-reference" content="${ref}"><title>NTK 契約・利用ガイド v${escape(review.version)}</title><style>${style}</style></head><body>${pages}</body></html>`;
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
  await fs.writeFile(path.join(out, stem + '.md'), raw, 'utf8');
  const hashFile = async p => createHash('sha256').update(await fs.readFile(p)).digest('hex');
  const generatorInputs = {};
  for (const name of ['build.mjs', 'print.css', 'package.json', 'pnpm-lock.yaml']) {
    generatorInputs['tools/customer-docs/' + name] = await hashFile(path.join(here, name));
  }
  const files = {};
  for (const ext of ['.md', '.pdf', '.html']) files[stem + ext] = await hashFile(path.join(out, stem + ext));
  const manifest = { source: 'docs/customer-guide.md', reference: ref,
    version: review.version, status: review.status, working_tree_dirty: dirty,
    source_sha256: sourceHash, review_sha256: await hashFile(reviewPath),
    generator_inputs: generatorInputs, files,
    pages: sections.length, diagrams, inspection, browser: browser.version() };
  await fs.writeFile(path.join(out, stem + '.json'), JSON.stringify(manifest, null, 2) + '\n');
  console.log(JSON.stringify({ pages: sections.length, diagrams, output: out, gaps: inspection.pages.map(p => p.availableGap) }));
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}
