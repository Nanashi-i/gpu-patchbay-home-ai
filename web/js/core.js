/* 共通の道具: DOM の取得・エスケープ・API 呼び出し・単位の整形 */
import {hooks} from './state.js';
export const $=s=>document.querySelector(s);
export const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let TOKEN=localStorage.getItem('patchbay-token')||'';

export async function api(path,body){
  const o={headers:{'X-Token':TOKEN}};
  if(body!==undefined){o.method='POST';o.headers['Content-Type']='application/json';o.body=JSON.stringify(body)}
  const r=await fetch(path,o);
  if(r.status===401){
    const t=prompt('アクセストークン(machine.json の token)を入力');
    if(!t) throw new Error('トークンが必要です');
    TOKEN=t;localStorage.setItem('patchbay-token',t);return api(path,body);
  }
  const j=await r.json();
  if(!r.ok) throw new Error(j.error||r.statusText);
  return j;
}
export const act=async(p,b)=>{try{await api(p,b)}catch(e){alert(e.message)}hooks.refresh()};
export const gb=n=>n==null?'?':n>=1073741824?(n/1073741824).toFixed(1)+' GB':(n/1048576).toFixed(0)+' MB';
export const mb=n=>(n/1048576).toFixed(0)+' MB';
