/* モニタータブ: タイルの構成・5秒ごとの取得・PC の情報・リソース使用状況・詳細グラフ */
import {state, SV} from './state.js';
import {$, api, esc} from './core.js';
import {css, drawChart, drawSpark, plot} from './charts.js';
import {llmDraw} from './monitor-llm.js';
import {f0, f1, tile, tileHtml} from './monitor-parts.js';
let MONS=[], monTimer=null;
const SYS_TILES=[['cpu','CPU','cpu'],['mem','メモリ','mem'],['dio','SSD 読み書き','io'],['dcap','SSD 容量','cap']];
const GPU_TILES=[['util','使用率','gpu'],['vram','VRAM','vram'],['temp','温度','temp'],['pow','消費電力','pow']];
const CHARTS=[['cpu','CPU'],['mem','メモリ'],['gutil','GPU 使用率'],['gvram','GPU VRAM'],['gtemp','GPU 温度'],['gpow','GPU 消費電力'],['dio','SSD 読み書き']];
let BUILT_G=-1;
document.body.insertAdjacentHTML('beforeend','<div id="mon-tip"></div>');
function monBuild(nG){  // GPU の枚数に合わせて、GPU ごとのタイル行を作る
  BUILT_G=nG;
  const gm=(state.monMeta&&state.monMeta.gpus)||[];
  let gh='';
  for(let i=0;i<nG;i++) gh+=`<div class="mon-h">GPU ${i} <span class="sub">${esc((gm[i]||{}).name||'')}</span></div><div class="mon-tiles">${GPU_TILES.map(([k,l,ic])=>tileHtml(`g${i}-${k}`,l,ic)).join('')}</div>`;
  $('#tab-mon').innerHTML=`
<div class="mon-top"><span class="sub" id="mon-note"></span></div>
<div class="svc mstat" id="mon-status"></div>
<div class="svc mstat" id="mon-pc"></div>
<div id="mon-llm"></div>
<div class="mon-tiles">${SYS_TILES.map(([k,l,i])=>tileHtml(k,l,i)).join('')}</div>
${gh}
<div class="svc" id="mon-bars" style="padding:16px 18px;margin-top:14px"></div>
<div class="mon-h">詳細グラフ <span class="sub">(マウスを乗せると、その時刻の値が出ます)</span></div>
<div class="mon-grid">${CHARTS.map(([k,l])=>`<div class="svc mcard"><div class="mh"><b>${l}</b><span class="sub" id="mv-${k}"></span></div><canvas id="mc-${k}"></canvas></div>`).join('')}</div>`;
  monStatus();
}
monBuild(0);
async function monFetch(){
  try{
    const since=MONS.length?MONS[MONS.length-1].t:0;
    const r=await api('/api/monitor?since='+since);
    state.monMeta=r.meta;MONS.push(...r.samples);
    const keep=Math.ceil((state.monMeta.hours||3)*3600/(state.monMeta.interval||5));
    if(MONS.length>keep) MONS.splice(0,MONS.length-keep);
    monDraw();
  }catch(e){}
}
export function monStart(){monFetch();monStatus();clearInterval(monTimer);monTimer=setInterval(monFetch,((state.monMeta&&state.monMeta.interval)||5)*1000)}
export function monStop(){clearInterval(monTimer)}
window.addEventListener('resize',()=>{if(state.tab==='mon')monDraw()});
const avg=a=>{const v=a.filter(x=>x!=null);return v.length?v.reduce((x,y)=>x+y,0)/v.length:null};
const mx=a=>{const v=a.filter(x=>x!=null);return v.length?Math.max(...v):null};
const lvl=p=>p>=90?'var(--err)':p>=70?'var(--warn)':'var(--ok)';
export function monStatus(){
  if(!state.status)return;const el=$('#mon-status');
  const chips=SV().filter(([k,s])=>s.installed).map(([k,s])=>{
    const st={running:'稼働中',starting:'起動中…',stopped:'停止'}[s.state];
    return `<span class="chip"><i class="dot ${s.state}"></i><b>${esc(s.label)}</b><span class="sub">${st}${s.pname&&s.state!=='stopped'?' · '+esc(s.pname):''}${s.set&&s.state!=='stopped'?' · '+esc(s.set):''}</span></span>`}).join('');
  const run=Object.values(state.status.services).filter(s=>s.enabled&&s.state==='running').length;
  el.innerHTML=`<div class="row" style="justify-content:space-between;margin-bottom:10px"><b>サービスの状態</b><span class="sub">${run?run+' 件が稼働中':'稼働中のサービスはありません'}</span></div><div class="row" style="gap:8px">${chips}</div>`;
}
function monDraw(){
  if(state.monMeta&&(state.monMeta.gpus||[]).length!==BUILT_G) monBuild((state.monMeta.gpus||[]).length);
  const note=$('#mon-note');
  if(!MONS.length||!state.monMeta){note.textContent='データを収集しています…(最初の点が出るまで数秒かかります)';return}
  const m=state.monMeta, all=MONS, last=all[all.length-1];
  const D=all;  // 保持している全期間(最大 3 時間)
  const have=(last.t-all[0].t)/60;
  note.textContent=`${m.interval} 秒ごとに記録 · 保持 ${have<60?Math.max(1,Math.round(have))+' 分':(have/60).toFixed(1)+' 時間'} / 最大 ${m.hours} 時間 · ハブを停止するとリセット`;
  const pc=m.pc||{};
  const pcRows=[['ホスト名',pc.hostname],['OS',[pc.os,pc.kernel?'Linux '+pc.kernel:'',pc.arch].filter(Boolean).join(' · ')],
    ['CPU',`${pc.cpu_model||'-'}${pc.cores?' · '+pc.cores+' コア':''} / ${m.cpus} スレッド`],['メモリ',`${m.mem_total_gb.toFixed(0)} GB`+(m.swap_total_gb>0.1?`(スワップ ${m.swap_total_gb.toFixed(0)} GB)`:'')],
    ...(m.gpus||[]).map((g,i)=>[`GPU ${i}`,`${g.name} · VRAM ${((g.mem_total||0)/1024).toFixed(0)} GB`]),['GPU ドライバ',pc.gpu_driver||'-']].filter(r=>r[1]);
  $('#mon-pc').innerHTML=`<b>このPC</b><div class="pcgrid">${pcRows.map(([l,v])=>`<div class="pr"><span>${esc(l)}</span><span>${esc(v)}</span></div>`).join('')}</div>`;
  const ts=D.map(s=>s.t*1000);if(ts.length<2){return}
  const col=[css('--c1'),css('--c2'),css('--c3'),css('--c4')];
  const nG=last.gpus.length, gl=last.gpus;
  const sp=(k,series,o)=>plot($('#ms-'+k),drawSpark,ts,series,o), ch=(k,series,o)=>plot($('#mc-'+k),drawChart,ts,series,o);
  const curL=(el,items)=>{$('#mv-'+el).innerHTML=items.map(([t,c])=>`<span style="color:${c}">●</span> ${esc(t)}`).join(' &nbsp; ')};
  // --- CPU
  const cpuS=[{name:'CPU',color:col[0],vals:D.map(s=>s.cpu)}];
  tile('cpu',f1(last.cpu),'%',`平均 ${f1(avg(cpuS[0].vals))}% · 最大 ${f1(mx(cpuS[0].vals))}%`);
  sp('cpu',cpuS,{ymax:100,unit:'%'});ch('cpu',cpuS,{ymax:100,unit:'%'});$('#mv-cpu').textContent=`${f1(last.cpu)} %  (${m.cpus} スレッド)`;
  // --- メモリ
  const memS=[{name:'使用',color:col[0],vals:D.map(s=>s.mem)},{name:'スワップ',color:col[2],vals:D.map(s=>s.swap)}];
  const mp=last.mem/m.mem_total_gb*100;
  tile('mem',f1(last.mem),`/ ${m.mem_total_gb.toFixed(0)} GB`,`${mp.toFixed(0)}% 使用 · 最大 ${f1(mx(memS[0].vals))} GB${last.swap>0.05?' · スワップ '+f1(last.swap)+' GB':''}`);
  sp('mem',[memS[0]],{ymax:Math.ceil(m.mem_total_gb),unit:'GB'});ch('mem',memS,{ymax:Math.ceil(m.mem_total_gb),unit:'GB'});
  curL('mem',[[`使用 ${f1(last.mem)} / ${m.mem_total_gb.toFixed(1)} GB (${mp.toFixed(0)}%)`,col[0]],[`スワップ ${f1(last.swap)} GB`,col[2]]]);
  // --- GPU(1枚ごとのタイル + 全GPUを重ねた詳細グラフ)
  const GCOL=[...col,'#8b5cf6','#06b6d4','#ec4899','#64748b'];
  if(nG){
    const gm=m.gpus||[], vmaxAll=Math.ceil(Math.max(...gm.map(g=>g.mem_total||0))/1024)||12;
    const pmaxAll=Math.ceil(Math.max(...gm.map(g=>g.power_limit||0))/10)*10||200;
    const one=(i,key,scale=1)=>[{name:`GPU${i}`,color:GCOL[i%GCOL.length],vals:D.map(s=>{const v=s.gpus[i]&&s.gpus[i][key];return v==null?null:v/scale})}];
    gl.forEach((g,i)=>{
      const mt=(gm[i]||{}), u=one(i,'util'), vr=one(i,'vram',1024), tp=one(i,'temp'), pw=one(i,'power');
      tile(`g${i}-util`,f0(g.util),'%',`平均 ${f0(avg(u[0].vals))}% · 最大 ${f0(mx(u[0].vals))}%`);
      sp(`g${i}-util`,u,{ymax:100,unit:'%',dec:0});
      const vt=(mt.mem_total||0)/1024, vp=vt?g.vram/1024/vt*100:0;
      tile(`g${i}-vram`,f1(g.vram/1024),`/ ${vt.toFixed(0)} GB`,`${vp.toFixed(0)}% 使用 · 最大 ${f1(mx(vr[0].vals))} GB`);
      sp(`g${i}-vram`,vr,{ymax:vt||vmaxAll,unit:'GB'});
      tile(`g${i}-temp`,f0(g.temp),'℃',`最大 ${f0(mx(tp[0].vals))}℃ · 最小 ${f0(Math.min(...tp[0].vals.filter(x=>x!=null)))}℃`);
      sp(`g${i}-temp`,tp,{fit:true,unit:'℃',dec:0});
      tile(`g${i}-pow`,f0(g.power),'W',`上限 ${f0(mt.power_limit)} W · 最大 ${f0(mx(pw[0].vals))} W`);
      sp(`g${i}-pow`,pw,{ymax:mt.power_limit||pmaxAll,unit:'W',dec:0});
    });
    const all=(key,scale=1)=>gl.flatMap((_,i)=>one(i,key,scale));
    ch('gutil',all('util'),{ymax:100,unit:'%',dec:0});curL('gutil',gl.map((g,i)=>[`GPU${i} ${g.util??'-'}%`,GCOL[i%GCOL.length]]));
    ch('gvram',all('vram',1024),{ymax:vmaxAll,unit:'GB'});curL('gvram',gl.map((g,i)=>[`GPU${i} ${(g.vram/1024).toFixed(1)}/${((gm[i]||{}).mem_total/1024).toFixed(0)} GB`,GCOL[i%GCOL.length]]));
    ch('gtemp',all('temp'),{ymax:100,unit:'℃',dec:0});curL('gtemp',gl.map((g,i)=>[`GPU${i} ${g.temp??'-'}℃`,GCOL[i%GCOL.length]]));
    ch('gpow',all('power'),{ymax:pmaxAll,unit:'W',dec:0});curL('gpow',gl.map((g,i)=>[`GPU${i} ${g.power!=null?g.power.toFixed(0):'-'} W`,GCOL[i%GCOL.length]]));
  }else{for(const k of ['gutil','gvram','gtemp','gpow'])$('#mv-'+k).textContent='GPU が見つかりません(nvidia-smi)'}
  // --- SSD
  if(m.disk_has_io){
    const io=[{name:'読み込み',color:col[0],vals:D.map(s=>s.disk_read)},{name:'書き込み',color:col[2],vals:D.map(s=>s.disk_write)}];
    tile('dio',f1(last.disk_read),'MB/s 読',`書き込み ${f1(last.disk_write)} MB/s · 最大 読 ${f1(mx(io[0].vals))} / 書 ${f1(mx(io[1].vals))}`);
    sp('dio',io,{unit:'MB/s'});ch('dio',io,{unit:'MB/s'});curL('dio',[[`読み込み ${f1(last.disk_read)} MB/s`,col[0]],[`書き込み ${f1(last.disk_write)} MB/s`,col[2]]]);
  }else{tile('dio','–','','この環境では取得できません')}
  const dp=last.disk_used/m.disk_total_gb*100;
  tile('dcap',f0(last.disk_used),`/ ${m.disk_total_gb.toFixed(0)} GB`,`${dp.toFixed(0)}% 使用 · ${f0(m.disk_total_gb-last.disk_used)} GB 空き`);
  const bar=$('#mtb-dcap i');bar.style.width=dp+'%';bar.style.background=lvl(dp);
  // --- リソース使用状況(バー)
  const rows=[];
  rows.push(['CPU 使用率',`${f1(last.cpu)} %`,last.cpu]);
  gl.forEach((g,i)=>{const t=(m.gpus[i]||{}).mem_total;if(t)rows.push([`GPU${i} VRAM`,`${(g.vram/1024).toFixed(1)} / ${(t/1024).toFixed(0)} GB`,g.vram/t*100])});
  rows.push(['システムメモリ',`${f1(last.mem)} / ${m.mem_total_gb.toFixed(0)} GB`,mp]);
  if(m.swap_total_gb>0.1)rows.push(['スワップ',`${f1(last.swap)} / ${m.swap_total_gb.toFixed(0)} GB`,last.swap/m.swap_total_gb*100]);
  gl.forEach((g,i)=>{if(g.temp!=null)rows.push([`GPU${i} 温度`,`${Math.round(g.temp)} ℃`,g.temp])});
  rows.push(['SSD 容量',`${f0(last.disk_used)} / ${m.disk_total_gb.toFixed(0)} GB`,dp]);
  llmDraw(D,ts,col,sp,ch,curL);
  $('#mon-bars').innerHTML=`<b>リソース使用状況</b><div class="bars">${rows.map(([l,v,p])=>`<div><div class="bl"><span>${esc(l)}</span><span>${esc(v)}</span></div><div class="bt"><i style="width:${Math.min(100,p)}%;background:${lvl(p)}"></i></div></div>`).join('')}</div>`;
}

// テーマを変えたときに、グラフの色を読み直す
export function redrawMonitor(){if(MONS.length)monDraw()}
