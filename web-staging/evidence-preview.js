import {getDocument, GlobalWorkerOptions} from './assets/pdfjs/build/pdf.mjs';

GlobalWorkerOptions.workerSrc = new URL('./assets/pdfjs/build/pdf.worker.mjs', import.meta.url).href;
const el = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const source = params.get('document') || '';
const snapshot = /^\/state-snapshots\/[a-f0-9]{64}\.pdf$/.test(source);
const history = /^\/state-evidence\/[a-f0-9]{64}\/search-history\.pdf$/.test(source);
let pdf, original, pageNumber = 1, busy = false;
const title = snapshot ? 'State Snapshot' : 'Names Searched';
const setStatus = value => { el('status').textContent = value; };
function controls() {
  el('previous').disabled = busy || !pdf || pageNumber <= 1;
  el('next').disabled = busy || !pdf || pageNumber >= pdf.numPages;
  el('download').disabled = !original;
  el('print').disabled = busy || !pdf;
}
async function paint(page, canvas, scale = 1.5) {
  const viewport = page.getViewport({scale});
  if (viewport.width * viewport.height > 16000000) throw new Error('This page is too large to preview. Use Download to open the original PDF.');
  canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height);
  await page.render({canvasContext: canvas.getContext('2d'), viewport}).promise;
  return viewport;
}
async function show(number) {
  if (busy || !pdf) return;
  busy = true; controls();
  try {
    await paint(await pdf.getPage(number), el('page'));
    pageNumber = number; el('pageNumber').textContent = `Page ${number} of ${pdf.numPages}`;
    setStatus('Viewing the saved PDF. Download and Print are optional.');
  } catch (error) { setStatus(error.message || 'The saved PDF could not be displayed.'); }
  finally { busy = false; controls(); }
}
el('previous').addEventListener('click', () => show(pageNumber - 1));
el('next').addEventListener('click', () => show(pageNumber + 1));
el('download').addEventListener('click', () => {
  if (!original) return;
  const url = URL.createObjectURL(new Blob([original], {type: 'application/pdf'}));
  const link = document.createElement('a'); link.href = url; link.download = `${title.replaceAll(' ', '-')}.pdf`;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
});
el('print').addEventListener('click', async () => {
  if (busy || !pdf) return;
  busy = true; controls(); const host = el('printPages'); host.replaceChildren();
  const styles = document.createElement('style'); document.head.appendChild(styles); let pixels = 0;
  try {
    setStatus('Preparing all PDF pages for printing…');
    for (let n = 1; n <= pdf.numPages; n++) {
      const page = await pdf.getPage(n), viewport = page.getViewport({scale: 1.5});
      pixels += viewport.width * viewport.height;
      if (pixels > 64000000) throw new Error('This PDF is too large for browser printing. Download the original PDF to print it.');
      const article = document.createElement('article'), canvas = document.createElement('canvas');
      const dimensions = page.getViewport({scale: 1});
      article.style.page = `pdf${n}`; styles.textContent += `@page pdf${n}{size:${dimensions.width}pt ${dimensions.height}pt;margin:0}`;
      article.style.width = `${dimensions.width}pt`; article.style.height = `${dimensions.height}pt`;
      article.appendChild(canvas); host.appendChild(article); await paint(page, canvas);
    }
    window.print(); setStatus('Viewing the saved PDF.');
  } catch (error) { setStatus(error.message || 'The saved PDF could not be prepared for printing.'); }
  finally { host.replaceChildren(); styles.remove(); busy = false; controls(); }
});
try {
  if (params.size !== 1 || !snapshot && !history) throw new Error('This saved-PDF link is invalid. Return to the result and open its evidence link.');
  el('title').textContent = title; document.title = `${title} — CharityClarity`;
  const response = await fetch(source, {credentials: 'same-origin', cache: 'no-store'});
  if (!response.ok || !(response.headers.get('Content-Type') || '').includes('application/pdf')) throw new Error('The saved PDF is unavailable. Return to CharityClarity, unlock it if needed, and try again.');
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.byteLength > 25000000 || new TextDecoder().decode(bytes.subarray(0, 5)) !== '%PDF-') throw new Error('The saved PDF could not be previewed.');
  original = bytes.slice(); controls();
  pdf = await getDocument({data: bytes, isEvalSupported: false, enableXfa: false,
    cMapUrl: './assets/pdfjs/cmaps/', cMapPacked: true, standardFontDataUrl: './assets/pdfjs/standard_fonts/', wasmUrl: './assets/pdfjs/wasm/'}).promise;
  if (pdf.numPages > 100) { pdf = null; throw new Error('This PDF is too long to preview. Download the original PDF to view it.'); }
  await show(1);
} catch (error) { setStatus(error.message || 'The saved PDF could not be opened.'); controls(); }
