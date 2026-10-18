/* 起動: 画面全体の更新(2秒ごとの状態の取得)・タブの切り替え。各ファイルをつなぐ(import の一番上) */
import {state, hooks} from './state.js';
import {$, api} from './core.js';
import {renderDash} from './dashboard.js';
import {PANEL} from './llama-panel.js';
import {renderDl} from './downloads.js';
import {loadModels, loadModelsTab} from './models.js';
import {monStart, monStop, monStatus} from './monitor.js';
import './theme.js';

hooks.refresh=refresh;
hooks.renderDash=renderDash;

document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{
  state.tab=b.dataset.tab;
  document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('on',x===b));
  for(const t of ['dash','mon','models','dl']) $('#tab-'+t).classList.toggle('hide',t!==state.tab);
  if(state.tab==='models') loadModelsTab();
  if(state.tab==='mon') monStart(); else monStop();
});


function render(){
  if(!state.status) return;
  const o=$('#ops');
  if(state.status.ops.busy){o.className='busy';o.textContent='⏳ '+state.status.ops.msg}
  else if(state.status.ops.error){o.className='err';o.textContent='⚠ '+state.status.ops.error}
  else{o.className='';o.textContent=''}
  const key=JSON.stringify([state.status.services,state.status.presets,state.models.length]);
  if(key!==state.renderKey){state.renderKey=key;renderDash()}
  const sb=PANEL.querySelector('#pf-start'); if(sb) sb.disabled=state.status.ops.busy;
  if(state.tab==='mon') monStatus();
  renderDl();
}

let prevDone=0;
async function refresh(){
  try{
    state.status=await api('/api/state');render();
    const done=state.status.downloads.filter(j=>j.state==='done').length;
    if(done!==prevDone){prevDone=done;loadModels();if(state.tab==='models')loadModelsTab()}
  }catch(e){$('#ops').className='err';$('#ops').textContent='⚠ '+e.message}
}
refresh().then(loadModels);setInterval(refresh,2000);
