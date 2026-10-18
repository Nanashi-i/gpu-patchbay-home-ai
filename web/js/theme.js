/* テーマの切り替え。一覧は /themes.json(web/css/themes/<id>.css の先頭のコメントから、サーバーが自動で作る)。
   テーマを足すには、web/css/themes/ に CSS を1つ置くだけ(書き方は patchbay/api/static.py の先頭を参照) */
import {state} from './state.js';
import {$, esc} from './core.js';
import {redrawMonitor} from './monitor.js';
let THEMES=[];   // [{id, name, swatch[], note}]
function applyTheme(id){
  if(id) document.documentElement.dataset.theme=id; else delete document.documentElement.dataset.theme;
  try{localStorage.setItem('patchbay-theme',id)}catch(e){}
  drawThemeMenu();
  if(state.tab==='mon') redrawMonitor();   // グラフは色を読み直す
}
function drawThemeMenu(){
  const cur=document.documentElement.dataset.theme||'';
  $('#tp-pop').innerHTML=THEMES.map(t=>`<button data-t="${esc(t.id)}" class="${t.id===cur?'on':''}" title="${esc(t.name+(t.note?'('+t.note+')':''))}" aria-label="${esc(t.name)}"><span class="sw">${t.swatch.map(c=>`<i style="background:${c}"></i>`).join('')}</span></button>`).join('');
}
$('#tp-btn').onclick=e=>{e.stopPropagation();$('#tp-pop').classList.toggle('hide')};
$('#tp-pop').onclick=e=>{const b=e.target.closest('button[data-t]');if(b){applyTheme(b.dataset.t);$('#tp-pop').classList.add('hide')}};
document.addEventListener('click',e=>{if(!e.target.closest('.tp'))$('#tp-pop').classList.add('hide')});
fetch('/themes.json').then(r=>r.json()).then(t=>{THEMES=t;drawThemeMenu()}).catch(()=>{});
