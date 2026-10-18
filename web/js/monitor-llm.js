/* モニターの「LLM 使用状況」(llama.cpp の /metrics。モデルが動いているときだけ表示) */
import {css, drawGauge, hhmm} from './charts.js';
import {state} from './state.js';
import {$} from './core.js';
import {f0, f1, ico, tile, tileHtml} from './monitor-parts.js';
// サンプルから、llama.cpp の指標(metrics が有効なときだけ)を取り出す
const llmOf=s=>{const L=s.apps&&s.apps.llama;return L&&L.metrics?L:null};
function llmDerive(D){
  const out=[];let prev=null;
  for(const s of D){
    const L=llmOf(s), r={t:s.t*1000,run:!!L,dp:0,dg:0,dps:0,dgs:0,dec:null,pre:null,total:L?L.prompt_tokens+L.gen_tokens:null};
    if(L&&prev){
      const dp=L.prompt_tokens-prev.prompt_tokens, dg=L.gen_tokens-prev.gen_tokens;
      if(dp>=0&&dg>=0){   // 負の差はモデルの再起動(累計のリセット)
        r.dp=dp;r.dg=dg;r.dps=L.prompt_seconds-prev.prompt_seconds;r.dgs=L.gen_seconds-prev.gen_seconds;
        if(dg>0&&r.dgs>0)r.dec=dg/r.dgs; if(dp>0&&r.dps>0)r.pre=dp/r.dps;
      }
    }
    prev=L;out.push(r);
  }
  return out;
}
const kfmt=n=>n>=1e6?(n/1e6).toFixed(2)+'M':n>=1e4?(n/1e3).toFixed(1)+'k':String(n);
export function llmDraw(D,ts,col,sp,ch,curL){
  const el=$('#mon-llm'), last=D[D.length-1].apps&&D[D.length-1].apps.llama;
  if(!last){el.innerHTML='';el._built=false;return}      // モデルが動いていないときは出さない
  if(last.metrics===false){el.innerHTML='<div class="mon-h">LLM 使用状況</div><div class="svc" style="padding:14px 18px"><span class="sub">llama-server が <code>--metrics</code> なしで動いているため、集計できません。ダッシュボードから起動すると、自動で有効になります。</span></div>';el._built=false;return}
  if(!el._built){
    el.innerHTML=`<div class="mon-h">LLM 使用状況 <span class="sub" id="llm-sub"></span></div><div class="mon-tiles">${tileHtml('ldec','生成速度','gpu')}${tileHtml('lpre','入力処理速度','vram')}${tileHtml('ltok','使用トークン','mem')}
      <div class="mtile"><div class="mt-h">${ico('io')}<span>コンテキスト</span></div><div style="display:flex;align-items:center;gap:14px;margin:8px 0 14px"><canvas id="lgauge" style="width:92px;height:92px;margin:0;flex:none"></canvas><div><div class="mt-v" style="margin:0"><b id="lgv">0</b><small>%</small></div><div class="mt-s" id="lgs" style="min-height:0">&nbsp;</div></div></div></div></div>
      <div class="svc" id="llm-recent" style="padding:14px 18px;margin-top:14px"></div>
      <div class="mon-grid" style="margin-top:14px">${[['lrate','トークン速度'],['ltotal','使用トークン(累計)']].map(([k,l])=>`<div class="svc mcard"><div class="mh"><b>${l}</b><span class="sub" id="mv-${k}"></span></div><canvas id="mc-${k}"></canvas></div>`).join('')}</div>`;
    el._built=true;
  }
  const dv=llmDerive(D), L=last, now=dv[dv.length-1];
  const sum=(a,k)=>a.reduce((x,r)=>x+(r[k]||0),0);
  const tps=(tok,sec)=>sec>0?tok/sec:null;
  const avgDec=tps(L.gen_tokens,L.gen_seconds), avgPre=tps(L.prompt_tokens,L.prompt_seconds);
  const lastDec=[...dv].reverse().find(r=>r.dec!=null), lastPre=[...dv].reverse().find(r=>r.pre!=null);
  const mxv=k=>Math.max(0,...dv.map(r=>r[k]||0));
  $('#llm-sub').textContent='モデル起動後の累計(モデルを入れ替えるとリセット)';
  tile('ldec',lastDec?f1(lastDec.dec):'–','tok/s',`最新 ${lastDec?hhmm(lastDec.t):'-'} · 平均 ${f1(avgDec)} · 最大 ${f1(mxv('dec'))}`);
  tile('lpre',lastPre?f0(lastPre.pre):'–','tok/s',`最新 ${lastPre?hhmm(lastPre.t):'-'} · 平均 ${f0(avgPre)} · 最大 ${f0(mxv('pre'))}`);
  tile('ltok',kfmt(L.prompt_tokens+L.gen_tokens),'tok',`入力 ${kfmt(L.prompt_tokens)} · 出力 ${kfmt(L.gen_tokens)}${L.cached_tokens?' · キャッシュ再利用 '+kfmt(L.cached_tokens):''}`);
  const nctx=L.n_ctx, frac=nctx?L.ctx_peak/nctx:0;
  $('#lgv').textContent=f0(frac*100);$('#lgs').innerHTML=`最大 ${kfmt(L.ctx_peak)} / ${kfmt(nctx)} tok<br>処理中 ${L.processing} · 待機 ${L.deferred}`;
  drawGauge($('#lgauge'),frac,frac>=.9?css('--err'):frac>=.7?css('--warn'):css('--ok'));
  const run=r=>r.run?1:null, zero=v=>v==null?0:v;
  sp('ldec',[{name:'生成',color:col[0],vals:dv.map(r=>r.run?zero(r.dec):null)}],{unit:'tok/s'});
  sp('lpre',[{name:'入力処理',color:col[1],vals:dv.map(r=>r.run?zero(r.pre):null)}],{unit:'tok/s',dec:0});
  sp('ltok',[{name:'累計',color:col[0],vals:dv.map(r=>r.total)}],{unit:'tok',dec:0});
  ch('lrate',[{name:'生成',color:col[0],vals:dv.map(r=>r.run?zero(r.dec):null)},{name:'入力処理',color:col[1],vals:dv.map(r=>r.run?zero(r.pre):null)}],{unit:'tok/s'});
  curL('lrate',[[`生成 ${lastDec?f1(lastDec.dec):'-'} tok/s`,col[0]],[`入力処理 ${lastPre?f0(lastPre.pre):'-'} tok/s`,col[1]]]);
  ch('ltotal',[{name:'入力',color:col[1],vals:D.map(s=>{const L=llmOf(s);return L?L.prompt_tokens:null})},{name:'出力',color:col[0],vals:D.map(s=>{const L=llmOf(s);return L?L.gen_tokens:null})}],{unit:'tok',dec:0});
  curL('ltotal',[[`入力 ${kfmt(L.prompt_tokens)}`,col[1]],[`出力 ${kfmt(L.gen_tokens)}`,col[0]]]);
  // 最近の処理: 連続して数値が増えた区間を1行にまとめる(5秒ごとの集計なので、リクエスト単位ではありません)
  const bursts=[];let cur=null;
  for(const r of dv){
    if(r.dp>0||r.dg>0){if(!cur){cur={t:r.t,n:0,dp:0,dg:0,dps:0,dgs:0};bursts.push(cur)}cur.n++;cur.dp+=r.dp;cur.dg+=r.dg;cur.dps+=r.dps;cur.dgs+=r.dgs}else cur=null;
  }
  $('#llm-recent').innerHTML=`<b>最近の処理</b> <span class="sub">(${intervalSec()} 秒ごとの集計から、連続した処理をまとめています)</span>`+
    (bursts.length?`<table style="margin-top:8px"><tr><th>時刻</th><th>入力</th><th>出力</th><th>入力処理 tok/s</th><th>生成 tok/s</th><th>継続(約)</th></tr>`+
      bursts.slice(-10).reverse().map(b=>`<tr><td>${hhmm(b.t)}</td><td>${b.dp}</td><td>${b.dg}</td><td>${b.dps>0&&b.dp>0?f0(b.dp/b.dps):'-'}</td><td>${b.dgs>0&&b.dg>0?f1(b.dg/b.dgs):'-'}</td><td>${b.n*intervalSec()} 秒</td></tr>`).join('')+`</table>`:`<div class="sub" style="margin-top:6px">まだ処理がありません</div>`);
}
const intervalSec=()=>(state.monMeta&&state.monMeta.interval)||5;
