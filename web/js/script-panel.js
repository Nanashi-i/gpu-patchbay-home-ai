/* スクリプト / ランチャー系サービス(Strata・ComfyUI・Forge)を選んだときの、右のパネルと、サービスのクリック処理・設定(⚙)ダイアログ */
import {base, hooks, state} from './state.js';
import {$, act, api, esc} from './core.js';
import {closeModal, keyDialog, modal, pathHint} from './dialogs.js';
export const SELS={}, SP={};
const SFORM=[['name','名前'],['cmd','実行ファイル'],['args','引数(任意)'],['note','メモ']];
export function drawSPanel(name){
  const el=SP[name]||(SP[name]=Object.assign(document.createElement('div'),{className:'panel'}));
  const k=SELS[name], s=state.status.services[name];
  if(!k){el.innerHTML='<div class="sub" style="padding:30px 8px;text-align:center">項目を選択すると、<br>ここに設定が表示されます</div>';return}
  let cur=null,v={};
  if(k.startsWith('p:')){cur=state.status.presets.find(x=>x.id===k.slice(2))||null;v=cur||{}}
  else if(k.startsWith('u:')){const u=k.slice(2);v={cmd:u,name:base(u).replace(/\.sh$/,'')}}
  let h=`<h3 style="margin:0 0 10px;font-size:15px">${esc(cur?cur.name:k==='new'?'新規追加':v.name)} <span class="sub">${esc(s.label)}</span></h3>`;
  for(const [f,l] of SFORM){ if(f==='cmd'&&s.launcher) continue; h+=`<div class="f" style="align-items:start"><label>${l}</label><div style="min-width:0"><input name="${f}" value="${esc(v[f]??'')}">${f==='cmd'?'<div class="sub" id="sp-cmdhint" style="margin-top:3px;word-break:break-all;font-size:11px"></div>':''}</div></div>`; }
  if(s.view){
    const sets=state.status.sets.sets.filter(x=>x.service===name);
    h+=`<div class="f"><label>モデルセット</label><select name="model_set"><option value="">すべて表示</option>${sets.map(x=>`<option value="${esc(x.id)}" ${v.model_set===x.id?'selected':''}>${esc(x.name)}</option>`).join('')}</select></div>
      <div class="sub">選んだセット(＋共通)のモデルだけが、起動する ${esc(s.label)} のドロップダウンに出ます。切り替えは再起動で反映されます。</div>`;
  }
  h+=`<div class="sub">変数: {home} が使えます${k.startsWith('u:')?' · 未登録スクリプトです。起動すると登録されます':''}</div>
    <div class="row" style="margin:12px 0 6px"><button class="b p" id="sp-start" style="flex:1" ${state.status.ops.busy?'disabled':''}>起動</button><button class="b" id="sp-save" style="flex:1">${cur?'保存':'登録'}</button></div>
    <div class="row">${cur?`<button class="b" id="sp-star">${cur.favorite?'★ お気に入り':'☆ お気に入りにする'}</button><button class="b d" id="sp-del">削除</button>`:''}<button class="b" id="sp-cancel" style="margin-left:auto">キャンセル</button></div>`;
  el.innerHTML=h;
  const ci=el.querySelector('input[name=cmd]'); if(ci) pathHint(ci,el.querySelector('#sp-cmdhint'),name,false);
  const q=x=>el.querySelector(x);
  const collect=()=>{const o={service:name};if(cur){o.id=cur.id;if(cur.favorite)o.favorite=true}
    el.querySelectorAll('[name]').forEach(i=>{const t=i.value.trim();if(t)o[i.name]=t});return o};
  const save=async()=>{const o=collect();if(!o.name||(!o.cmd&&!s.launcher)){alert('名前と実行ファイルは必須です');return null}
    const r=await api('/api/preset',o);await hooks.refresh();SELS[name]='p:'+r.id;return r.id};
  q('#sp-save').onclick=async()=>{try{const id=await save();if(id){drawSPanel(name);hooks.renderDash()}}catch(e){alert(e.message)}};
  q('#sp-start').onclick=async()=>{try{
    const go=async()=>{const id=await save();if(id){drawSPanel(name);hooks.renderDash();act('/api/start',{preset:id})}};
    if(s.key==='needed') keyDialog(name,go); else await go();
  }catch(e){alert(e.message)}};
  if(cur){
    q('#sp-star').onclick=async()=>{try{await api('/api/preset',{...cur,favorite:!cur.favorite});await hooks.refresh();drawSPanel(name)}catch(e){alert(e.message)}};
    q('#sp-del').onclick=async()=>{if(!confirm(`「${cur.name}」を削除しますか？`))return;try{await api('/api/preset/delete',{id:cur.id});SELS[name]=null;await hooks.refresh();drawSPanel(name);hooks.renderDash()}catch(e){alert(e.message)}};
  }
  q('#sp-cancel').onclick=()=>{SELS[name]=null;drawSPanel(name);hooks.renderDash()};
}
const homeify=p=>String(p).replace(/^\/home\/[^/]+/,'~');
export function svcDialog(name){
  const s=state.status.services[name], run=s.state!=='stopped';
  const portNote=(s.type==='llama'||s.launcher)?'ハブが起動するときに、このポートを指定します。':'ハブは状態の確認にだけ使います。起動スクリプトが使うポートと一致させてください。';
  $('#box').innerHTML=`<h3>⚙ ${esc(s.label)} の設定</h3>
    ${run?'<p style="color:var(--warn)">起動中は変更できません。先に停止してください。</p>':''}
    <div class="f" style="align-items:start"><label>インストール場所</label><div style="min-width:0"><input id="sc-dir" value="${esc(s.dir)}"><div class="sub" id="sc-dirhint" style="margin-top:3px;word-break:break-all"></div></div></div>
    ${(!s.installed&&(s.candidates||[]).length)?`<div class="sub" style="margin:-2px 0 10px">見つかりました: ${s.candidates.map(c=>`<button class="b" data-c="${esc(homeify(c))}">${esc(homeify(c))}</button>`).join(' ')}</div>`:''}
    <div class="f" style="align-items:start"><label>ポート</label><div><input id="sc-port" value="${s.port||''}" style="width:120px"><div class="sub" style="margin-top:3px">${portNote}</div></div></div>
    <div class="f"><label>モデル置き場</label><input id="sc-models" value="${esc(s.models_dir_raw||'')}"></div>
    <label style="display:flex;gap:8px;align-items:center;margin:8px 0"><input type="checkbox" id="sc-en" style="width:auto" ${s.enabled?'checked':''}>このサービスを使う(外すと、ダッシュボードから隠します)</label>
    <div class="sub">変数: {home} {root} {apps_root} {models_root} が使えます。保存すると machine.json に書き込みます(1つ前の版は machine.json.bak)。</div>
    <div class="row" style="margin-top:14px"><button class="b p" id="sc-save" ${run?'disabled':''}>保存</button><span class="sp"></span><button class="b" id="mclose">キャンセル</button></div>`;
  modal.classList.add('on');$('#mclose').onclick=closeModal;
  pathHint($('#sc-dir'),$('#sc-dirhint'),name,true);
  $('#box').querySelectorAll('button[data-c]').forEach(b=>b.onclick=()=>{const i=$('#sc-dir');i.value=b.dataset.c;i.dispatchEvent(new Event('input'))});
  $('#sc-save').onclick=async()=>{
    const portText=$('#sc-port').value.trim(), body={service:name,dir:$('#sc-dir').value,models_dir:$('#sc-models').value,enabled:$('#sc-en').checked};
    if(portText){   // API は整数だけを受け付ける(文字列のまま送らない)
      const port=Number(portText);
      if(!Number.isInteger(port)||port<1||port>65535) return alert('ポートは 1〜65535 の数字で指定してください');
      body.port=port;
    }
    try{await api('/api/service/config',body);closeModal();await hooks.refresh()}
    catch(e){alert(e.message)}
  };
}
