// heatmap.ts — Diverging bar chart (butterfly chart) for Log2FC expression data
// Visually attractive centered visualization with gradient fills.

interface HeatmapEntry {
  tissue: string;
  log2fc: number;
}

// ── Layout constants ─────────────────────────────────────────────────────────
const BAR_HEIGHT = 28;
const BAR_GAP = 6;
const LABEL_WIDTH = 200;
const CHART_HALF = 140;  // half-width of the chart area (left or right from center)
const CENTER_X = LABEL_WIDTH + CHART_HALF + 16;
const TOTAL_WIDTH = CENTER_X + CHART_HALF + 60;
const MAX_FC = 4;  // clamp range

// ── Color helpers ────────────────────────────────────────────────────────────
function upColor(intensity: number): string {
  // Green gradient for upregulated
  const t = Math.min(1, intensity);
  const r = Math.round(16 + (0 - 16) * t);
  const g = Math.round(185 + (140 - 185) * t);
  const b = Math.round(129 + (80 - 129) * t);
  return `rgb(${r},${g},${b})`;
}

function downColor(intensity: number): string {
  // Red/coral gradient for downregulated
  const t = Math.min(1, intensity);
  const r = Math.round(220 + (180 - 220) * t);
  const g = Math.round(80 + (40 - 80) * t);
  const b = Math.round(60 + (40 - 60) * t);
  return `rgb(${r},${g},${b})`;
}

/** Parse a rendered expression table for Log2FC + tissue columns. */
function parseExpressionTable(tbl: HTMLTableElement): HeatmapEntry[] {
  const headers = Array.from(tbl.querySelectorAll('thead th, tr:first-child th'));
  const log2fcCol = headers.findIndex(th => /log2fc/i.test(th.textContent ?? ''));
  const tissueCol = headers.findIndex(th => /tissue|genotype/i.test(th.textContent ?? ''));
  if (log2fcCol < 0) return [];

  const entries: HeatmapEntry[] = [];
  tbl.querySelectorAll('tbody tr').forEach((row) => {
    const cells = row.querySelectorAll('td');
    if (cells.length <= log2fcCol) return;
    const fc = parseFloat(cells[log2fcCol]?.textContent?.replace(/[+\s]/g, '') ?? '');
    if (isNaN(fc)) return;
    const tissue = tissueCol >= 0
      ? (cells[tissueCol]?.textContent?.trim() ?? `Row ${entries.length + 1}`)
      : `Row ${entries.length + 1}`;
    entries.push({ tissue, log2fc: fc });
  });
  return entries;
}

/** Build a diverging bar chart SVG. */
function buildDivergingChart(entries: HeatmapEntry[], stressLabel: string): SVGElement {
  const ns = 'http://www.w3.org/2000/svg';
  const bodyHeight = entries.length * (BAR_HEIGHT + BAR_GAP);
  const headerHeight = 36;
  const footerHeight = 44;
  const totalHeight = headerHeight + bodyHeight + footerHeight + 12;

  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${TOTAL_WIDTH} ${totalHeight}`);
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', `${totalHeight}`);
  svg.classList.add('heatmap-svg');

  // ── Gradient definitions ──────────────────────────────────────────────────
  const defs = document.createElementNS(ns, 'defs');
  const uid = `hm-${Date.now()}-${Math.random().toString(36).slice(2, 5)}`;

  // Up gradient (left to right, transparent → green)
  const upGrad = document.createElementNS(ns, 'linearGradient');
  upGrad.id = `${uid}-up`;
  [[0, 'rgba(16,185,129,0.15)'], [100, 'rgba(16,185,129,0.85)']].forEach(([o, c]) => {
    const s = document.createElementNS(ns, 'stop');
    s.setAttribute('offset', `${o}%`); s.setAttribute('stop-color', c as string);
    upGrad.appendChild(s);
  });
  defs.appendChild(upGrad);

  // Down gradient (right to left, transparent → red)
  const dnGrad = document.createElementNS(ns, 'linearGradient');
  dnGrad.id = `${uid}-dn`;
  [[0, 'rgba(220,80,60,0.85)'], [100, 'rgba(220,80,60,0.15)']].forEach(([o, c]) => {
    const s = document.createElementNS(ns, 'stop');
    s.setAttribute('offset', `${o}%`); s.setAttribute('stop-color', c as string);
    dnGrad.appendChild(s);
  });
  defs.appendChild(dnGrad);

  // Drop shadow filter
  const filter = document.createElementNS(ns, 'filter');
  filter.id = `${uid}-shadow`;
  filter.setAttribute('x', '-20%'); filter.setAttribute('y', '-20%');
  filter.setAttribute('width', '140%'); filter.setAttribute('height', '140%');
  const feDropShadow = document.createElementNS(ns, 'feDropShadow');
  feDropShadow.setAttribute('dx', '0'); feDropShadow.setAttribute('dy', '1');
  feDropShadow.setAttribute('stdDeviation', '2');
  feDropShadow.setAttribute('flood-color', 'rgba(0,0,0,0.1)');
  filter.appendChild(feDropShadow);
  defs.appendChild(filter);
  svg.appendChild(defs);

  // ── Title ─────────────────────────────────────────────────────────────────
  const titleGroup = document.createElementNS(ns, 'g');

  // Stress type pill
  const pillW = stressLabel.length * 8 + 24;
  const pillX = CENTER_X - pillW / 2;
  const pillRect = document.createElementNS(ns, 'rect');
  pillRect.setAttribute('x', `${pillX}`); pillRect.setAttribute('y', '4');
  pillRect.setAttribute('width', `${pillW}`); pillRect.setAttribute('height', '22');
  pillRect.setAttribute('rx', '11');
  pillRect.setAttribute('fill', 'rgba(16,163,127,0.1)');
  pillRect.setAttribute('stroke', 'rgba(16,163,127,0.2)');
  pillRect.setAttribute('stroke-width', '1');
  titleGroup.appendChild(pillRect);

  const title = document.createElementNS(ns, 'text');
  title.setAttribute('x', `${CENTER_X}`); title.setAttribute('y', '19');
  title.setAttribute('text-anchor', 'middle');
  title.setAttribute('class', 'heatmap-title');
  title.textContent = `${stressLabel} Response`;
  titleGroup.appendChild(title);
  svg.appendChild(titleGroup);

  // ── Center axis line ──────────────────────────────────────────────────────
  const axisLine = document.createElementNS(ns, 'line');
  axisLine.setAttribute('x1', `${CENTER_X}`); axisLine.setAttribute('x2', `${CENTER_X}`);
  axisLine.setAttribute('y1', `${headerHeight - 4}`);
  axisLine.setAttribute('y2', `${headerHeight + bodyHeight + 2}`);
  axisLine.setAttribute('stroke', 'rgba(0,0,0,0.12)');
  axisLine.setAttribute('stroke-width', '1.5');
  axisLine.setAttribute('stroke-dasharray', '3,3');
  svg.appendChild(axisLine);

  // Zero label at top of axis
  const zeroLabel = document.createElementNS(ns, 'text');
  zeroLabel.setAttribute('x', `${CENTER_X}`);
  zeroLabel.setAttribute('y', `${headerHeight - 8}`);
  zeroLabel.setAttribute('text-anchor', 'middle');
  zeroLabel.setAttribute('class', 'heatmap-axis-label');
  zeroLabel.textContent = '0';
  svg.appendChild(zeroLabel);

  // ── Bars ───────────────────────────────────────────────────────────────────
  entries.forEach((entry, i) => {
    const y = headerHeight + i * (BAR_HEIGHT + BAR_GAP);
    const clamped = Math.max(-MAX_FC, Math.min(MAX_FC, entry.log2fc));
    const barWidth = Math.abs(clamped) / MAX_FC * CHART_HALF;
    const isUp = clamped >= 0;

    // Subtle row background
    if (i % 2 === 0) {
      const bg = document.createElementNS(ns, 'rect');
      bg.setAttribute('x', '0'); bg.setAttribute('y', `${y - 1}`);
      bg.setAttribute('width', `${TOTAL_WIDTH}`);
      bg.setAttribute('height', `${BAR_HEIGHT + 2}`);
      bg.setAttribute('fill', 'rgba(0,0,0,0.015)');
      bg.setAttribute('rx', '4');
      svg.appendChild(bg);
    }

    // Tissue label (right-aligned before chart)
    const label = document.createElementNS(ns, 'text');
    label.setAttribute('x', `${LABEL_WIDTH}`);
    label.setAttribute('y', `${y + BAR_HEIGHT / 2 + 4}`);
    label.setAttribute('text-anchor', 'end');
    label.setAttribute('class', 'heatmap-label');
    const maxLen = 28;
    label.textContent = entry.tissue.length > maxLen ? entry.tissue.slice(0, maxLen - 1) + '…' : entry.tissue;
    svg.appendChild(label);

    // Bar
    const barX = isUp ? CENTER_X : CENTER_X - barWidth;
    const bar = document.createElementNS(ns, 'rect');
    bar.setAttribute('x', `${barX}`);
    bar.setAttribute('y', `${y + 2}`);
    bar.setAttribute('width', `${Math.max(barWidth, 2)}`);
    bar.setAttribute('height', `${BAR_HEIGHT - 4}`);
    bar.setAttribute('rx', `${(BAR_HEIGHT - 4) / 2}`);  // Pill shape
    bar.setAttribute('fill', `url(#${isUp ? upGrad.id : dnGrad.id})`);
    bar.setAttribute('filter', `url(#${filter.id})`);
    svg.appendChild(bar);

    // Dot at end of bar
    const dotX = isUp ? CENTER_X + barWidth : CENTER_X - barWidth;
    const dot = document.createElementNS(ns, 'circle');
    dot.setAttribute('cx', `${dotX}`);
    dot.setAttribute('cy', `${y + BAR_HEIGHT / 2}`);
    dot.setAttribute('r', '5');
    dot.setAttribute('fill', isUp ? upColor(Math.abs(clamped) / MAX_FC) : downColor(Math.abs(clamped) / MAX_FC));
    dot.setAttribute('stroke', '#fff');
    dot.setAttribute('stroke-width', '1.5');
    dot.setAttribute('filter', `url(#${filter.id})`);
    svg.appendChild(dot);

    // Value label
    const valX = isUp ? dotX + 14 : dotX - 14;
    const valText = document.createElementNS(ns, 'text');
    valText.setAttribute('x', `${valX}`);
    valText.setAttribute('y', `${y + BAR_HEIGHT / 2 + 4}`);
    valText.setAttribute('text-anchor', isUp ? 'start' : 'end');
    valText.setAttribute('class', isUp ? 'heatmap-value heatmap-value-up' : 'heatmap-value heatmap-value-down');
    valText.textContent = entry.log2fc > 0 ? `+${entry.log2fc.toFixed(2)}` : entry.log2fc.toFixed(2);
    svg.appendChild(valText);
  });

  // ── Footer legend ─────────────────────────────────────────────────────────
  const fy = headerHeight + bodyHeight + 16;

  // Down arrow + label
  const downArrow = document.createElementNS(ns, 'g');
  downArrow.setAttribute('transform', `translate(${CENTER_X - CHART_HALF - 10}, ${fy})`);
  const dnPath = document.createElementNS(ns, 'path');
  dnPath.setAttribute('d', 'M12 2 L6 10 L9 10 L9 18 L15 18 L15 10 L18 10 Z');
  dnPath.setAttribute('transform', 'rotate(180, 12, 10) scale(0.75)');
  dnPath.setAttribute('fill', 'rgba(220,80,60,0.6)');
  downArrow.appendChild(dnPath);
  const dnLabel = document.createElementNS(ns, 'text');
  dnLabel.setAttribute('x', '20'); dnLabel.setAttribute('y', '14');
  dnLabel.setAttribute('class', 'heatmap-legend-text');
  dnLabel.textContent = 'Downregulated';
  downArrow.appendChild(dnLabel);
  svg.appendChild(downArrow);

  // Up arrow + label
  const upArrow = document.createElementNS(ns, 'g');
  upArrow.setAttribute('transform', `translate(${CENTER_X + 20}, ${fy})`);
  const upPath = document.createElementNS(ns, 'path');
  upPath.setAttribute('d', 'M12 2 L6 10 L9 10 L9 18 L15 18 L15 10 L18 10 Z');
  upPath.setAttribute('transform', 'scale(0.75)');
  upPath.setAttribute('fill', 'rgba(16,185,129,0.6)');
  upArrow.appendChild(upPath);
  const upLabel = document.createElementNS(ns, 'text');
  upLabel.setAttribute('x', '20'); upLabel.setAttribute('y', '14');
  upLabel.setAttribute('class', 'heatmap-legend-text');
  upLabel.textContent = 'Upregulated';
  upArrow.appendChild(upLabel);
  svg.appendChild(upArrow);

  // Threshold markers
  const threshNote = document.createElementNS(ns, 'text');
  threshNote.setAttribute('x', `${CENTER_X}`);
  threshNote.setAttribute('y', `${fy + 30}`);
  threshNote.setAttribute('text-anchor', 'middle');
  threshNote.setAttribute('class', 'heatmap-threshold-note');
  threshNote.textContent = 'Log₂FC threshold: ±1.5';
  svg.appendChild(threshNote);

  return svg;
}

/**
 * Generate a diverging bar chart for a rendered expression table.
 * Returns null if the table has no Log2FC data.
 */
export function generateHeatmap(tbl: HTMLTableElement, stressLabel?: string): HTMLElement | null {
  const entries = parseExpressionTable(tbl);
  if (entries.length === 0) return null;
  const label = stressLabel ?? 'Expression';
  const container = document.createElement('div');
  container.className = 'heatmap-container';
  const svg = buildDivergingChart(entries, label);
  container.appendChild(svg);
  return container;
}

/**
 * Scan a rendered result body for expression tables and insert heatmaps.
 * @param afterTable if true, inserts after each table; if false, appends all at the bottom.
 */
export function insertHeatmaps(body: HTMLElement, afterTable: boolean = true): void {
  const tables = body.querySelectorAll<HTMLTableElement>('table.data-table');
  const heatmaps: HTMLElement[] = [];

  tables.forEach((tbl) => {
    const headers = Array.from(tbl.querySelectorAll('thead th, tr:first-child th'));
    const hasLog2FC = headers.some(th => /log2fc/i.test(th.textContent ?? ''));
    if (!hasLog2FC) return;

    let stressLabel = 'Expression';
    const wrapper = tbl.closest('.table-wrapper') ?? tbl;
    let prev: Element | null = wrapper.previousElementSibling;
    while (prev) {
      if (prev.tagName === 'H3') {
        stressLabel = prev.textContent?.replace(/\s*response\s*/i, '').trim() ?? 'Expression';
        break;
      }
      prev = prev.previousElementSibling;
    }

    const heatmap = generateHeatmap(tbl, stressLabel);
    if (!heatmap) return;

    if (afterTable) {
      wrapper.parentNode?.insertBefore(heatmap, wrapper.nextSibling);
    } else {
      heatmaps.push(heatmap);
    }
  });

  if (!afterTable && heatmaps.length > 0) {
    const section = document.createElement('div');
    section.className = 'heatmap-section';
    const heading = document.createElement('h3');
    heading.textContent = 'Expression Heatmaps';
    heading.className = 'heatmap-section-heading';
    section.appendChild(heading);
    heatmaps.forEach(h => section.appendChild(h));
    body.appendChild(section);
  }
}
