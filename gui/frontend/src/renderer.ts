// renderer.ts — Renders PipelineResult into the output DOM area

import { marked } from 'marked';
import { insertHeatmaps } from './heatmap';
import type { PipelineResult, IntentType } from './types';

// Configure marked with custom renderer for code blocks
const renderer = new marked.Renderer();

// Custom code block renderer — wraps in styled container with language label + copy
renderer.code = function (code: string, lang?: string): string {
  const language = lang || 'text';
  const langLabel = language.toUpperCase();
  return `<div class="code-block-wrapper">
    <div class="code-block-header">
      <span class="code-lang-label">${esc(langLabel)}</span>
      <button class="code-copy-btn" aria-label="Copy code">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
          <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="1.8"/>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        </svg>
        <span>Copy</span>
      </button>
    </div>
    <pre><code class="language-${esc(language)}">${code}</code></pre>
  </div>`;
};

marked.setOptions({ gfm: true, breaks: false, renderer });

const INTENT_META: Record<IntentType, { label: string; cls: string }> = {
  GENE_PROFILE:  { label: 'Gene Profile',  cls: 'intent-gene-profile'  },
  GENE_LIST:     { label: 'Gene List',     cls: 'intent-gene-list'     },
  EXPRESSION:    { label: 'Expression',    cls: 'intent-expression'    },
  SEQUENCE:      { label: 'Sequence',      cls: 'intent-sequence'      },
  STRESS_LABEL:  { label: 'Stress Label',  cls: 'intent-stress-label'  },
  COMPARISON:    { label: 'Comparison',    cls: 'intent-comparison'    },
  OUT_OF_SCOPE:  { label: 'Out of Scope',  cls: 'intent-out-of-scope'  },
};

export function renderResult(container: HTMLElement, result: PipelineResult): void {
  container.innerHTML = '';

  if (result.error) {
    container.innerHTML = `<div class="result-error"><span class="error-icon">⚠</span>${esc(result.error)}</div>`;
    return;
  }

  const intentMeta = INTENT_META[result.intent] ?? { label: result.intent, cls: '' };

  const metaBar = document.createElement('div');
  metaBar.className = 'result-meta-bar';
  metaBar.innerHTML = `
    <span class="intent-badge ${intentMeta.cls}">${intentMeta.label}</span>
    ${result.gene_id ? `<span class="gene-badge">${esc(result.gene_id)}</span>` : ''}
    ${result.output_format && result.output_format !== 'NONE'
      ? `<span class="format-badge">${esc(result.output_format)}</span>` : ''}
    ${result.validation_applied
      ? `<span class="validated-badge" title="AI-3 Validator applied corrections">Validated ✓</span>`
      : `<span class="unmodified-badge" title="Output passed validation unchanged">Passed ✓</span>`}
    ${result.agents_used?.length
      ? `<span class="agents-badge">Agents: ${result.agents_used.map(esc).join(' · ')}</span>` : ''}
  `;

  const body = document.createElement('div');
  body.className = result.intent === 'OUT_OF_SCOPE' ? 'result-body out-of-scope' : 'result-body';

  if (result.intent === 'OUT_OF_SCOPE') {
    const banner = document.createElement('div');
    banner.className = 'oos-banner';
    banner.innerHTML = '<span class="oos-banner-icon">⚠️</span>Out of scope — this pipeline answers chickpea stress-gene questions only';
    body.appendChild(banner);
    // Separator between banner and body text
    const hr = document.createElement('hr');
    hr.className = 'oos-sep';
    body.appendChild(hr);
  }

  const mdDiv = document.createElement('div');
  mdDiv.innerHTML = marked.parse(result.llm_response) as string;
  body.appendChild(mdDiv);

  // Style tables + Log2FC coloring
  body.querySelectorAll('table').forEach((tbl) => {
    tbl.classList.add('data-table');
    const wrapper = document.createElement('div');
    wrapper.className = 'table-wrapper';
    tbl.parentNode?.insertBefore(wrapper, tbl);
    wrapper.appendChild(tbl);
    _colorLog2FC(tbl as HTMLTableElement);
  });

  // Wire up code block copy buttons
  body.querySelectorAll('.code-copy-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const wrapper = btn.closest('.code-block-wrapper');
      const codeEl = wrapper?.querySelector('code');
      if (codeEl) {
        const text = codeEl.textContent ?? '';
        _copyCodeBlock(text, btn as HTMLButtonElement);
      }
    });
  });

  _highlightGenes(body);
  _linkifyGeoAccessions(body);

  // Insert heatmaps after expression tables (fallback to bottom if after-table fails)
  try {
    insertHeatmaps(body, true);
  } catch {
    try { insertHeatmaps(body, false); } catch { /* silent fallback */ }
  }

  const card = document.createElement('div');
  card.className = 'result-card';
  card.appendChild(metaBar);
  card.appendChild(body);
  container.appendChild(card);

  // Copy button — OUTSIDE the card, below it (ghost style, no border-top on card)
  const copyRow = document.createElement('div');
  copyRow.className = 'result-copy-row';
  const copyBtn = document.createElement('button');
  copyBtn.className = 'copy-btn';
  copyBtn.innerHTML = `
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
      <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="1.8"/>
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
    </svg>
    <span>Copy response</span>
  `;
  copyBtn.addEventListener('click', () => _copyText(result.llm_response, copyBtn));
  copyRow.appendChild(copyBtn);
  container.appendChild(copyRow);   // after card, not inside

  card.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

export function renderError(container: HTMLElement, message: string): void {
  container.innerHTML = `<div class="result-error"><span class="error-icon">⚠</span>${esc(message)}</div>`;
}

/** Renders a right-aligned user query bubble into container. */
export function renderUserBubble(container: HTMLElement, query: string): void {
  const el = document.createElement('div');
  el.className = 'user-bubble';
  el.innerHTML = `<div class="user-bubble-inner">${esc(query)}</div>`;
  container.appendChild(el);
}

// Copy text to clipboard and show a brief confirmation
function _copyText(text: string, btn: HTMLButtonElement): void {
  navigator.clipboard.writeText(text).then(() => {
    const span = btn.querySelector('span');
    const prev = span?.textContent ?? '';
    if (span) span.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => {
      if (span) span.textContent = prev;
      btn.classList.remove('copied');
    }, 1800);
  }).catch(() => {
    // Fallback for non-secure contexts
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  });
}

// Copy code block content
function _copyCodeBlock(text: string, btn: HTMLButtonElement): void {
  navigator.clipboard.writeText(text).then(() => {
    const span = btn.querySelector('span');
    if (span) span.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => {
      if (span) span.textContent = 'Copy';
      btn.classList.remove('copied');
    }, 1800);
  }).catch(() => {});
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Colorize Log2FC columns: ≥+1.5 green, ≤−1.5 red, else amber.
 * Threshold matches pipeline rules.md.
 */
function _colorLog2FC(tbl: HTMLTableElement): void {
  const headerRow = tbl.querySelector('tr');
  if (!headerRow) return;
  const headers = Array.from(headerRow.querySelectorAll('th'));
  const col = headers.findIndex((th) => /log2/i.test(th.textContent ?? ''));
  if (col < 0) return;
  tbl.querySelectorAll('tbody tr').forEach((row) => {
    const cell = row.querySelectorAll('td')[col] as HTMLTableCellElement | undefined;
    if (!cell) return;
    const val = parseFloat(cell.textContent?.trim() ?? '');
    if (isNaN(val)) return;
    cell.classList.add(val >= 1.5 ? 'log2fc-up' : val <= -1.5 ? 'log2fc-down' : 'log2fc-ns');
    cell.textContent = val > 0 ? `+${cell.textContent?.trim()}` : cell.textContent?.trim() ?? '';
  });
}

const GENE_RE = /\b(Ca_\d{5})\b/g;

function _highlightGenes(root: HTMLElement): void {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  let node: Node | null;
  while ((node = walker.nextNode())) {
    GENE_RE.lastIndex = 0;
    if (GENE_RE.test((node as Text).textContent ?? '')) nodes.push(node as Text);
  }
  for (const textNode of nodes) {
    GENE_RE.lastIndex = 0;
    const text = textNode.textContent ?? '';
    const frag = document.createDocumentFragment();
    let last = 0; let m: RegExpExecArray | null;
    while ((m = GENE_RE.exec(text)) !== null) {
      if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
      const span = document.createElement('span');
      span.className = 'gene-inline';
      span.textContent = m[1];
      frag.appendChild(span);
      last = m.index + m[0].length;
    }
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
    textNode.parentNode?.replaceChild(frag, textNode);
  }
}

const GEO_RE = /\b(GSE\d+|PRJNA\d+)\b/g;

/** Turn GEO/BioProject accession IDs into clickable NCBI links. */
function _linkifyGeoAccessions(root: HTMLElement): void {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  let node: Node | null;
  while ((node = walker.nextNode())) {
    GEO_RE.lastIndex = 0;
    if (GEO_RE.test((node as Text).textContent ?? '')) nodes.push(node as Text);
  }
  for (const textNode of nodes) {
    // Skip if parent is already a link
    if (textNode.parentElement?.tagName === 'A') continue;
    GEO_RE.lastIndex = 0;
    const text = textNode.textContent ?? '';
    const frag = document.createDocumentFragment();
    let last = 0; let m: RegExpExecArray | null;
    while ((m = GEO_RE.exec(text)) !== null) {
      if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
      const accession = m[1];
      const link = document.createElement('a');
      link.className = 'geo-accession-link';
      link.textContent = accession;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      if (accession.startsWith('GSE')) {
        link.href = `https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=${accession}`;
      } else {
        link.href = `https://www.ncbi.nlm.nih.gov/bioproject/${accession}`;
      }
      link.title = `View ${accession} on NCBI`;
      frag.appendChild(link);
      last = m.index + m[0].length;
    }
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
    textNode.parentNode?.replaceChild(frag, textNode);
  }
}

function esc(s: string): string {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
