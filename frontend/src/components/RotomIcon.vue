<template>
  <svg class="rotom-icon" viewBox="0 0 128 128" role="img" aria-label="Rotom Agent">
    <defs>
      <radialGradient id="rotom-body" cx="42%" cy="34%" r="68%">
        <stop offset="0%" stop-color="#fff4d0" />
        <stop offset="32%" stop-color="#ff9347" />
        <stop offset="100%" stop-color="#ff4d18" />
      </radialGradient>
      <filter id="rotom-glow" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="4" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>

    <circle cx="64" cy="64" r="44" fill="none" stroke="#2bd9fe" stroke-width="4" opacity="0.45" />
    <path class="aura" d="M27 39 13 29 33 28 38 12 47 31" />
    <path class="aura" d="M101 39 115 29 95 28 90 12 81 31" />
    <path class="aura" d="M30 91 14 104 37 101 44 116 50 95" />
    <path class="aura" d="M98 91 114 104 91 101 84 116 78 95" />

    <path class="arm arm-left" d="M42 59 20 48 34 66 19 73 44 78" />
    <path class="arm arm-right" d="M86 59 108 48 94 66 109 73 84 78" />

    <path
      filter="url(#rotom-glow)"
      d="M64 28c19 0 32 14 32 33 0 23-15 39-32 39S32 84 32 61c0-19 13-33 32-33Z"
      fill="url(#rotom-body)"
    />
    <path d="M47 62c0-7 5-12 12-12h10c7 0 12 5 12 12 0 10-7 18-17 18S47 72 47 62Z" fill="#fff1d4" opacity="0.22" />
    <ellipse cx="52" cy="61" rx="8" ry="10" fill="#85f4ff" />
    <ellipse cx="76" cy="61" rx="8" ry="10" fill="#85f4ff" />
    <circle cx="54" cy="58" r="3" fill="#ffffff" />
    <circle cx="78" cy="58" r="3" fill="#ffffff" />
    <path d="M52 78c8 8 18 8 26 0" fill="none" stroke="#4a1d4f" stroke-width="5" stroke-linecap="round" />
    <path d="M60 84c5 2 10 2 15-1" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" opacity="0.75" />
    <circle cx="40" cy="30" r="2" fill="#2bd9fe" />
    <circle cx="91" cy="34" r="2" fill="#ffe66d" />
    <circle cx="103" cy="86" r="2" fill="#2bd9fe" />
  </svg>
</template>
