// stages.ts — Stage progress panel controller

const STAGES = [
  { key: 'routing',    label: 'Semantic & intent interpretation' },
  { key: 'resolving',  label: 'Resolving gene identifiers' },
  { key: 'retrieving', label: 'Data retrieval & packet assembly' },
  { key: 'analysing',  label: 'Agents running  ·  LLM synthesis' },
  { key: 'validating', label: 'Routing capsule  ·  output validation' },
  { key: 'rendering',  label: 'Composing final response' },
] as const;

const SPINNER = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏'];

export class StagePanel {
  private panel:     HTMLElement;
  private items:     HTMLElement[] = [];
  private current:   number = -1;
  private frame:     number = 0;
  private ticker:    ReturnType<typeof setInterval> | null = null;
  private startTime: number = 0;

  constructor(panelEl: HTMLElement) {
    this.panel = panelEl;
    this._buildDOM();
  }

  reset(): void {
    this.current   = -1;
    this.frame     = 0;
    this.startTime = Date.now();
    // Clear any stale elapsed footer
    const old = this.panel.querySelector('.stage-elapsed');
    if (old) old.remove();
    this._updateAll();
    this.panel.classList.remove('hidden', 'done');
    this.panel.classList.add('visible');
    if (this.ticker) clearInterval(this.ticker);
    this.ticker = setInterval(() => {
      this.frame = (this.frame + 1) % SPINNER.length;
      this._updateActive();
    }, 80);
  }

  advance(index: number): void {
    this.current = index;
    this._updateAll();
  }

  complete(): void {
    this.current = STAGES.length;
    this._updateAll();
    if (this.ticker) { clearInterval(this.ticker); this.ticker = null; }
    // Show elapsed time
    const elapsed = ((Date.now() - this.startTime) / 1000).toFixed(1);
    const footer = document.createElement('div');
    footer.className = 'stage-elapsed';
    footer.textContent = `⏱ Completed in ${elapsed}s`;
    this.panel.appendChild(footer);
    setTimeout(() => this.panel.classList.add('done'), 600);
  }

  hide(): void {
    if (this.ticker) { clearInterval(this.ticker); this.ticker = null; }
    this.panel.classList.remove('visible');
    this.panel.classList.add('hidden');
  }

  private _buildDOM(): void {
    this.panel.innerHTML = `
      <div class="stage-header">
        <span class="stage-icon">⬡</span> Pipeline Progress
      </div>
      <ul class="stage-list"></ul>
    `;
    const ul = this.panel.querySelector('.stage-list') as HTMLUListElement;
    this.items = STAGES.map((s) => {
      const li = document.createElement('li');
      li.className = 'stage-item pending';
      li.innerHTML = `<span class="stage-glyph">·</span><span class="stage-label">${s.label}</span>`;
      ul.appendChild(li);
      return li;
    });
  }

  private _updateAll(): void {
    STAGES.forEach((_, i) => {
      const el    = this.items[i];
      const glyph = el.querySelector('.stage-glyph') as HTMLElement;
      if      (i < this.current)       { el.className = 'stage-item done';    glyph.textContent = '✓'; }
      else if (i === this.current)      { el.className = 'stage-item active';  glyph.textContent = SPINNER[this.frame]; }
      else                              { el.className = 'stage-item pending'; glyph.textContent = '·'; }
    });
  }

  private _updateActive(): void {
    const el = this.items[this.current];
    if (!el) return;
    (el.querySelector('.stage-glyph') as HTMLElement).textContent = SPINNER[this.frame];
  }
}
