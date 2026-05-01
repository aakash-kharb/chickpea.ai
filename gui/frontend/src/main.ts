// main.ts — Application entry point for Chickpea SRG RAG GUI

import './style.css';
import { fetchHealth, streamQuery } from './api';
import { StagePanel } from './stages';
import { renderResult, renderError, renderUserBubble } from './renderer';
import { GenePicker } from './genepicker';
import { initBackground } from './background';
import type { PipelineResult } from './types';

// ── Home Page → Chat Transition ──────────────────────────────────────────────
const homePage = document.getElementById('home-page') as HTMLElement;
const appEl    = document.getElementById('app')       as HTMLElement;
const homeCta  = document.getElementById('home-cta')  as HTMLButtonElement;

// Check if user already entered chat in this session
const _alreadyEntered = sessionStorage.getItem('chickpea_entered') === '1';

function _showChat(): void {
  homePage.classList.add('home-leaving');
  // After the exit animation completes, hide home page and show app
  setTimeout(() => {
    homePage.classList.add('home-hidden');
    appEl.classList.remove('app-hidden');
    appEl.classList.add('app-entering');
    // Trigger reflow then add the visible class for entrance animation
    void appEl.offsetHeight;
    appEl.classList.add('app-visible');
    sessionStorage.setItem('chickpea_entered', '1');
    // Initialize background after chat is visible
    initBackground();
    queryInput.focus();
    // Clean up entrance class after animation
    setTimeout(() => appEl.classList.remove('app-entering'), 600);
  }, 500);
}

if (_alreadyEntered) {
  // Skip home page — show chat directly
  homePage.classList.add('home-hidden');
  appEl.classList.remove('app-hidden');
  appEl.classList.add('app-visible');
  initBackground();
} else {
  // Show home page
  homePage.classList.remove('home-hidden');
  appEl.classList.add('app-hidden');
}

if (homeCta) {
  homeCta.addEventListener('click', _showChat);
}

// ── Input bar pill animation state ────────────────────────────────────────────
let inputExpanded = false;

// ── DOM refs ──────────────────────────────────────────────────────────────────
const queryInput   = document.getElementById('query-input')      as HTMLTextAreaElement;
const submitBtn    = document.getElementById('submit-btn')       as HTMLButtonElement;
const examplesBtn  = document.getElementById('examples-btn')     as HTMLButtonElement;
const chatThread   = document.getElementById('chat-thread')      as HTMLElement;
const stagePanel   = document.getElementById('stage-panel')      as HTMLElement;
const backendDot   = document.getElementById('backend-dot')      as HTMLElement;
const backendLabel = document.getElementById('backend-label')    as HTMLElement;
const emptyState   = document.getElementById('empty-state')      as HTMLElement;
const charCounter  = document.getElementById('char-counter')     as HTMLElement;
const welcomeGreet = document.getElementById('welcome-greeting') as HTMLElement;
const newChatBtn   = document.getElementById('new-chat-btn')     as HTMLButtonElement;
const historyList  = document.getElementById('history-list')     as HTMLElement;
const historyEmpty = document.getElementById('history-empty')    as HTMLElement;

const MAX_CHARS = 512;

// ── Time-based greeting ───────────────────────────────────────────────────────
(function setGreeting() {
  const h = new Date().getHours();
  welcomeGreet.textContent =
    h < 12 ? 'Good morning.' :
    h < 18 ? 'Good afternoon.' :
             'Good evening.';
})();

// ── Typewriter subtitle animation ─────────────────────────────────────────────
const _typewriterPhrases = [
  'Ask anything about chickpea stress genes',
  'Explore drought, heat, cold & salinity responses',
  'Compare gene expression across conditions',
  'Look up peptide sequences and properties',
  'Discover stress-responsive gene networks',
];

(function initTypewriter() {
  const textEl = document.getElementById('typewriter-text');
  if (!textEl) return;

  let phraseIdx = 0;
  let charIdx = 0;
  let isDeleting = false;
  let currentText = '';

  const TYPE_SPEED    = 45;   // ms per char (typing)
  const DELETE_SPEED  = 30;   // ms per char (backspace)
  const PAUSE_AFTER   = 2000; // ms to hold complete phrase
  const PAUSE_BEFORE  = 400;  // ms before typing next phrase

  function tick(): void {
    const phrase = _typewriterPhrases[phraseIdx];

    if (!isDeleting) {
      // Typing forward
      charIdx++;
      currentText = phrase.slice(0, charIdx);
      textEl!.textContent = currentText;

      if (charIdx >= phrase.length) {
        // Finished typing — pause, then start deleting
        setTimeout(() => { isDeleting = true; tick(); }, PAUSE_AFTER);
        return;
      }
      setTimeout(tick, TYPE_SPEED);
    } else {
      // Deleting (backspace)
      charIdx--;
      currentText = phrase.slice(0, charIdx);
      textEl!.textContent = currentText;

      if (charIdx <= 0) {
        // Finished deleting — move to next phrase
        isDeleting = false;
        phraseIdx = (phraseIdx + 1) % _typewriterPhrases.length;
        setTimeout(tick, PAUSE_BEFORE);
        return;
      }
      setTimeout(tick, DELETE_SPEED);
    }
  }

  // Start after a short initial delay
  setTimeout(tick, 600);
})();

// ── Sidebar collapse ────────────────────────────────────────────────────────
const sidebar            = document.querySelector('.sidebar')                  as HTMLElement;
const collapseBtn        = document.getElementById('sidebar-toggle-expanded')  as HTMLButtonElement; // right side of brand (expanded state)
const expandTrigger      = document.getElementById('sidebar-toggle-collapsed') as HTMLElement;       // brand-icon-wrap (collapsed state)

function _setSidebarCollapsed(collapsed: boolean): void {
  sidebar.classList.toggle('collapsed', collapsed);
}

// Collapse: right-edge button in expanded state
if (collapseBtn) {
  collapseBtn.addEventListener('click', () => _setSidebarCollapsed(true));
}

// Expand: hover+click on brand-icon-wrap in collapsed state
if (expandTrigger) {
  expandTrigger.addEventListener('click', () => {
    if (sidebar.classList.contains('collapsed')) _setSidebarCollapsed(false);
  });
  expandTrigger.addEventListener('keydown', (e: KeyboardEvent) => {
    if ((e.key === 'Enter' || e.key === ' ') && sidebar.classList.contains('collapsed'))
      _setSidebarCollapsed(false);
  });
}

const stages = new StagePanel(stagePanel);

void new GenePicker({
  triggerBtn: examplesBtn,
  inputEl:    queryInput,
  onPick:     (text) => { queryInput.value = text; queryInput.focus(); _syncCounter(); _autoGrow(); },
});

// ── In-session Chat History (in-memory only — clears on refresh) ──────────────
interface HistoryEntry {
  id: string;
  timestamp: number;
  query: string;
  result: PipelineResult;
}

const _sessionHistory: HistoryEntry[] = [];
const MAX_HISTORY = 50;

function _historyPush(query: string, result: PipelineResult): void {
  if (_sessionHistory.length >= MAX_HISTORY) _sessionHistory.shift();
  _sessionHistory.push({
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    timestamp: Date.now(),
    query,
    result,
  });
  _renderHistorySidebar();
}

function _renderHistorySidebar(): void {
  historyEmpty?.classList.add('hidden');
  historyList.querySelectorAll('.sidebar-item').forEach(el => el.remove());

  // Newest first
  [..._sessionHistory].reverse().forEach((entry) => {
    const btn = document.createElement('button');
    btn.className = 'sidebar-item';
    const timeStr = new Date(entry.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    // SVG chat icon — clean, no emoji
    const iconSvg = `<svg class="history-svg-icon" width="14" height="14" viewBox="0 0 24 24" fill="none">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>
    </svg>`;
    btn.innerHTML = `
      <span class="history-item-icon">${iconSvg}</span>
      <span class="history-item-body">
        <span class="history-item-query">${_escHtml(entry.query)}</span>
        <span class="history-item-meta">${timeStr}</span>
      </span>
    `;
    btn.addEventListener('click', () => _restoreHistory(entry));
    historyList.insertBefore(btn, historyList.firstChild);
  });

  if (_sessionHistory.length === 0) historyEmpty?.classList.remove('hidden');
}

function _restoreHistory(entry: HistoryEntry): void {
  cancelStream?.();
  isLoading = false;
  emptyState.classList.add('hidden');
  stages.hide();
  chatThread.innerHTML = '';

  const exchange = document.createElement('div');
  exchange.className = 'chat-exchange';
  renderUserBubble(exchange, entry.query);

  const resultContainer = document.createElement('div');
  renderResult(resultContainer, entry.result);
  exchange.appendChild(resultContainer);
  chatThread.appendChild(exchange);
  _resetInputState();
}


// ── State ─────────────────────────────────────────────────────────────────────
let cancelStream: (() => void) | null = null;
let isLoading = false;

// ── Health check ──────────────────────────────────────────────────────────────
async function initHealth(): Promise<void> {
  try {
    const h = await fetchHealth();
    backendDot.className     = 'status-dot online';
    backendLabel.textContent = h.backend;
  } catch {
    backendDot.className     = 'status-dot offline';
    backendLabel.textContent = 'Backend offline';
  }
}

// ── Textarea auto-grow ────────────────────────────────────────────────────────
function _autoGrow(): void {
  queryInput.style.height = 'auto';
  queryInput.style.height = `${Math.min(queryInput.scrollHeight, 200)}px`;
}

// ── Submit ────────────────────────────────────────────────────────────────────
function handleSubmit(): void {
  if (isLoading) {
    // Stop button click — cancel the running stream
    cancelStream?.();
    _resetInputState();
    return;
  }

  const query = queryInput.value.trim();
  if (!query) return;

  // Clear input immediately after capturing the query
  queryInput.value = '';
  _syncCounter();
  _autoGrow();

  cancelStream?.();
  isLoading = true;

  emptyState.classList.add('hidden');

  // Render user bubble
  const exchange = document.createElement('div');
  exchange.className = 'chat-exchange';
  renderUserBubble(exchange, query);
  chatThread.appendChild(exchange);

  // Scroll to bottom
  exchange.scrollIntoView({ behavior: 'smooth', block: 'end' });

  // Switch submit to stop
  submitBtn.classList.add('loading');
  submitBtn.disabled  = false;  // keep enabled so user can stop
  queryInput.disabled = true;
  stages.reset();

  // Collapse input bar to pill after submit
  _collapseInput();

  cancelStream = streamQuery(query, {
    onStage(event) {
      stages.advance(event.index);
    },
    onResult(result) {
      stages.complete();

      const resultContainer = document.createElement('div');
      renderResult(resultContainer, result);
      exchange.appendChild(resultContainer);

      _historyPush(query, result);
      _resetInputState();
    },
    onError(message) {
      stages.hide();
      const errContainer = document.createElement('div');
      renderError(errContainer, message);
      exchange.appendChild(errContainer);
      _resetInputState();
    },
    onNetworkError(message) {
      stages.hide();
      const errContainer = document.createElement('div');
      renderError(errContainer, `Connection error — is the backend running?\n${message}`);
      exchange.appendChild(errContainer);
      initHealth();
      _resetInputState();
    },
  });
}

function _resetInputState(): void {
  isLoading           = false;
  cancelStream        = null;
  submitBtn.classList.remove('loading');
  submitBtn.disabled  = queryInput.value.trim().length === 0;
  queryInput.disabled = false;
  queryInput.focus();
}

// ── New chat / reset ──────────────────────────────────────────────────────────
function handleNewChat(): void {
  cancelStream?.();
  isLoading             = false;
  cancelStream          = null;
  queryInput.value      = '';
  queryInput.disabled   = false;
  queryInput.style.height = '';
  chatThread.innerHTML  = '';
  stages.hide();
  submitBtn.classList.remove('loading');
  emptyState.classList.remove('hidden');
  submitBtn.disabled    = true;
  _syncCounter();
  queryInput.focus();
}

// ── Suggestion chips ──────────────────────────────────────────────────────────
document.querySelectorAll<HTMLButtonElement>('.suggestion-chip').forEach((chip) => {
  chip.addEventListener('click', () => {
    const q = chip.dataset['query'] ?? '';
    if (!q) return;
    queryInput.value = q;
    _syncCounter();
    _autoGrow();
    handleSubmit();
  });
});

// ── Input bar pill animation ──────────────────────────────────────────────────
const inputBar = document.querySelector('.input-bar') as HTMLElement;

function _expandInput(): void {
  if (inputExpanded) return;
  inputExpanded = true;
  inputBar.classList.add('expanded');
  inputBar.classList.remove('collapsed');
}

function _collapseInput(): void {
  if (!inputExpanded) return;
  inputExpanded = false;
  inputBar.classList.remove('expanded');
  inputBar.classList.add('collapsed');
}

// Start in collapsed pill state
inputBar.classList.add('collapsed');

// Click outside input area → collapse if empty
document.addEventListener('mousedown', (e) => {
  const target = e.target as Node;
  if (!inputBar.contains(target) && inputExpanded && queryInput.value.trim() === '' && !isLoading) {
    _collapseInput();
    queryInput.blur();
  }
});

// ── Event listeners ───────────────────────────────────────────────────────────
submitBtn.addEventListener('click', handleSubmit);
newChatBtn.addEventListener('click', handleNewChat);

queryInput.addEventListener('focus', () => _expandInput());

queryInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(); }
  if (e.key === 'Escape') {
    cancelStream?.();
    _resetInputState();
    if (queryInput.value.trim() === '') { _collapseInput(); queryInput.blur(); }
  }
});

queryInput.addEventListener('input', () => { _syncCounter(); _autoGrow(); });

// ── Helpers ───────────────────────────────────────────────────────────────────
function _syncCounter(): void {
  const len = queryInput.value.length;

  // When loading, keep submit enabled (it's the stop button)
  if (!isLoading) submitBtn.disabled = len === 0;

  charCounter.textContent = `${len} / ${MAX_CHARS}`;
  charCounter.className   = 'char-counter' +
    (len >= MAX_CHARS ? ' char-over' : len >= 400 ? ' char-warn' : '');

  if (len > MAX_CHARS) {
    queryInput.value        = queryInput.value.slice(0, MAX_CHARS);
    charCounter.textContent = `${MAX_CHARS} / ${MAX_CHARS}`;
  }
}

function _escHtml(s: string): string {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Init ──────────────────────────────────────────────────────────────────────
submitBtn.disabled = true;
initHealth();
