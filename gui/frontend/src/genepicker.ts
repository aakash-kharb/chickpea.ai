// genepicker.ts — Floating gene ID & example query popup

export interface PickerConfig {
  triggerBtn: HTMLElement;
  inputEl:    HTMLInputElement | HTMLTextAreaElement;
  onPick:     (text: string) => void;
}

const EXAMPLE_GENES = [
  'Ca_00001','Ca_00011','Ca_00099','Ca_00500','Ca_00999','LOC101511858','ARF1','NAC01',
];

const EXAMPLE_QUERIES = [
  { label: 'Heat profile',        query: 'Is Ca_00011 upregulated under heat?' },
  { label: 'Drought genes',       query: 'Give me 5 drought-responsive genes' },
  { label: 'Salinity comparison', query: 'Compare Ca_00001 and Ca_00011 under salinity' },
  { label: 'Sequence analysis',   query: 'Show peptide sequence analysis of Ca_00099' },
  { label: 'Cold + drought',      query: 'Give me 3 genes responsive to both cold and drought' },
  { label: 'Stress label',        query: 'What is the stress label of Ca_00500 under heat?' },
];

export class GenePicker {
  private popup:  HTMLElement;
  private isOpen: boolean = false;
  private onPick: (text: string) => void;
  private inputEl: HTMLInputElement | HTMLTextAreaElement;

  constructor(cfg: PickerConfig) {
    this.onPick  = cfg.onPick;
    this.inputEl = cfg.inputEl;
    this.popup   = this._buildPopup();
    document.body.appendChild(this.popup);

    cfg.triggerBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggle(cfg.triggerBtn);
    });

    // Auto-open removed: was too eager. Use the 🌿 button to open explicitly.

    document.addEventListener('click', (e) => {
      if (!this.popup.contains(e.target as Node) && e.target !== cfg.triggerBtn) this.close();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.close();
    });
  }

  toggle(anchor: HTMLElement): void { this.isOpen ? this.close() : this.open(anchor); }

  open(anchor: HTMLElement): void {
    this._position(anchor);
    this.popup.classList.add('visible');
    this.isOpen = true;
  }

  close(): void {
    this.popup.classList.remove('visible');
    this.isOpen = false;
  }

  private _buildPopup(): HTMLElement {
    const div = document.createElement('div');
    div.className = 'gene-picker-popup';

    // Gene chips section
    const geneSection = document.createElement('div');
    geneSection.className = 'picker-section';
    geneSection.innerHTML = '<p class="picker-section-label">Gene IDs</p>';
    const chips = document.createElement('div');
    chips.className = 'picker-chips';
    for (const geneId of EXAMPLE_GENES) {
      const chip = document.createElement('button');
      chip.className = 'picker-chip gene-chip';
      chip.textContent = geneId;
      chip.addEventListener('click', () => this._inject(geneId));
      chips.appendChild(chip);
    }
    geneSection.appendChild(chips);

    // Divider
    const divider = document.createElement('hr');
    divider.className = 'picker-divider';

    // Example queries section
    const querySection = document.createElement('div');
    querySection.className = 'picker-section';
    querySection.innerHTML = '<p class="picker-section-label">Example queries</p>';
    const queryList = document.createElement('ul');
    queryList.className = 'picker-query-list';
    for (const ex of EXAMPLE_QUERIES) {
      const li  = document.createElement('li');
      const btn = document.createElement('button');
      btn.className = 'picker-query-btn';
      btn.innerHTML = `<span class="picker-query-label">${ex.label}</span><span class="picker-query-text">${ex.query}</span>`;
      btn.addEventListener('click', () => { this.onPick(ex.query); this.close(); });
      li.appendChild(btn);
      queryList.appendChild(li);
    }
    querySection.appendChild(queryList);

    div.appendChild(geneSection);
    div.appendChild(divider);
    div.appendChild(querySection);
    return div;
  }

  private _inject(geneId: string): void {
    const cur = this.inputEl.value;
    const caIdx = cur.search(/Ca_\d*$/i);
    this.inputEl.value = caIdx !== -1
      ? cur.slice(0, caIdx) + geneId
      : (cur ? `${cur} ${geneId}` : geneId);
    this.inputEl.focus();
    this.onPick(this.inputEl.value);
    this.close();
  }

  private _position(anchor: HTMLElement): void {
    const rect = anchor.getBoundingClientRect();
    this.popup.style.bottom = `${window.innerHeight - rect.top + 8}px`;
    this.popup.style.right  = `${window.innerWidth - rect.right}px`;
    this.popup.style.left   = 'auto';
  }
}
