const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = v => String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

const store = {
  get(k, fallback = null) { try { return JSON.parse(localStorage.getItem(`acumen_${k}`)) ?? fallback; } catch { return fallback; } },
  set(k, v) { localStorage.setItem(`acumen_${k}`, JSON.stringify(v)); }
};

let supabaseClient = null;
let currentUser = null;

async function bootSupabase() {
  // UPGRADE: Anonymous Supabase Auth gives each browser a real user identity while
  // avoiding collection of an email or other personal identifier.
  if (!window.supabase) return null;
  try {
    const cfg = await fetch('/api/config').then(r => r.json());
    if (!cfg.supabase_url || !cfg.supabase_publishable_key) return null;
    supabaseClient = window.supabase.createClient(cfg.supabase_url, cfg.supabase_publishable_key);
    const existing = await supabaseClient.auth.getSession();
    if (existing.data.session?.user) {
      currentUser = existing.data.session.user;
      return currentUser;
    }
    const signed = await supabaseClient.auth.signInAnonymously();
    if (signed.error) throw signed.error;
    currentUser = signed.data.user;
    return currentUser;
  } catch (e) {
    console.warn('Supabase auth unavailable:', e.message);
    return null;
  }
}

async function ensureUser() {
  if (currentUser) return currentUser;
  return bootSupabase();
}

async function dbInsert(table, row) {
  const user = await ensureUser();
  if (!supabaseClient || !user) return { data: null, error: new Error('Supabase session unavailable') };
  return await supabaseClient.from(table).insert(row).select().single();
}

async function dbUpsert(table, row) {
  const user = await ensureUser();
  if (!supabaseClient || !user) return { data: null, error: new Error('Supabase session unavailable') };
  return await supabaseClient.from(table).upsert(row).select().single();
}

async function dbUpdate(table, values, filterColumn, filterValue) {
  const user = await ensureUser();
  if (!supabaseClient || !user) return { data: null, error: new Error('Supabase session unavailable') };
  return await supabaseClient.from(table).update(values).eq(filterColumn, filterValue).select().single();
}

async function dbSelect(table, columns = '*', queryFn = q => q) {
  const user = await ensureUser();
  if (!supabaseClient || !user) return { data: [], error: new Error('Supabase session unavailable') };
  let q = supabaseClient.from(table).select(columns);
  q = queryFn(q);
  return await q;
}

async function api(url, options = {}) {
  const opts = { ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } };
  const r = await fetch(url, opts);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail?.message || d.detail || d.message || 'Request failed');
  return d;
}

function apiKey() { return localStorage.getItem('acumen_key') || ''; }
function model() { return localStorage.getItem('acumen_model') || 'gemini-2.5-flash'; }

function toast(message, kind = 'normal') {
  const t = $('#toast'); if (!t) return;
  t.textContent = message; t.dataset.kind = kind; t.classList.add('show');
  clearTimeout(window.__toast); window.__toast = setTimeout(() => t.classList.remove('show'), 2800);
}

function nav() {
  const p = location.pathname.split('/').pop().replace('.html','') || 'index';
  const navEl = $('#nav');
  if (navEl) navEl.innerHTML = `
    <div class="navin">
      <a class="brand" href="/"><span class="mark">A</span><span>ACUMEN</span></a>
      <div class="links">
        <a href="/assessment.html" data-p="assessment">Scan</a>
        <a href="/blueprint.html" data-p="blueprint">Blueprint</a>
        <a href="/history.html" data-p="history">History</a>
        <a href="/mr-brown.html" data-p="mr-brown">Mentor</a>
        <a href="/quiz-forge.html" data-p="quiz-forge">Quiz Forge</a>
        <a href="/roadmap.html" data-p="roadmap">Roadmap</a>
      </div>
      <div class="actions"><a class="nav-pill" href="/faq.html">About</a><a class="btn primary small" href="/settings.html">Settings</a></div>
    </div>`;
  $$(`[data-p="${p}"]`).forEach(a => a.classList.add('active'));
  const footer = $('#footer');
  if (footer) footer.innerHTML = `<div class="footerin"><span><b>ACUMEN</b> · built by students, for students.</span><span>Self-reflection, not diagnosis. AI can be wrong.</span></div>`;
}

function profileLocal() { return store.get('profile', {}); }
function resultLocal() { return store.get('result', null); }
function needProfile() {
  if (!profileLocal().pseudo) { location = '/'; return false; }
  return true;
}

async function saveProfile(profile) {
  store.set('profile', profile);
  const user = await ensureUser();
  if (!user) return false;
  const { error } = await dbUpsert('acumen_profiles', {
    id: user.id,
    display_name: profile.pseudo,
    school_level: profile.context,
    onboarding_completed: true,
  });
  if (error) console.warn('Profile sync failed:', error.message);
  return !error;
}

async function home() {
  const f = $('#profile'); if (!f) return;
  const p = profileLocal();
  if (p.pseudo) f.pseudo.value = p.pseudo;
  if (p.context) f.context.value = p.context;
  f.onsubmit = async e => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(f));
    await saveProfile(d);
    toast('Profile secured. Starting your scan…');
    setTimeout(() => location = '/assessment.html', 450);
  };
}

async function assessment() {
  if (!needProfile()) return;
  const { questions } = await api('/api/questions');
  let answers = store.get('answers', {});
  let i = Number(localStorage.getItem('acumen_i') || 0);
  const render = () => {
    const q = questions[i], saved = answers[q.id] || {};
    $('#qi').textContent = `${String(i + 1).padStart(2,'0')} / ${questions.length}`;
    $('#section').textContent = q.section;
    $('#question').textContent = q.question;
    $('#bar').style.width = `${((i + 1) / questions.length) * 100}%`;
    $('#statements').innerHTML = q.statements.map((s, idx) => `
      <article class="statement ${saved[s.key] ? 'rated' : ''}">
        <div class="statement-head"><span class="statement-index">0${idx + 1}</span><div><b>${esc(s.label)}</b><p>${esc(s.text)}</p></div></div>
        <div class="scale" role="radiogroup" aria-label="Rate statement">
          ${[1,2,3,4,5].map(n => `<button type="button" class="scale-btn ${saved[s.key] === n ? 'selected' : ''}" data-k="${s.key}" data-v="${n}" aria-pressed="${saved[s.key] === n}"><strong>${n}</strong><small>${['Not me','Rarely','Sometimes','Often','Very me'][n-1]}</small></button>`).join('')}
        </div>
      </article>`).join('');
    $$('.scale-btn').forEach(b => b.onclick = () => {
      answers[q.id] ??= {};
      answers[q.id][b.dataset.k] = Number(b.dataset.v);
      store.set('answers', answers);
      $(`[data-k="${b.dataset.k}"]`, b.parentElement).closest('.statement').classList.add('rated');
      $$('.scale-btn', b.parentElement).forEach(x => { x.classList.remove('selected'); x.setAttribute('aria-pressed','false'); });
      b.classList.add('selected'); b.setAttribute('aria-pressed','true');
    });
    $('#prev').disabled = i === 0;
    $('#next').textContent = i === questions.length - 1 ? 'Generate my blueprint ↗' : 'Continue ↗';
    $('#counterNote').textContent = `${questions.length - i - 1} scenarios remaining`;
  };
  render();
  $('#prev').onclick = () => { i = Math.max(0, i - 1); localStorage.setItem('acumen_i', i); render(); scrollTo({top:0,behavior:'smooth'}); };
  $('#next').onclick = async () => {
    const current = answers[questions[i].id] || {};
    if (Object.keys(current).length < 4) { toast('Rate all four statements before continuing.', 'warn'); return; }
    if (i < questions.length - 1) { i++; localStorage.setItem('acumen_i', i); render(); scrollTo({top:0,behavior:'smooth'}); return; }
    const r = await api('/api/assessment/score', { method:'POST', body: JSON.stringify({ answers }) });
    store.set('result', r);
    const user = await ensureUser();
    if (user) {
      const row = { profile_id:user.id, questionnaire_version:'v2-likert', status:'completed', answers, scores:r.vectors, dominant_traits:r.top_matches, profile_snapshot:r };
      const saved = await dbInsert('acumen_assessments', row);
      if (saved.error) toast('Scan complete. History sync is temporarily unavailable.', 'warn');
      else {
        await dbUpdate('acumen_profiles', { latest_assessment_id:saved.data.id }, 'id', user.id);
      }
    }
    localStorage.removeItem('acumen_i');
    location = '/blueprint.html';
  };
}

function scoreBand(v) { return v < 43 ? 'Develop' : v > 68 ? 'Leverage' : 'Balanced'; }

async function blueprint() {
  if (!needProfile()) return;
  const r = resultLocal(); if (!r) { location = '/assessment.html'; return; }
  $('#scores').innerHTML = (r.axes || Object.entries(r.vectors).map(([key,score]) => ({key,name:key,description:'',score}))).map(x => `
    <article class="score-card"><div class="score-top"><span>${esc(x.name.replaceAll('_',' '))}</span><span>${scoreBand(x.score)}</span></div><div class="score-number">${Math.round(x.score)}<small>/100</small></div><div class="meter"><i style="width:${x.score}%"></i></div><p>${esc(x.description || '')}</p></article>`).join('');
  $('#strong').textContent = (r.axes?.find(x => x.key === r.strongest)?.name || r.strongest).replaceAll('_',' ');
  $('#weak').textContent = (r.axes?.find(x => x.key === r.weakest)?.name || r.weakest).replaceAll('_',' ');
  $('#signals').innerHTML = r.top_matches.map((x,i) => `<article class="signal"><span class="signal-no">0${i+1}</span><div><b>${esc(x.label)}</b><p>${esc(x.choice_text)}</p><span class="rating">Your rating · ${x.rating}/5</span></div></article>`).join('');
  $('#advice').innerHTML = (r.advice || []).map(a => `<article class="advice-card"><span class="tag">${esc(a.axis_name)}</span><h3>${esc(a.title)}</h3><p>${esc(a.why)}</p><div class="action-box"><small>10–15 MINUTE EXPERIMENT</small><b>${esc(a.actions?.[0] || a.action)}</b></div></article>`).join('');
  $('#historyLink').href = '/history.html';
}

async function historyPage() {
  if (!needProfile()) return;
  const user = await ensureUser();
  if (!user) { $('#historyList').innerHTML = `<div class="notice">History needs a Supabase session. The local scan is still available.</div>`; return; }
  const { data, error } = await dbSelect('acumen_assessments', 'id,questionnaire_version,status,scores,dominant_traits,created_at,completed_at', q => q.eq('profile_id', user.id).order('created_at',{ascending:false}).limit(20));
  if (error) { $('#historyList').innerHTML = `<div class="notice">Could not load history: ${esc(error.message)}</div>`; return; }
  if (!data?.length) { $('#historyList').innerHTML = `<div class="empty"><span>01</span><h3>No scans yet.</h3><p>Your next completed scan will appear here. Humans love graphs of themselves, apparently.</p><a class="btn primary" href="/assessment.html">Run first scan ↗</a></div>`; return; }
  $('#historyList').innerHTML = data.map((x,i) => {
    const scores = x.scores || {};
    const top = Object.entries(scores).sort((a,b) => b[1]-a[1])[0];
    return `<article class="history-row"><div class="history-index">${String(data.length-i).padStart(2,'0')}</div><div class="history-main"><div class="eyebrow">${new Date(x.created_at).toLocaleDateString(undefined,{year:'numeric',month:'short',day:'numeric'})}</div><h3>Scan ${data.length-i}</h3><p>${top ? `${esc(top[0].replaceAll('_',' '))} · ${Math.round(top[1])}/100` : 'Profile recorded'}</p></div><div class="mini-bars">${Object.values(scores).map(v=>`<i style="height:${Math.max(8,v)}%"></i>`).join('')}</div></article>`;
  }).join('');
}

function chat() {
  if (!needProfile()) return;
  let history = store.get('chat_history', []);
  const messages = $('#messages');
  history.forEach(x => add(x.role === 'assistant' ? 'ai' : 'user', x.content));
  $('#chat').onsubmit = async e => {
    e.preventDefault();
    const input = $('#msg'), text = input.value.trim(); if (!text) return;
    add('user', text); input.value = '';
    const pending = add('ai', 'Thinking through the evidence…', true);
    try {
      const r = await api('/api/ai/chat', { method:'POST', body:JSON.stringify({ api_key:apiKey(), model:model(), prompt:text, history, profile:resultLocal() || {} }) });
      pending.remove(); add('ai', r.answer);
      history.push({role:'user',content:text},{role:'assistant',content:r.answer});
      store.set('chat_history', history.slice(-20));
      await saveConversationMessage(text, r.answer);
    } catch (e) { pending.textContent = e.message; pending.classList.add('error'); }
  };
  function add(role,text,pending=false) { const d=document.createElement('div'); d.className=`bubble ${role}${pending?' pending':''}`; d.textContent=text; messages.appendChild(d); messages.scrollTop=messages.scrollHeight; return d; }
}

async function saveConversationMessage(userText, assistantText) {
  const user = await ensureUser(); if (!user) return;
  let conversationId = store.get('conversation_id');
  if (!conversationId) {
    const created = await dbInsert('acumen_conversations', { profile_id:user.id, title:'Study mentor', context:{ profile:resultLocal()?.vectors || {} } });
    if (created.error) return;
    conversationId = created.data.id; store.set('conversation_id', conversationId);
  }
  await supabaseClient.from('acumen_messages').insert([
    { conversation_id:conversationId, profile_id:user.id, role:'user', content:userText },
    { conversation_id:conversationId, profile_id:user.id, role:'assistant', content:assistantText },
  ]);
  await dbUpdate('acumen_conversations', { updated_at:new Date().toISOString() }, 'id', conversationId);
}

async function sim(kind) {
  if (!needProfile()) return;
  $('#sim').onsubmit = async e => {
    e.preventDefault(); const d = Object.fromEntries(new FormData(e.target));
    $('#out').innerHTML='<div class="loading-card">Running scenario model…</div>';
    try { const r=await api('/api/simulations/'+kind,{method:'POST',body:JSON.stringify({api_key:apiKey(),model:model(),profile:resultLocal()||{},scenario:d.scenario,academic_tier:d.tier,environment:d.env})}); $('#out').innerHTML=`<article class="result-card"><div class="eyebrow">SCENARIO OUTPUT</div><p>${esc(r.answer)}</p></article>`; }
    catch(e){$('#out').innerHTML=`<div class="notice">${esc(e.message)}</div>`;}
  };
}

async function quiz() {
  const f=$('#file'), src=$('#source'); if(!f)return;
  f.onchange=async()=>{const fd=new FormData();fd.append('file',f.files[0]);const r=await fetch('/api/quiz/extract',{method:'POST',body:fd}),d=await r.json();if(!r.ok){toast(d.detail,'warn');return}src.value=d.text;$('#fileinfo').textContent=`${d.filename} · ${d.characters.toLocaleString()} characters`};
  $('#qform').onsubmit=async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(e.target));d.api_key=apiKey();d.model=model();d.num_questions=+d.num_questions;$('#quizout').innerHTML='<div class="loading-card">Forging retrieval questions…</div>';try{renderQuiz(await api('/api/quiz/generate',{method:'POST',body:JSON.stringify(d)}));}catch(err){$('#quizout').innerHTML=`<div class="notice">${esc(err.message)}</div>`;}};
}
function renderQuiz(q){let a={};$('#quizout').innerHTML=q.questions.map((x,i)=>`<article class="card quiz-card"><span class="tag">QUESTION ${i+1}</span><h3>${esc(x.question)}</h3>${Object.entries(x.options).map(([k,v])=>`<button class="option-btn" data-q="${i}" data-a="${k}">${k}. ${esc(v)}</button>`).join('')}<div class="exp" hidden></div></article>`).join('')+'<button id="grade" class="btn primary">Evaluate answers ↗</button><div id="score" style="margin-top:18px"></div>';$$('.option-btn').forEach(b=>b.onclick=()=>{a[b.dataset.q]=b.dataset.a;$$(`[data-q="${b.dataset.q}"]`).forEach(x=>x.classList.remove('selected'));b.classList.add('selected')});$('#grade').onclick=()=>{if(Object.keys(a).length<q.questions.length){toast('Answer every question first.','warn');return}let s=0;q.questions.forEach((x,i)=>{const ok=a[i]===x.correct;s+=ok;const box=$$('.quiz-card')[i],ex=$('.exp',box);ex.hidden=false;ex.innerHTML=`<div class="notice">${ok?'Correct.':'Not quite.'} ${esc(x.explanation)}</div>`});$('#score').innerHTML=`<div class="result-card"><div class="score-number">${s}/${q.questions.length}</div><p>${Math.round(s/q.questions.length*100)}% retrieval accuracy</p></div>`}}

async function roadmap(){if(!needProfile())return;$('#plan').onsubmit=async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(e.target));d.api_key=apiKey();d.model=model();d.daily_hours=+d.daily_hours;d.plan_length=+d.plan_length;d.preferred_slots=$$('input[name=slots]:checked').map(x=>x.value);d.profile=resultLocal()||{};$('#planout').innerHTML='<div class="loading-card">Building a realistic roadmap…</div>';try{const r=await api('/api/planning/generate',{method:'POST',body:JSON.stringify(d)});$('#planout').innerHTML=`<div class="timeline">${r.days.map(x=>`<div class="day"><span class="tag">DAY ${x.day}</span><h2>${esc(x.title)}</h2>${(x.blocks||[]).map(b=>`<div class="block"><div class="time">${esc(b.time||'')}</div><b>${esc(b.task||'')}</b><div class="muted">${esc(b.note||'')}</div></div>`).join('')}</div>`).join('')}</div>`}catch(e){$('#planout').innerHTML=`<div class="notice">${esc(e.message)}</div>`}}}

function settings(){const f=$('#settings');if(!f)return;f.api_key.value=apiKey();f.model.value=model();f.onsubmit=e=>{e.preventDefault();localStorage.setItem('acumen_key',f.api_key.value.trim());localStorage.setItem('acumen_model',f.model.value);toast('Settings saved locally');};}
function feedback(){const f=$('#feedback');if(!f)return;f.onsubmit=async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(f));const user=await ensureUser();if(user){const r=await dbInsert('acumen_feedback',{profile_id:user.id,target_type:'general',rating:Number(d.rating),liked:Number(d.rating)>=4,comment:d.message||null});if(r.error)toast('Feedback could not be synced.','warn');else toast('Feedback saved.')}f.reset();};}

window.addEventListener('DOMContentLoaded', async()=>{
  nav();
  await bootSupabase();
  const p=location.pathname.split('/').pop().replace('.html','')||'index';
  ({index:home,assessment,blueprint,history:historyPage,'mr-brown':chat,'what-if':()=>sim('what-if'),'old-days':()=>sim('old-days'),'quiz-forge':quiz,roadmap,settings,feedback}[p]||(()=>{}))();
});
