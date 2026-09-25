'use strict';
const token = location.hash.slice(1) || sessionStorage.getItem('watari-dashboard-token') || '';
if(token) sessionStorage.setItem('watari-dashboard-token',token);
history.replaceState(null, '', location.pathname);
const content = document.querySelector('#content');
const notice = document.querySelector('#notice');
let data, view = 'overview', query = '', kind = '', offset = 0, requestId = 0;
const names = { overview:'概要', memory:'記憶', history:'記録と出典', connections:'接続', sync:'同期・パソコン', settings:'設定・機能' };
function el(tag, text, className) { const n = document.createElement(tag); if (text !== undefined) n.textContent = String(text); if (className) n.className = className; return n; }
function add(parent, ...nodes) { parent.append(...nodes); return parent; }
function details(value, label = '詳細を表示') { return add(el('details'), el('summary', label), el('pre', JSON.stringify(value, null, 2))); }
function card(title, value, note) { const n = add(el('article', undefined, 'card'), el('h2', title), el('strong', value, 'count')); if (note) n.append(el('p', note, 'muted')); return n; }
function empty(text='該当する記録はありません。') { content.append(el('p', text, 'empty')); }
function row(title, note, value) { const n=add(el('article', undefined, 'row'), el('h3', title)); if(note) n.append(el('p', note)); if(value) n.append(details(value)); return n; }
async function api(path) { const response=await fetch(path, {headers:{'X-Watari-Token':token},cache:'no-store'}); if(!response.ok) throw new Error(response.status===403?'この画面のアクセス情報がありません。ワタリからダッシュボードを開き直してください。':'読み取りに失敗しました。表示上限（1ファイル32MB）・ファイル形式・権限を確認してください。'); return response.json(); }
function section(title, items) { content.append(el('h2',title,'section-title')); if(!items.length) { empty(); return; } content.append(add(el('div',undefined,'rows'),...items)); }
function memoryItems() {
 const life=data.memory.life || {}, learning=data.memory.learning || {};
 const result=[];
 for(const [topic,v] of Object.entries(life.facts||{})) result.push({topic, ...v, category:'人物・事実'});
 for(const v of life.open_threads||[]) result.push({...v,category:'進行中'});
 for(const [topic,v] of Object.entries(life.interests||{})) result.push({topic,...v,category:'関心'});
 for(const [domain,d] of Object.entries(learning.domains||{})) for(const [topic,v] of Object.entries(d.topics||{})) result.push({topic,...v,domain,category:'学習'});
 return result;
}
async function render() {
 const id=++requestId; content.replaceChildren(); document.querySelector('#title').textContent=names[view];
 document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
 if(!data) return;
 const life=data.memory.life||{}, items=memoryItems();
 if(view==='overview') {
  content.append(add(el('div',undefined,'grid'),card('人物・事実',Object.keys(life.facts||{}).length),card('進行中',(life.open_threads||[]).length),card('学習',items.filter(v=>v.category==='学習').length),card('MCP接続先',data.connections.mcp.servers.length,'登録数です。接続状態は未確認です。')));
  const top=row('あなたの記憶と、このパソコンの設定','接続先や同期先へ通信せず、保存された情報を表示しています。');
  top.append(el('p',data.settings.home,'muted')); content.append(top);
  section('機能',data.capabilities.map(c=>row(c.name,c.detail,{command:c.command})));
 }
 if(view==='memory') {
  const input=el('input'); input.placeholder='記憶を検索'; input.setAttribute('aria-label','記憶を検索');
  const list=el('div',undefined,'rows'); const page=el('div',undefined,'paging'); let pageIndex=0;
  function draw() { const filtered=items.filter(v=>JSON.stringify(v).toLowerCase().includes(input.value.toLowerCase())); list.replaceChildren(...filtered.slice(pageIndex*50,(pageIndex+1)*50).map(v=>{const n=row(v.topic,v.note,v); n.prepend(el('span',v.category,'badge')); return n;})); page.replaceChildren(el('span',`${filtered.length}件 · ${filtered.length ? pageIndex*50+1 : 0}–${Math.min((pageIndex+1)*50,filtered.length)}`)); for(const [label,dir] of [['前へ',-1],['次へ',1]]) { const b=el('button',label); b.disabled=dir<0?pageIndex===0:(pageIndex+1)*50>=filtered.length;b.onclick=()=>{pageIndex+=dir;draw();}; page.append(b); } }
  input.oninput=()=>{pageIndex=0;draw();}; content.append(input,list,page); draw();
 }
 if(view==='history') {
  const form=el('form'), input=el('input'); input.placeholder='題名・本文・出典を検索'; input.setAttribute('aria-label','記録を検索'); input.value=query;
  const select=el('select'); select.setAttribute('aria-label','記録の種類'); for(const [k,label] of [['','すべて'],['fact','事実'],['thread','進行事項'],['interest','関心'],['study','学習']]) {const o=el('option',label);o.value=k;select.append(o);} select.value=kind;
  form.append(input,select,el('button','検索')); form.onsubmit=e=>{e.preventDefault();query=input.value;kind=select.value;offset=0;render().catch(fail);}; content.append(form);
  const records=await api(`/api/history?offset=${offset}&q=${encodeURIComponent(query)}&kind=${encodeURIComponent(kind)}`); if(id!==requestId)return;
  if(!records.rows.length)empty(); else content.append(add(el('div',undefined,'rows'),...records.rows.map(v=>{const n=row(v.topic||v.summary||v.kind,v.note||v.summary,v);n.prepend(el('small',`${v.ts||''} · ${v.source||''}`));return n;})));
  const paging=add(el('div',undefined,'paging'),el('span',`${records.total}件`));
  const prev=el('button','前へ'); prev.disabled=offset===0;prev.onclick=()=>{offset=Math.max(0,offset-50);render().catch(fail);};
  const next=el('button','次へ'); next.disabled=records.next_offset===null;next.onclick=()=>{offset=records.next_offset;render().catch(fail);};paging.append(prev,next);content.append(paging);
 }
 if(view==='connections') {
  content.append(row('MCP','登録や認証は watari connect で行います。ここでは外部への接続テストを実行しません。認証キー・実行引数・環境変数は表示しません。'));
  const mcp=data.connections.mcp;
  if(!mcp.available)content.append(row('MCP拡張が未導入です',mcp.message));
  if(mcp.error)content.append(row('確認できません',mcp.error));
  if(mcp.config_files?.length)content.append(details(mcp.config_files,'接続設定の参照先'));
  section('MCP接続先',mcp.servers.map(s=>row(s.name,`${s.status==='disabled'?'無効':'登録済み・接続状態未確認'} · ${s.transport}${s.endpoint?' · '+s.endpoint:''}`,s)));
  section('従来方式・ローカルの読み取り先',data.connections.legacy.map(c=>row(c.name,c.scope==='local'?'このパソコンのデータ':'従来方式のサービス読み取り',c)));
  content.append(el('p','MCPの追加だけでは定期的な記憶の読み取りは始まりません。既存の読み取り設定は自動で移行・削除しません。','muted'));
 }
 if(view==='sync') {
  content.append(row('会話の同期',data.sync.conversation_credentials_present?'認証情報の保存あり · 実際の同期状態は未確認です。':'保存済み認証情報は確認できません。同期を使う場合は watari auth を実行してください。'));
  section('記録されているパソコン',data.sync.hosts.map(h=>row(h.hostname||h.machine_id,h.machine_id,h)));
  content.append(el('p','読み取り位置は保存された時点の情報です。GitやGoogle Driveへの同期成功を示すものではありません。','muted'));
 }
 if(view==='settings') {
  content.append(row('このパソコン',`${data.computer.hostname} · ${data.computer.computer} / ${data.computer.runtime}`,data.computer));
  if(data.session) content.append(row('この会話の環境（画面を開いた時点）',`${data.session.provider||''} / ${data.session.model||''} · thinking: ${data.session.thinking||''}`,data.session));
  else content.append(row('会話の環境','モデル・思考設定・利用可能な道具は、会話中の /dashboard から開くと表示されます。'));
  content.append(row('設定',`Watari ${data.package_version} · ${data.settings.performance}`,data.settings));
  content.append(el('p','秘密を含み得る設定項目は値を表示せず、項目名だけを示します。記憶の本文と出典には私的な内容が含まれます。このURLは共有しないでください。','muted'));
  section('機能とコマンド',data.capabilities.map(c=>row(c.name,c.detail,{command:c.command})));
 }
}
function fail(e){notice.textContent=e.message;}
async function refresh(){notice.textContent='';data=await api('/api/snapshot');document.querySelector('#machine').textContent=`${data.computer.hostname} · ${data.computer.computer.toUpperCase()}`;document.querySelector('#updated').textContent=`表示を更新: ${new Date(data.generated_at).toLocaleString()}`;if(data.errors.length)notice.textContent=data.errors.join('\n');await render();}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{view=b.dataset.view;render().catch(fail);});
document.querySelector('#refresh').onclick=()=>refresh().catch(fail);
refresh().catch(fail);
