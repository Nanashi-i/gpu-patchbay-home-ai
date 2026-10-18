/* モデルタブ: サービスごとのモデル一覧・モデルセットの編集・削除コマンド */
import {state, SV, hooks} from './state.js';
import {$, act, api, esc, gb} from './core.js';
import {renderDash} from './dashboard.js';
import {selectModel} from './llama-panel.js';
import {closeModal, modal} from './dialogs.js';
export async function loadModels(){  // ダッシュボード用: llama のモデル一覧
  try{state.models=(await api('/api/models?service=llama')).items}catch(e){return}
  $('#modellist').innerHTML=state.models.map(m=>`<option value="${esc(m.path)}">`).join('');
  state.renderKey='';renderDash();
}
let MT=null, MTDATA=null, MTITEMS=[];
export async function loadModelsTab(){
  if(!state.status) return;
  if(!MT||!state.status.services[MT]||!state.status.services[MT].enabled) MT=(SV()[0]||[])[0];
  try{MTDATA=await api('/api/models?service='+MT)}catch(e){return alert(e.message)}
  drawModelsTab();
}
function drawModelsTab(){
  const r=MTDATA, el=$('#tab-models'); MTITEMS=[];
  const reg=it=>{MTITEMS.push(it);return MTITEMS.length-1};
  const rmBtn=it=>`<button class="b" data-a="rm" data-i="${reg(it)}">削除コマンド</button>`;
  let h=`<div class="row" style="margin-bottom:10px">${SV().map(([k,s])=>`<button class="b ${k===MT?'p':''}" data-a="svc" data-s="${k}">${esc(s.label)}</button>`).join('')}
    <span class="sp"></span><button class="b" data-a="rescan">再スキャン</button></div>
    <div class="sub" style="margin-bottom:8px">保存先: ${esc(r.dir)}</div>`;
  if(r.kind==='llama'){
    h+=`<div class="svc"><table><tr><th>モデル</th><th>サイズ</th><th>使用中のプリセット</th><th></th></tr>`+r.items.map(m=>
      `<tr><td style="word-break:break-all">${esc(m.path)}${m.shards>1?` <span class="tag">${m.shards}分割</span>`:''}${m.mmproj.length?' <span class="tag">mmproj</span>':''}</td><td>${gb(m.size)}</td>
      <td>${m.used_by.length?m.used_by.map(esc).join('<br>'):'<span class="tag new">未登録</span>'}</td>
      <td><div class="row"><button class="b" data-a="mk" data-p="${esc(m.path)}">${m.used_by.length?'設定を追加':'設定を作成'}</button>${rmBtn(m)}</div></td></tr>`).join('')
      +`</table></div><div class="sub">${r.items.length} 件 · 合計 ${gb(r.items.reduce((a,m)=>a+m.size,0))}</div>`;
  }else if(r.kind==='categories'){
    if(state.status.services[MT].view) h+=setsSection();
    for(const c of r.categories){
      h+=`<details class="svc" ${c.count?'open':''}><summary style="padding:10px 14px;cursor:pointer"><b>${esc(c.label)}</b> <span class="sub">${esc(c.key)} · ${c.count} 件${c.size?' · '+gb(c.size):''}${c.hint?' · '+esc(c.hint):''}</span></summary>`;
      h+=c.count?`<table>`+c.items.map(m=>`<tr><td style="word-break:break-all">${esc(m.path)}
        ${m.link?`<span class="tag" title="${esc(m.link)}">${m.broken?'⚠ リンク切れ':'共有リンク'}</span>`:''}${m.linked_by.length?` <span class="tag" title="${esc(m.linked_by.join('\n'))}">${m.linked_by.length} 箇所に共有</span>`:''}${(m.sets||[]).map(n=>` <span class="tag new">${esc(n)}</span>`).join('')}</td>
        <td>${gb(m.size)}</td><td>${rmBtn(m)}</td></tr>`).join('')+`</table>`:'<div class="sub" style="padding:0 14px 10px">なし</div>';
      h+='</details>';
    }
  }else{
    h+=`<div class="svc"><table><tr><th>項目</th><th>サイズ</th><th>参照している設定</th><th></th></tr>`+(r.items.length?r.items.map(m=>
      `<tr><td style="word-break:break-all">${m.is_dir?'📁 ':''}${esc(m.name)}</td><td>${gb(m.size)}</td>
      <td>${m.used_by.length?m.used_by.map(esc).join('<br>'):'<span class="tag">参照なし</span>'}</td><td>${rmBtn(m)}</td></tr>`).join(''):'<tr><td colspan="4" class="sub">なし</td></tr>')+`</table></div>`;
  }
  el.innerHTML=h;
}
$('#tab-models').onclick=e=>{
  const b=e.target.closest('button[data-a]'); if(!b) return;
  const {a,s,i,p}=b.dataset;
  if(a==='svc'){MT=s;loadModelsTab()}
  else if(a==='rescan') loadModelsTab();
  else if(a==='mk'){document.querySelector('nav button[data-tab=dash]').click();selectModel(p)}
  else if(a==='rm') rmDialog(MTITEMS[i]);
  else if(a==='setnew') setEditor(null);
  else if(a==='setedit') setEditor(b.dataset.id);
  else if(a==='setdel'){const st=state.status.sets.sets.find(x=>x.id===b.dataset.id);if(confirm(`セット「${st.name}」を削除しますか？(モデルファイルは消えません)`))act('/api/set/delete',{id:st.id}).then(loadModelsTab)}
};
function setsSection(){
  const sets=state.status.sets.sets.filter(x=>x.service===MT), common=state.status.sets.common[MT]||{};
  const cnt=f=>Object.values(f||{}).reduce((a,l)=>a+l.length,0);
  let h=`<div class="svc" style="padding:12px 14px"><div class="row" style="justify-content:space-between;margin-bottom:4px"><b>モデルセット</b><button class="b" data-a="setnew">＋ セットを作成</button></div>
    <div class="sub" style="margin-bottom:10px">ダッシュボードで ${esc(state.status.services[MT].label)} の設定にセットを選んで起動すると、そのセットと「共通」のモデルだけが選択肢に出ます。</div>
    <div class="row">`;
  h+=`<div class="card" style="min-width:200px"><b>共通</b><div class="n">全セットで表示 · ${cnt(common)} 件</div><div class="row"><button class="b" data-a="setedit" data-id="_common">編集</button></div></div>`;
  for(const x of sets) h+=`<div class="card" style="min-width:200px;max-width:300px"><b>${esc(x.name)}</b><div class="n">${cnt(x.files)} 件${x.note?' · '+esc(x.note):''}</div>
    <div class="row"><button class="b" data-a="setedit" data-id="${esc(x.id)}">編集</button><button class="b d" data-a="setdel" data-id="${esc(x.id)}">削除</button></div></div>`;
  return h+'</div></div>';
}
function setEditor(id){
  const isCommon=id==='_common';
  const st=isCommon?{name:'共通',note:'',files:state.status.sets.common[MT]||{}}:id?state.status.sets.sets.find(x=>x.id===id):{name:'',note:'',files:{}};
  let h=`<h3>${isCommon?'共通セットの編集':id?'セットの編集':'セットの作成'}</h3>`;
  if(!isCommon) h+=`<div class="f"><label>名前</label><input id="se-name" value="${esc(st.name)}" placeholder="例: Qwen-Image 2.1"></div><div class="f"><label>メモ</label><input id="se-note" value="${esc(st.note)}" placeholder="例: これで動作確認済み"></div>`;
  h+=`<div class="sub" style="margin-bottom:6px">このセットで見せるモデルにチェックを入れてください。</div><div style="max-height:50vh;overflow:auto">`;
  for(const c of MTDATA.categories){
    const have=new Set(c.items.map(i=>i.path)), picked=st.files[c.key]||[];
    const paths=[...c.items.map(i=>i.path),...picked.filter(p=>!have.has(p))];
    if(!paths.length) continue;
    h+=`<details ${picked.length?'open':''} style="margin-bottom:6px"><summary style="cursor:pointer"><b>${esc(c.label)}</b> <span class="sub">${picked.length}/${paths.length}</span></summary>`+
      paths.map(pth=>`<label style="display:flex;gap:8px;padding:2px 0;word-break:break-all"><input type="checkbox" style="width:auto" data-cat="${esc(c.key)}" value="${esc(pth)}" ${picked.includes(pth)?'checked':''}>${esc(pth)}${have.has(pth)?'':' <span class="tag">見つかりません</span>'}</label>`).join('')+`</details>`;
  }
  h+=`</div><div class="row" style="margin-top:12px"><button class="b p" id="se-save">保存</button><span class="sp"></span><button class="b" id="mclose">キャンセル</button></div>`;
  $('#box').innerHTML=h;modal.classList.add('on');$('#mclose').onclick=closeModal;
  $('#se-save').onclick=async()=>{
    const files={};
    $('#box').querySelectorAll('input[type=checkbox]:checked').forEach(c=>{(files[c.dataset.cat]=files[c.dataset.cat]||[]).push(c.value)});
    try{
      if(isCommon) await api('/api/set/common',{service:MT,files});
      else{const name=$('#se-name').value.trim();if(!name)return alert('名前を入力してください');
        await api('/api/set',{id:id||undefined,name,note:$('#se-note').value.trim(),service:MT,files})}
      closeModal();await hooks.refresh();loadModelsTab();
    }catch(e){alert(e.message)}
  };
}
function rmDialog(m){
  const warns=[];
  if(m.used_by&&m.used_by.length) warns.push(`「${m.used_by.map(esc).join('」「')}」が使用/参照しています。先に設定を見直してください。`);
  if(m.linked_by&&m.linked_by.length) warns.push(`他サービスのリンクが指しています(${m.linked_by.map(esc).join(', ')})。実体だけ消すとリンク切れになります。「${esc(m.rm_all_label)}」のコマンドを使ってください。`);
  if(m.broken) warns.push('リンク切れです。リンクを消すだけで構いません。');
  $('#box').innerHTML=`<h3>削除コマンド</h3>${warns.map(w=>`<p style="color:var(--warn)">⚠ ${w}</p>`).join('')}
    <p class="sub">ターミナルに貼り付けて実行してください(この画面からは削除しません)</p>
    <textarea id="rmc" rows="3" readonly>${esc(m.rm)}</textarea>
    ${m.rm_all?`<p class="sub">${esc(m.rm_all_label)}:</p><textarea id="rmc2" rows="3" readonly>${esc(m.rm_all)}</textarea>`:''}
    <div class="row" style="margin-top:12px"><button class="b p" id="cp1">コピー</button>${m.rm_all?`<button class="b" id="cp2">${esc(m.rm_all_label)}でコピー</button>`:''}<span class="sp"></span><button class="b" id="mclose">閉じる</button></div>`;
  modal.classList.add('on');$('#mclose').onclick=closeModal;
  const cp=(id,btn)=>{const t=$(id);t.select();(navigator.clipboard?navigator.clipboard.writeText(t.value):Promise.reject()).catch(()=>document.execCommand('copy')).finally(()=>{$(btn).textContent='コピーしました'})};
  $('#cp1').onclick=()=>cp('#rmc','#cp1'); if(m.rm_all) $('#cp2').onclick=()=>cp('#rmc2','#cp2');
}
