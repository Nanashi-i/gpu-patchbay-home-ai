/* ダウンロードタブ: URL の確認・ファイルの選択(種別ごとにまとめて表示)・トークン・進捗 */
import {state, SV, hooks} from './state.js';
import {$, act, api, esc, gb, mb} from './core.js';
import {closeModal, modal} from './dialogs.js';
let DLS=null, INSPECT=null;
$('#tab-dl').innerHTML=`<div class="svc" style="padding:14px">
  <div class="row" style="justify-content:space-between;margin-bottom:6px"><span class="sub">保存先サービス</span><button class="b" id="dl-tok"></button></div><div class="row" id="dl-svc"></div>
  <div class="sub" id="dl-dest" style="margin:8px 0"></div>
  <div class="row"><input id="dl-url" placeholder="Hugging Face のURL(リポジトリ / ファイル) または 直リンク" style="flex:1;min-width:240px"><button class="b p" id="dl-inspect">確認</button></div>
  <div id="dl-pick" class="hide" style="margin-top:12px"></div></div>
  <div class="row" style="justify-content:space-between;margin:0 0 6px"><b>ダウンロード状況</b><button class="b" id="dl-clear">完了分を消す</button></div><div id="dl-list"></div>`;
const TSRC={app:'登録済み',config:'登録済み(machine.json)'};
function tokLabel(){const t=state.status.tokens||{};$('#dl-tok').textContent='🔑 トークン'+(t.hf?' (HF登録済み)':' (HF未登録)')}
function tokenDialog(){
  const t=state.status.tokens||{};
  const row=(k,l,desc)=>`<div style="margin-bottom:16px"><div class="row" style="justify-content:space-between"><b>${l}</b><span class="tag ${t[k]?'':'new'}">${t[k]?TSRC[t[k]]:'未登録'}</span></div>
    <div class="sub" style="margin:2px 0 6px">${desc}</div>
    <div class="row"><input id="tk-${k}" type="password" placeholder="${t[k]?'新しいトークンで上書き':'トークンを貼り付け'}" style="flex:1;min-width:200px" autocomplete="off"><button class="b p" data-k="${k}" data-a="save">保存</button>${t[k]==='app'?`<button class="b d" data-k="${k}" data-a="clear">削除</button>`:''}</div></div>`;
  $('#box').innerHTML=`<h3>🔑 ダウンロード用トークン</h3>
    ${row('hf','Hugging Face','gated(利用規約への同意が必要)や非公開のモデル、速度/回数制限の緩和に使います。公開モデルだけなら不要です。発行: huggingface.co/settings/tokens(Read権限でOK)')}
    ${row('civitai','Civitai','Civitai の直リンクのダウンロードに使います。発行: civitai.com/user/account → API Keys')}
    <div class="sub">保存先は ${esc('~/.local/state/gpu-patchbay-home-ai/secrets.json')}(本人のみ読み取り可)です。画面には表示しません。</div>
    <div class="row" style="margin-top:12px"><span class="sp"></span><button class="b" id="mclose">閉じる</button></div>`;
  modal.classList.add('on');$('#mclose').onclick=closeModal;
  $('#box').onclick=async e=>{
    const b=e.target.closest('button[data-k]');if(!b)return;const k=b.dataset.k;
    try{
      if(b.dataset.a==='clear'){if(!confirm('登録を削除しますか？'))return;await api('/api/token',{kind:k,clear:true})}
      else{const v=$('#tk-'+k).value.trim();if(!v)return alert('トークンを入力してください');const r=await api('/api/token',{kind:k,token:v});if(r.user)alert('確認できました: '+r.user)}
      await hooks.refresh();tokenDialog();
    }catch(err){alert(err.message)}
  };
}
$('#dl-tok').onclick=tokenDialog;
function drawDlSvc(){
  tokLabel();
  if(!DLS||!state.status.services[DLS]||!state.status.services[DLS].enabled) DLS=(SV()[0]||[])[0];
  $('#dl-svc').innerHTML=SV().map(([k,s])=>`<button class="b ${k===DLS?'p':''}" data-s="${k}">${esc(s.label)}</button>`).join('');
  const s=state.status.services[DLS];
  $('#dl-dest').textContent=`保存先: ${s.models_dir}`+(s.categories.length?' / 種別フォルダ(ファイルごとに選べます)':'');
}
$('#dl-svc').onclick=e=>{const b=e.target.closest('button[data-s]');if(!b)return;DLS=b.dataset.s;INSPECT=null;$('#dl-pick').classList.add('hide');drawDlSvc()};
$('#dl-inspect').onclick=async()=>{
  const b=$('#dl-inspect');b.disabled=true;b.textContent='確認中…';
  try{INSPECT=await api('/api/dl/inspect',{url:$('#dl-url').value.trim(),service:DLS});drawPick()}catch(e){alert(e.message)}
  b.disabled=false;b.textContent='確認';
};
const shardKey=p=>{const m=p.match(/^(.*)-\d{5}-of-(\d{5})\.gguf$/);return m?m[1]+'|'+m[2]:null};
function renderRows(){
  const d=INSPECT, cats=d.categories, hasCat=cats.length>0, q=(d.filter||'').toLowerCase();
  const idx=d.files.map((_,i)=>i).filter(i=>!q||d.files[i].path.toLowerCase().includes(q));
  const row=i=>{const f=d.files[i];return `<tr><td style="width:28px"><input type="checkbox" data-i="${i}" style="width:auto" ${d.sel.has(i)?'checked':''}></td>
    <td style="word-break:break-all">${esc(f.path||'(ファイル名を入力)')}</td><td style="white-space:nowrap">${gb(f.size)}</td>
    ${hasCat?`<td><select data-cat="${i}" style="min-width:150px">${cats.map(c=>`<option value="${esc(c.key)}" ${c.key===f.category?'selected':''}>${esc(c.label)}</option>`).join('')}</select></td>`:''}</tr>`};
  let h='';
  if(hasCat){
    for(const c of cats){
      const g=idx.filter(i=>d.files[i].category===c.key).sort((a,b)=>d.files[a].path.localeCompare(d.files[b].path));
      if(!g.length) continue;
      h+=`<tr class="grp"><td colspan="4"><b>${esc(c.label)}</b> <span class="sub">${g.length} 件${g.filter(i=>d.sel.has(i)).length?' · '+g.filter(i=>d.sel.has(i)).length+' 件選択':''} · 保存先: ${esc(c.key)}/</span></td></tr>`+g.map(row).join('');
    }
  }else h=idx.map(row).join('');
  $('#dl-rows').innerHTML=h||'<tr><td class="sub">該当なし</td></tr>';
}
function drawPick(){
  const d=INSPECT, el=$('#dl-pick'), cats=d.categories, hasCat=cats.length>0;
  el.classList.remove('hide');
  const others=SV().filter(([k,s])=>k!==DLS&&s.categories.length).map(([,s])=>s.label);
  d.sel=new Set(d.files.map((f,i)=>d.preselect.includes(f.path)?i:-1).filter(i=>i>=0)); d.filter='';
  let h='';
  if(!hasCat&&!d.direct) h+=`<div class="f"><label>保存先フォルダ</label><input id="dl-folder" value="${esc(d.folder)}"></div>`;
  if(d.direct&&d.need_name) h+=`<div class="f"><label>ファイル名</label><input id="dl-name" placeholder="拡張子を含む(例: model.safetensors)"></div><div class="sub">許可: ${d.allowed.join(' ')}</div>`;
  if(d.files.length>8) h+=`<div class="f"><label>絞り込み</label><input id="dl-filter" placeholder="ファイル名の一部"></div>`;
  h+=`<table id="dl-tbl"><tbody id="dl-rows"></tbody></table>`;
  if(hasCat&&others.length) h+=`<label style="display:flex;gap:8px;align-items:center;margin-top:10px"><input type="checkbox" id="dl-link" style="width:auto" checked>${esc(others.join(' / '))} でも使えるようにする(対応する種別があればリンクを作成)</label>`;
  if(state.status.services[DLS].view){
    const sets=state.status.sets.sets.filter(x=>x.service===DLS);
    h+=`<div class="f" style="margin-top:10px"><label>モデルセットに追加</label><div class="row"><select id="dl-set" style="flex:1;min-width:140px"><option value="">追加しない</option><option value="_common">共通</option>
      ${sets.map(x=>`<option value="${esc(x.id)}">${esc(x.name)}</option>`).join('')}<option value="__new">＋ 新しいセット…</option></select>
      <input id="dl-newset" class="hide" placeholder="新しいセット名" style="flex:1;min-width:140px"></div></div>`;
  }
  h+=`<div class="row" style="margin-top:10px"><button class="b p" id="dl-go">ダウンロード開始</button></div>`;
  el.innerHTML=h;
  if($('#dl-set')) $('#dl-set').onchange=e=>$('#dl-newset').classList.toggle('hide',e.target.value!=='__new');
  renderRows();
  el.onchange=e=>{
    const c=e.target;
    if(c.type==='checkbox'&&c.dataset.i!=null){
      const i=+c.dataset.i, k=shardKey(d.files[i].path);
      d.files.forEach((f,j)=>{if(j===i||(k&&shardKey(f.path)===k)){c.checked?d.sel.add(j):d.sel.delete(j)}});
      renderRows();
    }else if(c.dataset.cat!=null){d.files[+c.dataset.cat].category=c.value;renderRows()}  // 種別を変えたら、その種別のグループへ移動
  };
  const fl=$('#dl-filter');
  if(fl) fl.oninput=()=>{d.filter=fl.value;renderRows()};
  $('#dl-go').onclick=async()=>{
    const files=[...d.sel].sort((x,y)=>x-y).map(i=>{
      const f=d.files[i];
      return {path:d.direct&&d.need_name?($('#dl-name').value.trim()):f.path,category:hasCat?f.category:null};
    });
    const body={service:DLS,files,folder:$('#dl-folder')?$('#dl-folder').value:'',link:!!($('#dl-link')&&$('#dl-link').checked)};
    if($('#dl-set')){const v=$('#dl-set').value;if(v==='__new')body.new_set=$('#dl-newset').value.trim();else if(v)body.set_id=v}
    if(d.direct) body.url=d.url; else {body.repo=d.repo;body.rev=d.rev}
    try{await api('/api/dl/start',body);el.classList.add('hide');$('#dl-url').value='';hooks.refresh()}catch(e){alert(e.message)}
  };
}
export function renderDl(){
  if(state.status&&!$('#dl-svc').firstChild) drawDlSvc();
  const l=state.status.downloads;
  $('#dl-list').innerHTML=l.length?l.map(j=>{
    const pct=j.total?Math.min(100,j.done/j.total*100):0;
    const stl={queued:'待機中',downloading:'ダウンロード中',done:'✅ 完了',error:'⚠ '+esc(j.error),cancelled:'中止'}[j.state];
    const where=(state.status.services[j.service]?.label||j.service)+(j.category?' / '+j.category:'');
    return `<div class="svc" style="padding:10px 14px"><div class="row" style="justify-content:space-between"><b style="word-break:break-all">${esc(j.name)} <span class="tag">${esc(where)}</span></b>
      ${['queued','downloading'].includes(j.state)?`<button class="b d" data-id="${j.id}">中止</button>`:''}</div>
      <div class="prog"><i style="width:${pct}%"></i></div>
      <div class="sub">${stl} · ${mb(j.done)} / ${j.total?mb(j.total):'?'} (${pct.toFixed(1)}%)${j.speed?` · ${(j.speed/1048576).toFixed(1)} MB/s`:''}${j.speed&&j.total?` · 残り約 ${Math.round((j.total-j.done)/j.speed/60)} 分`:''}</div></div>`}).join('')
    :'<div class="sub">なし</div>';
}
$('#dl-list').onclick=e=>{const b=e.target.closest('button[data-id]');if(b)act('/api/dl/cancel',{id:b.dataset.id})};
$('#dl-clear').onclick=()=>act('/api/dl/clear',{});
