/* 画面の共有の状態と、状態の読み取り。ほかのファイルは、これを import して使う(依存の一番下)。
   state の中身を書き換えてよいのは、持ち主のファイルだけ:
     status    main.js    /api/state の最新の結果(サービス・プリセット・操作の進捗・ダウンロード)
     models    models.js  llama.cpp のモデル一覧(ダッシュボード用)
     tab       main.js    いま開いているタブ
     renderKey main.js    サービスタブの描き直しが要るかの判定用
     sel       llama-panel.js  選んでいる llama.cpp のモデル
     monMeta   monitor.js モニターの情報(間隔・GPU の名前など) */
export const state={status:null, models:[], tab:'dash', renderKey:'', sel:null, monMeta:null};

// ファイル同士が循環して import しないための、接続口。main.js が、起動時に中身を入れる
export const hooks={refresh:async()=>{}, renderDash:()=>{}};

export const base=s=>String(s||'').split('/').pop();
export const LL=()=>Object.keys(state.status.services).find(k=>state.status.services[k].type==='llama');
export const SV=()=>Object.entries(state.status.services).filter(([k,s])=>s.enabled);   // 「使う」にしているサービス
export const presetsOf=m=>state.status.presets.filter(p=>p.service===LL()&&p.model===m);
