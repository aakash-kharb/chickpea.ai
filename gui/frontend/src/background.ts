/**
 * background.ts — Vibrant gradient ambient background
 *
 * Creates CSS-driven gradient orbs with a rich blue, orange, purple, and
 * golden palette centered on the viewport.  Pure CSS animations on
 * transform (GPU-accelerated) — no requestAnimationFrame loop.
 */

export function initBackground(): void {
  const container = document.getElementById('gradient-bg');
  if (!container) return;

  const orbs = [
    { // Rich orange — center-right
      color: 'radial-gradient(circle, rgba(255,150,60,0.32) 0%, rgba(255,130,40,0.12) 40%, transparent 68%)',
      size: 900,
      x: 58, y: 25,
      drift: 'orb-drift-1',
    },
    { // Deep blue — center-left
      color: 'radial-gradient(circle, rgba(80,140,255,0.30) 0%, rgba(60,120,240,0.10) 40%, transparent 68%)',
      size: 850,
      x: 25, y: 40,
      drift: 'orb-drift-2',
    },
    { // Warm golden — center
      color: 'radial-gradient(circle, rgba(255,210,120,0.22) 0%, rgba(255,190,90,0.07) 40%, transparent 65%)',
      size: 1000,
      x: 42, y: 32,
      drift: 'orb-drift-3',
    },
    { // Soft purple — top-left
      color: 'radial-gradient(circle, rgba(160,120,255,0.18) 0%, rgba(140,100,240,0.06) 40%, transparent 68%)',
      size: 650,
      x: 15, y: 8,
      drift: 'orb-drift-4',
    },
    { // Teal accent — bottom-center
      color: 'radial-gradient(circle, rgba(60,210,200,0.16) 0%, rgba(40,190,180,0.05) 40%, transparent 68%)',
      size: 550,
      x: 50, y: 75,
      drift: 'orb-drift-1',
    },
    { // Coral pink — far right
      color: 'radial-gradient(circle, rgba(255,130,120,0.15) 0%, rgba(255,110,100,0.05) 40%, transparent 68%)',
      size: 500,
      x: 82, y: 60,
      drift: 'orb-drift-2',
    },
  ];

  for (const orb of orbs) {
    const el = document.createElement('div');
    el.className = `gradient-orb ${orb.drift}`;
    el.style.width = `${orb.size}px`;
    el.style.height = `${orb.size}px`;
    el.style.left = `${orb.x}%`;
    el.style.top = `${orb.y}%`;
    el.style.background = orb.color;
    container.appendChild(el);
  }
}
