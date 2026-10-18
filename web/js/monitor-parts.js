/* モニターのタイルの部品(アイコン・タイルの枠・数字の書き込み・数字の整形)。monitor.js と monitor-llm.js が共有する */
import {$} from './core.js';
const ICON={
  cpu:'<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  mem:'<path d="M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5"/>',
  gpu:'<rect x="2" y="6" width="20" height="11" rx="2"/><circle cx="9" cy="11.5" r="2.5"/><path d="M15 9h4M15 14h4M6 20h12"/>',
  vram:'<rect x="3" y="7" width="18" height="10" rx="2"/><path d="M7 7V4M12 7V4M17 7V4M7 20v-3M12 20v-3M17 20v-3"/>',
  temp:'<path d="M14 14.8V5a2 2 0 0 0-4 0v9.8a4 4 0 1 0 4 0z"/>',
  pow:'<path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z"/>',
  io:'<rect x="3" y="13" width="18" height="7" rx="2"/><path d="M5.5 13l2-8h9l2 8M17 16.5h.01"/>',
  cap:'<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
};
export const ico=k=>`<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICON[k]}</svg>`;
export const tileHtml=(k,l,i)=>`<div class="mtile"><div class="mt-h">${ico(i)}<span>${l}</span></div>
  <div class="mt-v"><b id="mtv-${k}">–</b><small id="mtu-${k}"></small></div><div class="mt-s" id="mts-${k}">&nbsp;</div>
  ${k==='dcap'?'<div class="prog" id="mtb-dcap" style="margin-top:18px"><i></i></div>':`<canvas id="ms-${k}"></canvas>`}</div>`;
export const f1=v=>v==null?'-':v.toFixed(1), f0=v=>v==null?'-':v.toFixed(0);
export function tile(k,big,unit,sub){$('#mtv-'+k).textContent=big;$('#mtu-'+k).textContent=unit||'';$('#mts-'+k).innerHTML=sub||'&nbsp;'}
