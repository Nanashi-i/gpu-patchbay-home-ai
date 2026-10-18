/* llama.cpp のモデルを選んだときの、右のパネル(お気に入り・パラメータ・フラグのチェックボックス) */
import {LL, base, hooks, presetsOf, state} from './state.js';
import {act, api, esc, gb} from './core.js';
import {pathHint} from './dialogs.js';
export const PANEL=document.createElement('div');PANEL.className='panel';   // 右のパネル(ダッシュボードが、ここを差し込む)
const FORM=[['ctx','コンテキスト長'],['reasoning','reasoning'],['temp','temperature'],['top_p','top_p'],['top_k','top_k'],['min_p','min_p'],
  ['ngl','GPU層数(-ngl)'],['server_dir','llama.cpp の場所(任意)'],['extra','その他の追加フラグ'],['note','メモ']];
export function selectModel(m){
  state.sel=m;const list=presetsOf(m), d=list.find(p=>p.favorite)||list[0];
  drawPanel(d?d.id:null);hooks.renderDash();
}
// 値の入力欄: 「▼」から候補を選べ、直接の入力もできる(候補は目安。値は自由に書き換えられます)
const FIELD_OPTS={
  ctx:[['2048',''],['4096',''],['8192',''],['16384',''],['32768',''],['65536',''],['98304','96K'],['131072','128K'],['262144','256K']],
  reasoning:[['auto','テンプレ任せ'],['off','thinking を無効化'],['-1','無制限'],['100','予算 100 トークン'],['500','予算 500'],['1000','予算 1000'],['4096','予算 4096']],
  temp:[['0','決定的'],['0.3','低め'],['0.6',''],['0.7','標準的'],['0.8',''],['1.0','高め'],['1.2','かなり高め']],
  top_p:[['0.8',''],['0.9',''],['0.95','標準的'],['1.0','無効']],
  top_k:[['0','無効'],['20','Qwen 推奨'],['40',''],['64',''],['100','']],
  min_p:[['0','無効'],['0.01',''],['0.05',''],['0.1','']],
  ngl:[['999','全層を GPU'],['auto','自動(--fit 併用時)'],['0','CPU のみ'],['20',''],['40','']],
};
function comboHtml(k,x){
  return `<div class="row" style="flex-wrap:nowrap;gap:4px"><input name="${k}" value="${esc(x)}" style="flex:1;min-width:0">
    <select class="combo" data-for="${k}" title="候補から選ぶ"><option value=""></option>${FIELD_OPTS[k].map(([v,n])=>`<option value="${esc(v)}">${esc(v)}${n?' — '+esc(n):''}</option>`).join('')}</select></div>`;
}
// 各欄の説明(ラベルのマウスオーバー全文 / 欄の下に一行の要約)
const FIELD_HELP={
  ctx:['一度に扱える文章の長さ(トークン数)。','長いほど長文を扱えますが、VRAM を多く使います。足りないと起動に失敗します。'],
  reasoning:['考える(thinking)モデルの思考量。','auto=モデルのテンプレート任せ / off=思考しない / -1=無制限 / 数値=思考に使うトークン数の上限。'],
  temp:['出力のランダムさ。','低い=安定して決まった答え、高い=多様で創作向き。0 だと毎回ほぼ同じ答えになります。'],
  top_p:['確率の高い単語から順に、合計が p に達するまでの候補だけから選ぶ(核サンプリング)。','小さいほど無難で単調、1.0 で無効。temperature と併用します。'],
  top_k:['確率の高い上位 k 個の単語だけから選ぶ。','小さいほど無難で単調、大きいほど多様。0 で無効。'],
  min_p:['最有力候補の確率の p 倍に満たない単語を除外する。','0 で無効。0.05 前後がよく使われ、低確率の変な単語を減らせます。'],
  ngl:['GPU に載せるモデルの層の数(-ngl)。','999=全層を GPU / 0=CPU のみ / auto=--fit 併用時。VRAM が足りないときは減らします。'],
  server_dir:['別ビルドの llama.cpp を使うときのフォルダ。','空欄なら標準の llama.cpp。'],
  extra:['上のチェックにないフラグを、空白区切りで書きます。','例: -a 名前 -b 256 -ub 128 --presence-penalty 1.5'],
};
const flagCat=()=>state.status.services[LL()].flag_catalog||[];
function liftFlags(p){  // 保存済みの flags と、追加フラグ欄に書かれていたカタログ既知のフラグをまとめて「チェック」に持ち上げる
  const known={};for(const f of flagCat())for(const a of [f.flag,...(f.aliases||[])])known[a]=f.flag;
  const fl=new Set(p.flags||[]), rest=[];
  for(const t of String(p.extra||'').split(/\s+/).filter(Boolean)){if(known[t])fl.add(known[t]);else rest.push(t)}
  return {flags:[...fl].sort(),rest:rest.join(' ')};
}
function flagsHtml(sel){
  const groups={};for(const f of flagCat())(groups[f.group||'その他']=groups[f.group||'その他']||[]).push(f);
  return `<div style="margin:12px 0 8px"><div class="sub" style="font-weight:600">オプション(チェックで追加)</div>`+Object.entries(groups).map(([g,fs])=>`<div class="sub" style="margin:6px 0 2px">${esc(g)}</div>`+
    fs.map(f=>`<label title="${esc(f.note||'')}" style="display:flex;gap:6px;align-items:flex-start;padding:2px 0;cursor:pointer;color:var(--fg);font-size:13px"><input type="checkbox" class="pf-flag" style="width:auto;margin-top:4px" value="${esc(f.flag)}" ${sel.includes(f.flag)?'checked':''}><span><code>${esc(f.flag)}</code> <span class="sub">(${esc(f.short||String(f.note||'').split(/[。.]/)[0])})</span></span></label>`).join('')).join('')+`</div>`;
}
function panelParams(){
  const o={service:LL(),model:state.sel};
  const fl=[...PANEL.querySelectorAll('.pf-flag:checked')].map(c=>c.value);if(fl.length)o.flags=fl;
  PANEL.querySelectorAll('[name]').forEach(el=>{
    let v=el.value.trim();if(v==='')return;
    if(['ctx','top_k'].includes(el.name))v=parseInt(v);
    else if(['temp','top_p','min_p'].includes(el.name))v=parseFloat(v);
    o[el.name]=v;
  });
  return o;
}
export function drawPanel(curId){
  if(!state.sel){PANEL.innerHTML='<div class="sub" style="padding:30px 8px;text-align:center">モデルを選択すると、<br>ここにパラメータが表示されます</div>';return}
  const list=presetsOf(state.sel), cur=list.find(p=>p.id===curId)||null;
  const v=cur||{ctx:8192,reasoning:'auto',ngl:'999'};
  const mi=state.models.find(m=>m.path===state.sel);
  const RS=['auto','off','-1','100','1000'];
  let h=`<h3 style="margin:0 0 2px;word-break:break-all;font-size:15px">${esc(base(state.sel))}</h3><div class="sub" style="margin-bottom:10px">${mi?gb(mi.size):''}</div>
    <div class="row" style="margin-bottom:6px"><select id="pf-sel" style="flex:1;min-width:0"><option value="">― 新規(標準値) ―</option>
      ${list.map(p=>`<option value="${p.id}" ${cur&&cur.id===p.id?'selected':''}>${p.favorite?'★ ':''}${esc(p.name)}</option>`).join('')}</select>
      <button class="b" id="pf-save">お気に入り保存</button></div>
    <div class="row" style="margin-bottom:10px">${cur?`<button class="b" id="pf-star">${cur.favorite?'★ 既定':'☆ 既定にする'}</button><button class="b d" id="pf-del">この設定を削除</button>`:''}</div>`;
  const lf=liftFlags(v);
  for(const [k,l] of FORM){
    const x=k==='extra'?lf.rest:(v[k]??'');
    let inp;
    if(k==='extra') h+=flagsHtml(lf.flags);
    if(FIELD_OPTS[k]) inp=comboHtml(k,x);
    else if(k==='extra') inp=`<textarea name="${k}" rows="3" placeholder="上にない追加フラグ(例: -a myname -b 256)">${esc(x)}</textarea>`;
    else inp=`<input name="${k}" value="${esc(x)}">`;
    const hp=FIELD_HELP[k];
    h+=`<div class="f" style="align-items:start"><label ${hp?`title="${esc(hp[0]+' '+hp[1])}" style="cursor:help;text-decoration:underline dotted;padding-top:7px"`:''}>${l}</label><div style="min-width:0">${inp}${k==='server_dir'?'<div class="sub" id="pf-sdhint" style="margin-top:3px;word-break:break-all;font-size:11px"></div>':''}</div></div>`;
  }
  h+=`<div class="sub">変数: {home} {models_dir} / reasoning: auto=テンプレ任せ・off・-1=無制限・数値=budget</div>
    <div class="row" style="margin-top:12px"><button class="b p" id="pf-start" style="flex:1" ${state.status.ops.busy?'disabled':''}>起動</button><button class="b" id="pf-cancel" style="flex:1">キャンセル</button></div>`;
  PANEL.innerHTML=h;
  const sdi=PANEL.querySelector('input[name=server_dir]'); if(sdi) pathHint(sdi,PANEL.querySelector('#pf-sdhint'),LL(),false);
  const $p=s=>PANEL.querySelector(s);
  PANEL.querySelectorAll('select.combo').forEach(sel=>sel.onchange=()=>{
    if(sel.value==='')return;
    PANEL.querySelector(`input[name="${sel.dataset.for}"]`).value=sel.value;sel.value='';
  });
  $p('#pf-sel').onchange=e=>drawPanel(e.target.value||null);
  $p('#pf-save').onclick=async()=>{
    const name=prompt('お気に入りの名前',cur?cur.name:'標準');if(!name)return;
    const same=list.find(p=>p.name===name);
    if(same&&same!==cur&&!confirm(`「${name}」は既にあります。上書きしますか？`))return;
    const o={...panelParams(),name};
    if(same){o.id=same.id;if(same.favorite)o.favorite=true}else if(!list.length)o.favorite=true;
    try{const r=await api('/api/preset',o);await hooks.refresh();drawPanel(r.id)}catch(e){alert(e.message)}
  };
  if(cur){
    $p('#pf-star').onclick=async()=>{try{await api('/api/preset',{...cur,favorite:!cur.favorite});await hooks.refresh();drawPanel(cur.id)}catch(e){alert(e.message)}};
    $p('#pf-del').onclick=async()=>{if(!confirm(`「${cur.name}」を削除しますか？(モデルファイルは消えません)`))return;
      try{await api('/api/preset/delete',{id:cur.id});await hooks.refresh();drawPanel(null)}catch(e){alert(e.message)}};
  }
  $p('#pf-cancel').onclick=()=>{state.sel=null;drawPanel(null);hooks.renderDash()};
  $p('#pf-start').onclick=()=>{
    const o=panelParams();
    const cl=cur?liftFlags(cur):null;
    const same=cur&&FORM.every(([k])=>k==='extra'||String(cur[k]??'')===String(o[k]??''))&&JSON.stringify(cl.flags)===JSON.stringify([...(o.flags||[])].sort())&&cl.rest===String(o.extra||'');
    act('/api/start',same?{preset:cur.id}:{preset:cur?cur.id:null,params:o,label:cur?cur.name+'(一時変更)':'一時設定'});
  };
}
