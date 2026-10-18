/* グラフ描画の道具(外部ライブラリなし): 折れ線(軸・凡例・ホバー)・タイルの小さな推移グラフ */
import {$, esc} from './core.js';
export const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function niceMax(m){if(!(m>0))return 1;const p=Math.pow(10,Math.floor(Math.log10(m)));for(const f of [1,2,5,10]) if(m<=f*p) return f*p;return 10*p}
function downsample(ts,series,maxPts){
  const n=ts.length;if(n<=maxPts)return {ts,series};
  const step=Math.ceil(n/maxPts), t2=[], s2=series.map(s=>({...s,vals:[]}));
  for(let i=0;i<n;i+=step){
    const e=Math.min(n,i+step);t2.push(ts[e-1]);
    series.forEach((s,k)=>{let sum=0,c=0;for(let j=i;j<e;j++){if(s.vals[j]!=null){sum+=s.vals[j];c++}}s2[k].vals.push(c?sum/c:null)});
  }
  return {ts:t2,series:s2};
}
export const hhmm=t=>{const d=new Date(t);return String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')};
function setup(cv){const dpr=window.devicePixelRatio||1,W=cv.clientWidth,H=cv.clientHeight;if(!W||!H)return null;cv.width=W*dpr;cv.height=H*dpr;const g=cv.getContext('2d');g.scale(dpr,dpr);return {g,W,H}}
export function drawChart(cv,ts0,series0,o){
  const c=setup(cv);if(!c)return;const {g,W,H}=c;
  const {ts,series}=downsample(ts0,series0,Math.max(60,Math.floor(W-50)));
  const L=40,R=8,T=8,B=20, pw=W-L-R, ph=H-T-B;
  let ymax=o.ymax;if(!ymax){let m=0;series.forEach(s=>s.vals.forEach(v=>{if(v!=null&&v>m)m=v}));ymax=niceMax(m)}
  const x0=ts[0], x1=ts[ts.length-1], span=Math.max(1,x1-x0);
  const X=t=>L+(t-x0)/span*pw, Y=v=>T+ph-(Math.min(v,ymax)/ymax)*ph;
  g.font='11px system-ui, sans-serif';g.lineWidth=1;
  g.strokeStyle=css('--line');g.fillStyle=css('--mute');
  for(const f of [0,.5,1]){const y=T+ph-f*ph;g.beginPath();g.moveTo(L,y);g.lineTo(W-R,y);g.stroke();g.textAlign='right';g.fillText((ymax*f).toFixed(ymax<10&&f?1:0),L-4,y+4)}
  const mins=span/60000, step=[1,2,5,10,15,30,60,120].find(s=>mins/s<=6)||180;
  g.textAlign='center';
  for(let t=Math.ceil(x0/(step*60000))*step*60000;t<=x1;t+=step*60000){g.fillText(hhmm(t),X(t),H-5)}
  series.forEach(s=>{
    g.strokeStyle=s.color;g.lineWidth=1.6;g.beginPath();let pen=false;
    s.vals.forEach((v,i)=>{if(v==null){pen=false;return}const x=X(ts[i]),y=Y(v);pen?g.lineTo(x,y):g.moveTo(x,y);pen=true});
    g.stroke();
  });
  cv._m={ts,series,o,L,pw};
  if(cv._hover!=null&&cv._hover<ts.length){
    const i=cv._hover,x=X(ts[i]);g.strokeStyle=css('--mute');g.lineWidth=1;g.beginPath();g.moveTo(x,T);g.lineTo(x,T+ph);g.stroke();
    series.forEach(s=>{if(s.vals[i]!=null){g.fillStyle=s.color;g.beginPath();g.arc(x,Y(s.vals[i]),3,0,7);g.fill()}});
  }
}
export function drawSpark(cv,ts0,series0,o){  // タイル用: 軸なし・塗りつぶしの小さな推移グラフ
  const c=setup(cv);if(!c)return;const {g,W,H}=c;
  const {ts,series}=downsample(ts0,series0,Math.max(40,Math.floor(W)));
  const T=4,B=2, ph=H-T-B;
  let ymax=o.ymax, ymin=0;
  if(o.fit){  // 温度など「ほぼ一定」の値: 最小〜最大の範囲に合わせて変化が見えるようにする
    let lo=1e9,hi=-1e9;series.forEach(s=>s.vals.forEach(v=>{if(v!=null){lo=Math.min(lo,v);hi=Math.max(hi,v)}}));
    const pad=Math.max(3,(hi-lo)*.25);ymin=Math.max(0,lo-pad);ymax=hi+pad;
  }else if(!ymax){let m=0;series.forEach(s=>s.vals.forEach(v=>{if(v!=null&&v>m)m=v}));ymax=niceMax(m)}
  const x0=ts[0], span=Math.max(1,ts[ts.length-1]-x0);
  const X=t=>(t-x0)/span*W, Y=v=>T+ph-((Math.min(Math.max(v,ymin),ymax)-ymin)/(ymax-ymin))*ph;
  series.forEach(s=>{
    const pts=[];s.vals.forEach((v,i)=>{if(v!=null)pts.push([X(ts[i]),Y(v)])});
    if(pts.length<2)return;
    g.beginPath();pts.forEach(([x,y],i)=>i?g.lineTo(x,y):g.moveTo(x,y));
    g.strokeStyle=s.color;g.lineWidth=1.8;g.lineJoin='round';g.stroke();
    g.lineTo(pts[pts.length-1][0],H);g.lineTo(pts[0][0],H);g.closePath();
    const gr=g.createLinearGradient(0,T,0,H);gr.addColorStop(0,s.color);gr.addColorStop(1,s.color);
    g.globalAlpha=series.length>1?.10:.16;g.fillStyle=gr;g.fill();g.globalAlpha=1;
  });
  cv._m={ts,series,o,L:0,pw:W};
  if(cv._hover!=null&&cv._hover<ts.length){
    const i=cv._hover,x=X(ts[i]);g.strokeStyle=css('--mute');g.lineWidth=1;g.beginPath();g.moveTo(x,0);g.lineTo(x,H);g.stroke();
    series.forEach(s=>{if(s.vals[i]!=null){g.fillStyle=s.color;g.beginPath();g.arc(x,Y(s.vals[i]),3,0,7);g.fill()}});
  }
}
function wireHover(cv){
  if(cv._wired)return;cv._wired=true;const tip=$('#mon-tip');
  cv.onmousemove=e=>{
    const m=cv._m;if(!m)return;const r=cv.getBoundingClientRect(), x=e.clientX-r.left;
    let i=Math.round(((x-m.L)/m.pw)*(m.ts.length-1));i=Math.max(0,Math.min(m.ts.length-1,i));
    cv._hover=i;cv._redraw();
    tip.style.display='block';tip.style.left=Math.min(window.innerWidth-200,e.clientX+12)+'px';tip.style.top=(e.clientY+14)+'px';
    tip.innerHTML=`<b>${hhmm(m.ts[i])}</b>`+m.series.map(s=>`<div><span style="color:${s.color}">●</span> ${esc(s.name)}: ${s.vals[i]==null?'-':s.vals[i].toFixed(m.o.dec??1)} ${m.o.unit}</div>`).join('');
  };
  cv.onmouseleave=()=>{cv._hover=null;tip.style.display='none';if(cv._redraw)cv._redraw()};
}
export function plot(cv,fn,ts,series,o){cv._redraw=()=>fn(cv,ts,series,o);wireHover(cv);cv._redraw()}
export function drawGauge(cv,frac,color){
  const c=setup(cv);if(!c)return;const {g,W,H}=c, cx=W/2, cy=H/2, R=Math.min(W,H)/2-7;
  g.lineWidth=9;g.lineCap='round';
  g.strokeStyle=css('--line');g.beginPath();g.arc(cx,cy,R,.75*Math.PI,2.25*Math.PI);g.stroke();
  if(frac>0){g.strokeStyle=color;g.beginPath();g.arc(cx,cy,R,.75*Math.PI,.75*Math.PI+Math.min(1,frac)*1.5*Math.PI);g.stroke()}
}
