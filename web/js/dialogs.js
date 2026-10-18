/* 共通のダイアログ: モーダルの開閉・ログの表示・API キーの登録 */
import {state, hooks} from './state.js';
import {$, api, esc} from './core.js';
export const modal=$('#modal');
modal.onclick=e=>{if(e.target===modal) closeModal()};
export const closeModal=()=>{modal.classList.remove('on');clearInterval(logTimer);$('#box').onclick=null};
let logTimer;
export async function showLog(name){
  $('#box').innerHTML=`<h3>${esc(state.status.services[name].label)} ログ</h3><pre id="logpre"></pre><div class="row" style="margin-top:10px"><button class="b" id="mclose">閉じる</button></div>`;
  $('#mclose').onclick=closeModal;modal.classList.add('on');
  const load=async()=>{try{const r=await api('/api/log?service='+name);const pre=$('#logpre');if(!pre)return;const bot=pre.scrollTop+pre.clientHeight>=pre.scrollHeight-20;pre.textContent=r.log||'(ログなし)';if(bot)pre.scrollTop=pre.scrollHeight}catch{}};
  await load();$('#logpre').scrollTop=1e9;logTimer=setInterval(load,2000);
}

export function keyDialog(name,then){
  const s=state.status.services[name], isSet=s.key==='set';
  const cmd=`python3 -c "import json;print(json.load(open('${s.secrets_file}'))['${name}'])"`;
  $('#box').innerHTML=`<h3>🔑 ${esc(s.label)} のAPIキー</h3>
    <p class="sub">${isSet?'登録済みです。起動時に環境変数として渡されます(キー自体は画面に表示しません)。':'初回のみ登録が必要です。登録したキーは起動時に自動で渡されます。'}<br>
    このキーを要求する側(クライアント)にも同じキーの設定が必要です。</p>
    <div class="row" style="margin-bottom:10px">
      ${s.key_import?'<button class="b p" id="k-imp">既存のキーファイルから取り込む</button>':''}
      <button class="b ${s.key_import?'':'p'}" id="k-gen">新規生成</button></div>
    <div class="f"><label>手入力</label><input id="k-in" placeholder="既存のAPIキーを貼り付け"></div>
    <div class="row"><button class="b" id="k-save">この値で登録</button>${isSet?'<button class="b d" id="k-clr">登録を削除</button>':''}<span class="sp"></span><button class="b" id="mclose">閉じる</button></div>
    ${isSet?`<p class="sub" style="margin-top:12px">登録済みのキーを確認するコマンド:</p><textarea rows="2" readonly>${esc(cmd)}</textarea>`:''}
    <div id="k-res"></div>`;
  modal.classList.add('on');$('#mclose').onclick=closeModal;
  const send=async body=>{
    try{const r=await api('/api/secret',{service:name,...body});await hooks.refresh();
      if(r.key){$('#k-res').innerHTML=`<p style="color:var(--warn)">生成したキー(この画面でしか表示されません。控えてください)</p><textarea rows="2" readonly>${esc(r.key)}</textarea>
        <div class="row" style="margin-top:8px"><button class="b p" id="k-ok">OK</button></div>`;$('#k-ok').onclick=()=>{closeModal();then&&then()}}
      else{closeModal();then&&then()}
    }catch(e){alert(e.message)}
  };
  if(s.key_import) $('#k-imp').onclick=()=>send({import:true});
  $('#k-gen').onclick=()=>send({generate:true});
  $('#k-save').onclick=()=>{const v=$('#k-in').value.trim();if(!v)return alert('キーを入力してください');send({key:v})};
  if(isSet) $('#k-clr').onclick=()=>{if(confirm('登録を削除しますか？'))send({clear:true})};
}

// 入力欄の下に、そのパスが見つかるかどうかを、確認して出す
export function pathHint(input,hint,service,asDir){
  let t;const run=async()=>{
    if(!asDir&&!input.value.trim()){hint.textContent='';return}
    try{const r=await api(`/api/resolve?service=${encodeURIComponent(service)}&path=${encodeURIComponent(input.value)}${asDir?'&dir=1':''}`);
      const ok=asDir?r.installed_here:r.exists;
      hint.innerHTML=`<span style="color:var(--${ok?'ok':'err'})">${ok?'✓':'✗'}</span> ${esc(r.resolved)}${ok?'':(asDir?(r.exists?` (フォルダはありますが、${esc(r.marker)} が見つかりません)`:' (見つかりません)'):' (見つかりません)')}`}
    catch(e){hint.textContent=''}};
  input.addEventListener('input',()=>{clearTimeout(t);t=setTimeout(run,300)});run();
}
