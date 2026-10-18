/* サービスタブ: サービスのカード・llama.cpp のモデルタイル・未導入のサービス */
import {base, presetsOf, state} from './state.js';
import {$, act, esc, gb} from './core.js';
import {PANEL, drawPanel, selectModel} from './llama-panel.js';
import {SELS, SP, drawSPanel, svcDialog} from './script-panel.js';
import {keyDialog, showLog} from './dialogs.js';
export function renderDash(){
  let h='';
  for(const [name,s] of Object.entries(state.status.services)){
    if(!(s.enabled&&s.installed)) continue;
    const ps=state.status.presets.filter(p=>p.service===name);
    const st={running:'稼働中',starting:'起動中…',stopped:'停止'}[s.state];
    h+=`<div class="svc"><div class="svc-h"><span class="dot ${s.state}"></span><b>${esc(s.label)}</b>${s.version?` <span class="tag" title="${esc(s.version.full)}">${esc(s.version.short)}</span>`:''}
      <span class="sub">${st}${s.pname?' · '+esc(s.pname):''}${s.set?' · セット: '+esc(s.set):''}${s.external?' · 外部起動':''}${s.port?' · :'+s.port:''}</span>
      ${s.key==='needed'?'<span class="tag new">🔑 APIキー未登録</span>':''}<span class="sp"></span>
      ${s.key?`<button class="b" data-a="key" data-s="${name}">🔑 APIキー</button>`:''}
      ${s.state==='running'&&s.port?`<a class="b" href="http://${location.hostname}:${s.port}" target="_blank">開く ↗</a>`:''}
      <button class="b" data-a="svccfg" data-s="${name}" title="場所・ポートなどの設定">⚙</button>
      <button class="b" data-a="log" data-s="${name}">ログ</button>
      <button class="b d" data-a="stop" data-s="${name}" ${s.state==='stopped'?'disabled':''}>停止</button></div>`;
    if(s.type==='llama'){
      const paths=[...new Set([...state.models.map(m=>m.path),...ps.map(p=>p.model).filter(Boolean)])]
        .sort((a,b)=>(presetsOf(b).length?1:0)-(presetsOf(a).length?1:0)||a.localeCompare(b));
      h+=`<div class="split"><div class="tiles">`+paths.map(path=>{
        const mi=state.models.find(m=>m.path===path), n=presetsOf(path).length, run=s.state!=='stopped'&&s.model===path;
        return `<div class="tile ${state.sel===path?'sel':''} ${run?'run':''}" data-a="tile" data-m="${esc(path)}"><div class="tn">${esc(base(path))}</div>
          <div class="sub">${mi?gb(mi.size)+(mi.shards>1?' · '+mi.shards+'分割':''):'⚠ ファイルなし'}</div>
          <div class="tb">${run?'<span class="dot running"></span><span class="sub">稼働中</span>':''}<span class="tag">${n?'★ '+n:'未設定'}</span></div></div>`}).join('')
        +`</div><div class="pslot" data-svc="${name}"></div></div>`;
    }else{
      const items=ps.slice().sort((x,y)=>(y.favorite?1:0)-(x.favorite?1:0)).map(p=>({k:'p:'+p.id,n:p.name,sub:p.note||base(p.cmd),run:s.state!=='stopped'&&s.preset===p.id,tag:p.favorite?'★':''}))
        .concat((s.unregistered||[]).map(u=>({k:'u:'+u,n:base(u).replace(/\.sh$/,''),sub:'未登録スクリプト',tag:'未登録'})));
      h+=`<div class="split"><div class="tiles">`+items.map(t=>`<div class="tile ${SELS[name]===t.k?'sel':''} ${t.run?'run':''}" data-a="stile" data-s="${name}" data-k="${esc(t.k)}"><div class="tn">${esc(t.n)}</div>
          <div class="sub">${esc(t.sub)}</div><div class="tb">${t.run?'<span class="dot running"></span><span class="sub">稼働中</span>':''}${t.tag?`<span class="tag">${t.tag}</span>`:''}</div></div>`).join('')
        +`<div class="tile ${SELS[name]==='new'?'sel':''}" style="border-style:dashed;align-items:center;justify-content:center" data-a="stile" data-s="${name}" data-k="new">＋ 追加</div></div><div class="pslot" data-svc="${name}"></div></div>`;
    }
    h+='</div>';
  }
  const off=Object.entries(state.status.services).filter(([k,s])=>!(s.enabled&&s.installed));
  if(off.length) h+=`<div class="svc" style="padding:14px 18px"><b>未導入・非表示のサービス (${off.length})</b><div class="sub" style="margin:2px 0 8px">使わないサービスや、まだ入れていないサービスは、ここにまとめています。</div>`+off.map(([k,s])=>`<div class="row" style="gap:10px;padding:10px 0;border-top:1px solid var(--line);align-items:center">
      <div style="flex:1;min-width:230px"><b>${esc(s.label)}</b> <span class="tag">${!s.enabled?'使わない':'未導入'}</span><div class="sub">探した場所: ${esc(s.dir_resolved)}</div>
      ${(s.candidates||[]).map(c=>`<div class="sub">見つかりました: <code>${esc(c)}</code> <button class="b" data-a="usecand" data-s="${k}" data-p="${esc(c)}">これを使う</button></div>`).join('')}</div>
      ${s.homepage?`<a class="b" href="${esc(s.homepage)}" target="_blank" rel="noopener">インストール手順 ↗</a>`:''}
      <button class="b" data-a="svccfg" data-s="${k}">場所を指定…</button>
      ${!s.enabled?`<button class="b p" data-a="svcon" data-s="${k}">使う</button>`:`<button class="b" data-a="svcoff" data-s="${k}">使わない</button>`}</div>`).join('')+`</div>`;
  $('#tab-dash').innerHTML=h;
  document.querySelectorAll('#tab-dash .pslot').forEach(slot=>{
    const n=slot.dataset.svc;
    if(state.status.services[n].type==='llama'){slot.appendChild(PANEL);if(!PANEL.firstChild)drawPanel(null)}
    else{if(!SP[n])drawSPanel(n);slot.appendChild(SP[n])}
  });
}

// サービスタブ内のクリックを、data-a 属性で振り分ける(イベント委譲)
$('#tab-dash').onclick=e=>{
  const b=e.target.closest('[data-a]'); if(!b) return;
  const {a,s,id,p,m}=b.dataset;
  if(a==='tile') selectModel(m);
  else if(a==='stile'){const {k}=b.dataset;SELS[s]=k;drawSPanel(s);renderDash()}
  else if(a==='stop') act('/api/stop',{service:s});
  else if(a==='key') keyDialog(s);
  else if(a==='log') showLog(s);
  else if(a==='svccfg') svcDialog(s);
  else if(a==='usecand') act('/api/service/config',{service:s,dir:p.replace(/^\/home\/[^/]+/,'~'),enabled:true});
  else if(a==='svcon') act('/api/service/config',{service:s,enabled:true});
  else if(a==='svcoff') act('/api/service/config',{service:s,enabled:false});
};
