const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = value => String(value ?? '').replace(/[&<>\'\"]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[c]));

const store = {
  get(key, fallback = null) {
    try { return JSON.parse(localStorage.getItem(`acumen_${key}`)) ?? fallback; }
    catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(`acumen_${key}`, JSON.stringify(value)); return true; }
    catch { return false; }
  },
  remove(key) { try { localStorage.removeItem(`acumen_${key}`); } catch {} }
};

let supabaseClient = null;
let currentUser = null;
let supabaseBooted = false;

async function bootSupabase() {
  if (supabaseBooted) return currentUser;
  supabaseBooted = true;
  if (!window.supabase?.createClient) return null;

  try {
    const cfg = await fetch('/api/config', { cache: 'no-store' }).then(r => r.ok ? r.json() : null);
    if (!cfg?.supabase_url || !cfg?.supabase_publishable_key) return null;

    supabaseClient = window.supabase.createClient(cfg.supabase_url, cfg.supabase_publishable_key);
    const { data, error } = await supabaseClient.auth.getSession();
    if (!error && data?.session?.user) currentUser = data.session.user;
    return currentUser;
  } catch (error) {
    console.info('Supabase unavailable. Local mode remains active.', error?.message || error);
    supabaseClient = null;
    currentUser = null;
    return null;
  }
}

async function ensureUser() { return currentUser || await bootSupabase(); }

async function dbInsert(table, row) {
  const user = await ensureUser();
  if (!supabaseClient || !user) return { data: null, error: new Error('No Supabase session') };
  return supabaseClient.from(table).insert(row).select().single();
}

async function dbUpsert(table, row) {
  const user = await ensureUser();
  if (!supabaseClient || !user) return { data: null, error: new Error('No Supabase session') };
  return supabaseClient.from(table).upsert(row).select().single();
}

async function dbUpdate(table, values, filterColumn, filterValue) {
  const user = await ensureUser();
  if (!supabaseClient || !user) return { data: null, error: new Error('No Supabase session') };
  return supabaseClient.from(table).update(values).eq(filterColumn, filterValue).select().single();
}

async function dbSelect(table, columns = '*', queryFn = q => q) {
  const user = await ensureUser();
  if (!supabaseClient || !user) return { data: [], error: new Error('No Supabase session') };
  return queryFn(supabaseClient.from(table).select(columns));
}

async function api(url, options = {}) {
  const isForm = options.body instanceof FormData;
  const headers = { ...(options.headers || {}) };
  if (!isForm && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
  const response = await fetch(url, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    let detail = typeof data.detail === 'object' ? data.detail?.message : data.detail;
    const kind = typeof data.detail === 'object' ? data.detail?.kind : '';
    if (Array.isArray(data.detail)) {
      detail = data.detail.map(item => item?.msg).filter(Boolean).join(' · ');
    }
    const suffix = kind === 'auth' ? ' Open Settings and check your Gemini key.' : '';
    throw new Error((detail || data.message || `Request failed (${response.status})`) + suffix);
  }
  return data;
}

function apiKey() { return localStorage.getItem('acumen_key') || ''; }
function model() { return localStorage.getItem('acumen_model') || 'gemini-2.5-flash'; }

function toast(message, kind = 'normal') {
  const element = $('#toast');
  if (!element) return;
  element.textContent = message;
  element.dataset.kind = kind;
  element.classList.add('show');
  clearTimeout(window.__acumenToast);
  window.__acumenToast = setTimeout(() => element.classList.remove('show'), 3200);
}

async function updateAccountNav() {
  const link = $('#accountNav');
  if (!link) return;
  const user = await ensureUser();
  if (user) {
    link.textContent = 'Account · signed in';
    link.dataset.state = 'signed-in';
    link.title = user.email || 'Signed in';
  } else {
    link.textContent = 'Account';
    link.dataset.state = 'signed-out';
    link.title = 'Account is optional';
  }
}

function nav() {
  const page = location.pathname.split('/').pop().replace('.html', '') || 'index';
  const navEl = $('#nav');
  if (navEl) {
    navEl.innerHTML = `
      <div class="navin">
        <a class="brand" href="/"><span class="mark">A</span><span>ACUMEN</span></a>
        <div class="links">
          <a href="/assessment.html" data-p="assessment">Scan</a>
          <a href="/blueprint.html" data-p="blueprint">Blueprint</a>
          <a href="/mr-brown.html" data-p="mr-brown">Mentor</a>
          <a href="/quiz-forge.html" data-p="quiz-forge">Quiz Forge</a>
          <a href="/roadmap.html" data-p="roadmap">Roadmap</a>
        </div>
        <div class="actions"><a class="nav-pill" href="/faq.html">About</a><a class="nav-account" id="accountNav" href="/account.html">Account</a><a class="btn primary small" href="/settings.html">Settings</a></div>
      </div>`;
    $$(`[data-p="${CSS.escape(page)}"]`).forEach(link => link.classList.add('active'));
  }
  // UPGRADE: Make account state visible everywhere. Users should never have to guess whether they are signed in.
  updateAccountNav();

  const footer = $('#footer');
  if (footer) footer.innerHTML = `<div class="footerin"><span><b>ACUMEN</b> · built by students, for students.</span><span>Self-reflection, not diagnosis. AI can be wrong.</span></div>`;
}

function profileLocal() { return store.get('profile', {}); }
function resultLocal() { return store.get('result', null); }

// UPGRADE: Keep the last completed result and history local even when cloud auth is unavailable.
function hasLocalHistory() { return Array.isArray(store.get('history', [])) && store.get('history', []).length > 0; }

function needProfile() {
  if (!profileLocal().pseudo) {
    toast('Set up your student profile first.', 'warn');
    setTimeout(() => { location.href = '/#profile-setup'; }, 100);
    return false;
  }
  return true;
}

function formDataObject(form) {
  if (!(form instanceof HTMLFormElement)) throw new Error('Expected a form element.');
  return Object.fromEntries(new FormData(form));
}

function setBusy(button, busy, label = 'Working…') {
  if (!button) return;
  if (busy) {
    button.dataset.originalText = button.textContent;
    button.disabled = true;
    button.textContent = label;
  } else {
    button.disabled = false;
    button.textContent = button.dataset.originalText || button.textContent;
  }
}

async function saveProfile(profile) {
  const clean = { pseudo: profile.pseudo.trim(), context: profile.context || 'High School' };
  store.set('profile', clean);
  const user = await ensureUser();
  if (!user) return false;
  const { error } = await dbUpsert('acumen_profiles', {
    id: user.id,
    display_name: clean.pseudo,
    school_level: clean.context,
    onboarding_completed: true,
  });
  return !error;
}

async function home() {
  const form = $('#profile-form');
  if (!(form instanceof HTMLFormElement)) return;
  const profile = profileLocal();
  if (form.elements.pseudo && profile.pseudo) form.elements.pseudo.value = profile.pseudo;
  if (form.elements.context && profile.context) form.elements.context.value = profile.context;

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const submit = $('button[type="submit"]', form) || $('button', form);
    try {
      const data = formDataObject(form);
      if (!data.pseudo?.trim()) return toast('Choose a nickname first.', 'warn');
      setBusy(submit, true, 'Preparing your scan…');
      const synced = await saveProfile(data);
      if (!synced) toast('Profile saved on this device. Supabase sync is unavailable.', 'warn');
      location.href = '/assessment.html';
    } catch (error) {
      console.error('Profile submit failed:', error);
      toast(error.message || 'Could not save the profile.', 'warn');
      setBusy(submit, false);
    }
  });
}

async function assessment() {
  if (!needProfile()) return;
  const statementBox = $('#statements');
  const next = $('#next');
  const prev = $('#prev');
  if (!statementBox || !next || !prev) return;

  try {
    const { questions } = await api('/api/questions');
    if (!Array.isArray(questions) || !questions.length) throw new Error('The question bank is empty.');

    let answers = store.get('answers', {});
    let index = Math.min(Math.max(Number(localStorage.getItem('acumen_i') || 0), 0), questions.length - 1);

    const render = () => {
      const question = questions[index];
      const saved = answers[question.id] || {};
      $('#qi').textContent = `${String(index + 1).padStart(2, '0')} / ${questions.length}`;
      $('#section').textContent = question.section || 'Assessment';
      $('#question').textContent = question.question;
      $('#bar').style.width = `${((index + 1) / questions.length) * 100}%`;
      statementBox.innerHTML = question.statements.map((statement, idx) => `
        <article class="statement ${saved[statement.key] ? 'rated' : ''}">
          <div class="statement-head"><span class="statement-index">0${idx + 1}</span><div><b>${esc(statement.label)}</b><p>${esc(statement.text)}</p></div></div>
          <div class="scale" role="radiogroup" aria-label="Rate statement">
            ${[1,2,3,4,5].map(value => `<button type="button" class="scale-btn ${saved[statement.key] === value ? 'selected' : ''}" data-k="${esc(statement.key)}" data-v="${value}" aria-pressed="${saved[statement.key] === value}"><strong>${value}</strong><small>${['Not me','Rarely','Sometimes','Often','Very me'][value - 1]}</small></button>`).join('')}
          </div>
        </article>`).join('');

      $$('.scale-btn', statementBox).forEach(button => {
        button.addEventListener('click', () => {
          answers[question.id] ||= {};
          answers[question.id][button.dataset.k] = Number(button.dataset.v);
          store.set('answers', answers);
          const statement = button.closest('.statement');
          statement?.classList.add('rated');
          $$('.scale-btn', button.parentElement).forEach(item => {
            item.classList.remove('selected');
            item.setAttribute('aria-pressed', 'false');
          });
          button.classList.add('selected');
          button.setAttribute('aria-pressed', 'true');
        });
      });

      prev.disabled = index === 0;
      next.textContent = index === questions.length - 1 ? 'Generate my blueprint' : 'Continue';
      $('#counterNote').textContent = `${questions.length - index - 1} scenarios remaining`;
    };

    render();
    prev.onclick = () => {
      index = Math.max(0, index - 1);
      localStorage.setItem('acumen_i', String(index));
      render();
      scrollTo({ top: 0, behavior: 'smooth' });
    };

    next.onclick = async () => {
      const current = answers[questions[index].id] || {};
      const requiredKeys = questions[index].statements.map(statement => statement.key);
      const complete = requiredKeys.length === 4 && requiredKeys.every(key => Number.isInteger(current[key]) && current[key] >= 1 && current[key] <= 5);
      if (!complete) return toast('Rate all four statements before continuing.', 'warn');
      setBusy(next, true, index === questions.length - 1 ? 'Scoring…' : 'Saving…');
      try {
        if (index < questions.length - 1) {
          index += 1;
          localStorage.setItem('acumen_i', String(index));
          render();
          setBusy(next, false);
          scrollTo({ top: 0, behavior: 'smooth' });
          return;
        }

        const result = await api('/api/assessment/score', { method: 'POST', body: JSON.stringify({ answers }) });
        store.set('result', result);
        const now = new Date().toISOString();
        const history = store.get('history', []);
        history.unshift({
          id: `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          questionnaire_version: 'v2-likert',
          status: 'completed',
          answers,
          scores: result.vectors,
          dominant_traits: result.top_matches,
          profile_snapshot: result,
          created_at: now,
          completed_at: now,
        });
        store.set('history', history.slice(0, 20));

        const user = await ensureUser();
        if (user) {
          const saved = await dbInsert('acumen_assessments', {
            profile_id: user.id,
            questionnaire_version: 'v2-likert',
            status: 'completed',
            answers,
            scores: result.vectors,
            dominant_traits: result.top_matches,
            profile_snapshot: result,
          });
          if (!saved.error) await dbUpdate('acumen_profiles', { latest_assessment_id: saved.data.id }, 'id', user.id);
        }

        store.remove('answers');
        localStorage.removeItem('acumen_i');
        location.href = '/account.html?from=scan';
      } catch (error) {
        console.error('Assessment submit failed:', error);
        toast(error.message || 'The scan could not be completed.', 'warn');
        setBusy(next, false);
      }
    };
  } catch (error) {
    console.error('Assessment boot failed:', error);
    statementBox.innerHTML = `<div class="notice">${esc(error.message || 'The scan could not load.')}<br><br>Check that ACUMEN is running on port 8001, then refresh.</div>`;
    next.disabled = true;
  }
}

function scoreBand(value) { const n = Number(value) || 0; return n < 43 ? 'Develop' : n > 68 ? 'Leverage' : 'Balanced'; }

function profileAdviceFallback(result) {
  const axes = Array.isArray(result?.axes) ? result.axes : [];
  const library = {
    'Active Processing': { title:'Make your thinking visible', why:'Your responses suggest that turning information into something you can explain or retrieve may be a useful place to experiment.', action:'Close your notes and explain one concept from memory for 5 minutes, then check what you missed.', minutes:10 },
    'Execution Reliability': { title:'Make the first move smaller', why:'Your responses suggest that the gap may be less about knowing what to do and more about making the first action concrete enough to start.', action:'Write one task as a verb + object, prepare the exact material, and work on it for 10 minutes before planning anything else.', minutes:10 },
    'Uncertainty Flexibility': { title:'Practise changing course without losing the goal', why:'Your responses suggest that unexpected changes may be worth treating as a skill to practise rather than a reason to abandon the session.', action:'Pick one study task and create a simple Plan B that takes 10 minutes if Plan A becomes impossible.', minutes:10 },
    'Cognitive Endurance': { title:'Stop measuring study by sheer duration', why:'Your responses suggest that the useful part of a session matters more than how long you remain at the desk.', action:'Do one 15-minute active block using questions, retrieval or exercises, then stop and check whether the work was actually productive.', minutes:15 }
  };
  return axes.sort((a,b)=>Number(a.score)-Number(b.score)).slice(0,2).map(axis => {
    const item = library[axis.name];
    return item ? { axis_name:axis.name, ...item, actions:[item.action] } : null;
  }).filter(Boolean);
}

async function blueprint() {
  if (!needProfile()) return;
  const result = resultLocal();
  if (!result) { location.href = '/assessment.html'; return; }
  $('#scores').innerHTML = (result.axes || Object.entries(result.vectors || {}).map(([key, score]) => ({ key, name: key, description: '', score }))).map(axis => `
    <article class="score-card"><div class="score-top"><span>${esc(String(axis.name).replaceAll('_', ' '))}</span><span>${scoreBand(axis.score)}</span></div><div class="score-number">${Math.round(axis.score)}<small>/100</small></div><div class="meter"><i style="width:${Math.max(0, Math.min(100, axis.score))}%"></i></div><p>${esc(axis.description || '')}</p></article>`).join('');
  const axisName = key => result.axes?.find(axis => axis.key === key)?.name || key || '—';
  $('#strong').textContent = String(axisName(result.strongest)).replaceAll('_', ' ');
  $('#weak').textContent = String(axisName(result.weakest)).replaceAll('_', ' ');
  $('#signals').innerHTML = (result.top_matches || []).map((item, i) => `<article class="signal"><span class="signal-no">0${i + 1}</span><div><b>${esc(item.label)}</b><p>${esc(item.choice_text)}</p><span class="rating">Your rating · ${item.rating}/5</span></div></article>`).join('');
  const advice = Array.isArray(result.advice) && result.advice.length ? result.advice : profileAdviceFallback(result);
  $('#advice').innerHTML = advice.map(item => `<article class="advice-card"><span class="tag">${esc(item.axis_name || 'PROFILE SIGNAL')}</span><h3>${esc(item.title)}</h3><p>${esc(item.why)}</p><div class="action-box"><small>${esc(item.minutes || 10)} MINUTE EXPERIMENT</small><b>${esc(item.actions?.[0] || item.action || '')}</b></div></article>`).join('');
  if (!advice.length) $('#advice').innerHTML = '<div class="empty"><h3>Finish a scan to unlock profile guidance.</h3><p>Your recommendations appear here after ACUMEN has enough responses to work with.</p></div>';

  // UPGRADE: Make the three core AI experiences visible from the blueprint instead of hiding them in the navigation.
  const aiGrid = $('#aiGrid');
  if (aiGrid) aiGrid.innerHTML = `
    <a class="ai-card" href="/mr-brown.html"><span class="ai-kicker">01 · MR. BROWN</span><h3>Talk through a real study problem</h3><p>Conversation, profile context and one concrete experiment at the end.</p><span class="ai-link">Open mentor</span></a>
    <a class="ai-card" href="/what-if.html"><span class="ai-kicker">02 · CHRONOS</span><h3>Explore a choice before you make it</h3><p>Compare plausible mechanisms, trade-offs and uncertainty without pretending to predict your future.</p><span class="ai-link">Explore a scenario</span></a>
    <a class="ai-card" href="/old-days.html"><span class="ai-kicker">03 · THE ARCHIVIST</span><h3>Examine an alternate path</h3><p>Use counterfactual thinking to understand choices, consequences and what is still under your control.</p><span class="ai-link">Open alternate timeline</span></a>`;
}

async function historyPage() {
  if (!needProfile()) return;
  const renderHistory = data => {
    if (!data.length) {
      $('#historyList').innerHTML = `<div class="empty"><span>01</span><h3>No scans yet.</h3><p>Your next completed scan will appear here.</p><a class="btn primary" href="/assessment.html">Run first scan ↗</a></div>`;
      return;
    }
    $('#historyList').innerHTML = data.map((item, index) => {
      const scores = item.scores || {};
      const top = Object.entries(scores).sort((a, b) => Number(b[1]) - Number(a[1]))[0];
      const date = item.created_at ? new Date(item.created_at).toLocaleDateString(undefined, { year:'numeric', month:'short', day:'numeric' }) : 'Saved locally';
      return `<article class="history-row"><div class="history-index">${String(data.length - index).padStart(2, '0')}</div><div class="history-main"><div class="eyebrow">${esc(date)}</div><h3>Scan ${data.length - index}</h3><p>${top ? `${esc(String(top[0]).replaceAll('_', ' '))} · ${Math.round(Number(top[1]))}/100` : 'Profile recorded'}</p></div><div class="mini-bars">${Object.values(scores).map(value => `<i style="height:${Math.max(8, Math.min(100, Number(value) || 0))}%"></i>`).join('')}</div></article>`;
    }).join('');
  };

  const local = store.get('history', []);
  const user = await ensureUser();
  if (!user) return renderHistory(local);
  const { data, error } = await dbSelect('acumen_assessments', 'id,questionnaire_version,status,scores,dominant_traits,created_at,completed_at', q => q.eq('profile_id', user.id).order('created_at', { ascending: false }).limit(20));
  renderHistory(error || !data?.length ? local : data);
}

function chat() {
  if (!needProfile()) return;
  const form = $('#chat');
  const messages = $('#messages');
  if (!(form instanceof HTMLFormElement) || !messages) return;
  let history = store.get('chat_history', []);
  history.forEach(item => add(item.role === 'assistant' ? 'ai' : 'user', item.content));

  form.onsubmit = async event => {
    event.preventDefault();
    try {
      const data = formDataObject(form);
      const text = String(data.msg || '').trim();
      if (!text) return;
      const input = $('#msg', form);
      const send = $('button[type="submit"]', form) || $('button', form);
      add('user', text);
      if (input) input.value = '';
      setBusy(send, true, 'Thinking…');
      const pending = add('ai', 'Thinking through the evidence…', true);
      const result = await api('/api/ai/chat', { method:'POST', body:JSON.stringify({ api_key:apiKey(), model:model(), prompt:text, history, profile:resultLocal() || {} }) });
      pending.remove();
      add('ai', result.answer);
      history.push({ role:'user', content:text }, { role:'assistant', content:result.answer });
      store.set('chat_history', history.slice(-20));
      await saveConversationMessage(text, result.answer);
    } catch (error) {
      console.error('Chat failed:', error);
      toast(error.message || 'The mentor could not respond.', 'warn');
    } finally {
      const send = $('button[type="submit"]', form) || $('button', form);
      setBusy(send, false);
    }
  };

  function renderMentorMarkdown(value) {
    // UPGRADE: Keep Mr. Brown's headings and bold emphasis readable without adding a full markdown library.
    let html = esc(value);
    html = html.replace(/^###\s+(.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^##\s+(.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^#\s+(.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\n{2,}/g, '</p><p>');
    html = html.replace(/\n/g, '<br>');
    return `<p>${html}</p>`;
  }

  function add(role, text, pending = false) {
    const bubble = document.createElement('div');
    bubble.className = `bubble ${role}${pending ? ' pending' : ''}`;
    bubble.innerHTML = role === 'ai' && !pending ? renderMentorMarkdown(text) : esc(text);
    messages.appendChild(bubble);
    messages.scrollTop = messages.scrollHeight;
    return bubble;
  }
}

async function saveConversationMessage(userText, assistantText) {
  const user = await ensureUser();
  if (!user) return;

  // FIX: acumen_conversations.profile_id references acumen_profiles.id. Auth can exist
  // before the profile row does, which makes PostgREST reject the conversation insert.
  const localProfile = profileLocal();
  const profileSync = await dbUpsert('acumen_profiles', {
    id: user.id,
    display_name: localProfile.pseudo || user.email?.split('@')[0] || 'Student',
    school_level: localProfile.context || 'High School',
    onboarding_completed: !!resultLocal(),
    updated_at: new Date().toISOString(),
  });
  if (profileSync.error) {
    console.warn('Mentor profile sync failed:', profileSync.error.message);
    return;
  }

  let conversationId = store.get('conversation_id');
  if (conversationId) {
    // FIX: Never trust a locally stored conversation id after an account change. Verify ownership first.
    const owned = await dbSelect('acumen_conversations', 'id', q => q.eq('id', conversationId).eq('profile_id', user.id).limit(1));
    if (!owned.data?.[0]?.id) { conversationId = null; store.remove('conversation_id'); }
  }
  if (!conversationId) {
    const created = await dbInsert('acumen_conversations', { profile_id:user.id, title:'Study mentor', context:{ profile:resultLocal()?.vectors || {} } });
    if (created.error) {
      // FIX: A conflict must never break Mr. Brown. Recover the latest conversation owned by this account.
      const recovered = await dbSelect('acumen_conversations', 'id', q => q.eq('profile_id', user.id).order('updated_at', { ascending:false }).limit(1));
      if (recovered.data?.[0]?.id) conversationId = recovered.data[0].id;
      else return;
    } else {
      conversationId = created.data.id;
    }
    store.set('conversation_id', conversationId);
  }
  await supabaseClient.from('acumen_messages').insert([
    { conversation_id:conversationId, profile_id:user.id, role:'user', content:userText },
    { conversation_id:conversationId, profile_id:user.id, role:'assistant', content:assistantText },
  ]);
  await dbUpdate('acumen_conversations', { updated_at:new Date().toISOString() }, 'id', conversationId);
}

function simulation(kind) {
  if (!needProfile()) return;
  const form = $('#sim');
  const output = $('#out');
  if (!(form instanceof HTMLFormElement) || !output) return;
  form.onsubmit = async event => {
    event.preventDefault();
    const button = $('button[type="submit"]', form) || $('button', form);
    try {
      const data = formDataObject(form);
      setBusy(button, true, 'Running…');
      output.innerHTML = '<div class="loading-card">Running scenario model…</div>';
      const result = await api(`/api/simulations/${kind}`, { method:'POST', body:JSON.stringify({ api_key:apiKey(), model:model(), profile:resultLocal() || {}, scenario:data.scenario, academic_tier:data.tier, environment:data.env }) });
      output.innerHTML = `<article class="result-card"><div class="eyebrow">SCENARIO OUTPUT</div><p>${esc(result.answer)}</p></article>`;
    } catch (error) {
      console.error(`${kind} failed:`, error);
      output.innerHTML = `<div class="notice">${esc(error.message)}</div>`;
    } finally { setBusy(button, false); }
  };
}

async function quiz() {
  const file = $('#file');
  const source = $('#source');
  const form = $('#qform');
  if (!file || !(form instanceof HTMLFormElement)) return;

  // UPGRADE: Explain AI readiness before the user submits a quiz.
  const setupNotice = $('.ai-setup-notice');
  if (setupNotice) {
    const ready = !!apiKey();
    setupNotice.innerHTML = ready
      ? '<b>Gemini is ready.</b> Quiz Forge uses the same key as Mr. Brown and Study Plan.'
      : '<b>Gemini key needed.</b> Add the same Gemini API key in Settings. The scan itself does not need AI.';
    setupNotice.dataset.state = ready ? 'ready' : 'missing';
  }

  file.addEventListener('change', async () => {
    if (!file.files?.[0]) return;
    const fileInfo = $('#fileinfo');
    const data = new FormData();
    data.append('file', file.files[0]);
    if (fileInfo) fileInfo.textContent = 'Extracting text…';
    try {
      const result = await api('/api/quiz/extract', { method:'POST', body:data });
      source.value = result.text;
      if (fileInfo) fileInfo.textContent = `${result.filename} · ${result.characters.toLocaleString()} characters`;
    } catch (error) {
      console.error('File extraction failed:', error);
      if (fileInfo) fileInfo.textContent = '';
      toast(error.message || 'Could not read this file.', 'warn');
    }
  });

  form.onsubmit = async event => {
    event.preventDefault();
    const button = $('button[type="submit"]', form) || $('button', form);
    try {
      const data = formDataObject(form);
      data.api_key = apiKey();
      data.model = model();
      data.num_questions = Number(data.num_questions);
      data.source_text = String(data.source_text || '').slice(0, 45000);
      if (!String(data.source_text || '').trim()) return toast('Add study material first.', 'warn');
      setBusy(button, true, 'Forging…');
      $('#quizout').innerHTML = '<div class="loading-card">Forging retrieval questions…</div>';
      renderQuiz(await api('/api/quiz/generate', { method:'POST', body:JSON.stringify(data) }));
    } catch (error) {
      console.error('Quiz generation failed:', error);
      $('#quizout').innerHTML = `<div class="notice">${esc(error.message)}</div>`;
    } finally { setBusy(button, false); }
  };
}

function renderQuiz(quizData) {
  const output = $('#quizout');
  if (!output) return;
  let answers = {};
  const modeNotice = quizData.mode === 'local_fallback'
    ? '<div class="notice" style="margin-bottom:18px"><b>Local recovery mode.</b> Gemini was temporarily unavailable, so ACUMEN built this quiz directly from your study material. No outside facts were added.</div>'
    : '';
  output.innerHTML = modeNotice + quizData.questions.map((question, index) => `<article class="card quiz-card"><span class="tag">QUESTION ${index + 1}</span><h3>${esc(question.question)}</h3>${Object.entries(question.options).map(([key, value]) => `<button type="button" class="option-btn" data-q="${index}" data-a="${esc(key)}">${key}. ${esc(value)}</button>`).join('')}<div class="exp" hidden></div></article>`).join('') + '<button id="grade" type="button" class="btn primary">Evaluate answers</button><div id="score" style="margin-top:18px"></div>';
  $$('.option-btn', output).forEach(button => button.onclick = () => {
    answers[button.dataset.q] = button.dataset.a;
    $$(`[data-q="${CSS.escape(button.dataset.q)}"]`, output).forEach(item => item.classList.remove('selected'));
    button.classList.add('selected');
  });
  $('#grade', output).onclick = () => {
    if (Object.keys(answers).length < quizData.questions.length) return toast('Answer every question first.', 'warn');
    let score = 0;
    quizData.questions.forEach((question, index) => {
      const correct = answers[index] === question.correct;
      score += correct ? 1 : 0;
      const explanation = $('.exp', $$('.quiz-card', output)[index]);
      explanation.hidden = false;
      explanation.innerHTML = `<div class="notice">${correct ? 'Correct.' : 'Not quite.'} ${esc(question.explanation)}</div>`;
    });
    $('#score', output).innerHTML = `<div class="result-card"><div class="score-number">${score}/${quizData.questions.length}</div><p>${Math.round(score / quizData.questions.length * 100)}% retrieval accuracy</p></div>`;
  };
}

function roadmap() {
  if (!needProfile()) return;
  const form = $('#plan');
  if (!(form instanceof HTMLFormElement)) return;
  form.onsubmit = async event => {
    event.preventDefault();
    const button = $('button[type="submit"]', form) || $('button', form);
    try {
      const data = formDataObject(form);
      data.api_key = apiKey();
      data.model = model();
      data.daily_hours = Number(data.daily_hours);
      data.plan_length = Number(data.plan_length);
      data.preferred_slots = $$('input[name="slots"]:checked', form).map(item => item.value);
      data.profile = resultLocal() || {};
      setBusy(button, true, 'Building…');
      $('#planout').innerHTML = '<div class="loading-card">Building a realistic roadmap…</div>';
      const result = await api('/api/planning/generate', { method:'POST', body:JSON.stringify(data) });
      const printable = `<div class="plan-sheet"><div class="plan-heading"><div><div class="eyebrow">ACUMEN · STUDY PLAN</div><h2>${esc(result.title || 'Study plan')}</h2><p>${esc(result.summary || 'A schedule built around your available time and profile.')}</p></div><div class="plan-meta">${esc(data.plan_length)} day${data.plan_length > 1 ? 's' : ''}</div></div>${result.days.map(day => `<section class="day"><div class="day-head"><span class="tag">DAY ${day.day}</span><div><h2>${esc(day.title)}</h2><p class="muted">${esc(day.focus || '')}</p></div></div>${(day.blocks || []).map(block => `<div class="block"><div class="time">${esc(block.time || '')}</div><div><b>${esc(block.task || '')}</b><div class="muted">${esc(block.note || '')}</div></div></div>`).join('')}</section>`).join('')}</div>`;
      $('#planout').innerHTML = `<div class="plan-actions"><button id="printPlan" class="btn primary" type="button">Print plan</button><button id="copyPlan" class="btn" type="button">Copy plan</button></div>${printable}`;
      $('#printPlan')?.addEventListener('click', () => window.print());
      $('#copyPlan')?.addEventListener('click', async () => {
        const text = result.days.map(day => `DAY ${day.day} · ${day.title}\n${day.focus || ''}\n${(day.blocks || []).map(b => `${b.time}  ${b.task}\n${b.note || ''}`).join('\n')}`).join('\n\n');
        try { await navigator.clipboard.writeText(text); toast('Plan copied.'); } catch { toast('Could not copy the plan.', 'warn'); }
      });
    } catch (error) {
      console.error('Roadmap failed:', error);
      $('#planout').innerHTML = `<div class="notice">${esc(error.message)}</div>`;
    } finally { setBusy(button, false); }
  };
}

async function syncLocalHistoryToCloud(user) {
  if (!user || !supabaseClient) return { synced: 0, failed: 0 };

  const profile = profileLocal();
  if (profile.pseudo) {
    const profileResult = await dbUpsert('acumen_profiles', {
      id: user.id,
      display_name: profile.pseudo,
      school_level: profile.context || 'High School',
      onboarding_completed: true,
    });
    if (profileResult.error) console.warn('Profile sync failed:', profileResult.error.message);
  }

  const history = store.get('history', []);
  const syncedIds = new Set(store.get('synced_history_ids', []));
  let synced = 0;
  let failed = 0;

  for (const item of [...history].reverse()) {
    if (!item?.id || syncedIds.has(item.id)) continue;
    const result = await dbInsert('acumen_assessments', {
      profile_id: user.id,
      questionnaire_version: item.questionnaire_version || 'v2-likert',
      status: item.status || 'completed',
      answers: item.answers || {},
      scores: item.scores || {},
      dominant_traits: item.dominant_traits || [],
      profile_snapshot: item.profile_snapshot || {},
    });
    if (result.error) {
      failed += 1;
      console.warn('History sync failed:', result.error.message);
    } else {
      syncedIds.add(item.id);
      synced += 1;
    }
  }

  store.set('synced_history_ids', [...syncedIds]);
  return { synced, failed };
}

async function account() {
  const signup = $('#signup');
  const login = $('#login');
  const signupButton = signup ? $('button[type="submit"]', signup) : null;
  const loginButton = login ? $('button[type="submit"]', login) : null;
  const status = $('#accountStatus');
  const user = await ensureUser();

  const showStatus = message => { if (status) status.textContent = message; };

  if (user) {
    showStatus(`Signed in as ${user.email || 'your account'}.`);
    const result = await syncLocalHistoryToCloud(user);
    if (result.synced) showStatus(`Account connected. ${result.synced} local scan${result.synced > 1 ? 's' : ''} synced to your history.`);
    const actions = $('#accountActions');
    if (actions) actions.innerHTML = `<a class="btn primary" href="/history.html">Open my history ↗</a> <button id="signout" class="btn" type="button">Sign out</button>`;
    $('#signout')?.addEventListener('click', async () => {
      if (supabaseClient) await supabaseClient.auth.signOut();
      currentUser = null;
      toast('Signed out. Local scans remain on this device.');
      setTimeout(() => location.reload(), 250);
    });
    return;
  }

  if (!supabaseClient) {
    showStatus('Account service is unavailable right now. Your scans remain saved locally on this device.');
  }

  if (signup) signup.onsubmit = async event => {
    event.preventDefault();
    if (!supabaseClient) return toast('Account service is unavailable right now.', 'warn');
    try {
      const data = formDataObject(signup);
      const email = String(data.email || '').trim();
      const password = String(data.password || '');
      if (!email || password.length < 6) return toast('Use a valid email and a password of at least 6 characters.', 'warn');
      setBusy(signupButton, true, 'Creating…');
      const { data: authData, error } = await supabaseClient.auth.signUp({ email, password });
      if (error) throw error;
      if (authData?.session?.user) {
        currentUser = authData.session.user;
        const result = await syncLocalHistoryToCloud(currentUser);
        showStatus(`Account created. ${result.synced} local scan${result.synced > 1 ? 's' : ''} synced.`);
        setTimeout(() => { location.href = '/blueprint.html'; }, 500);
      } else {
        showStatus('Account created. If email confirmation is enabled, check your inbox before signing in. You can also keep using ACUMEN without an account. Your local scans are safe on this device.');
      }
    } catch (error) {
      console.error('Sign-up failed:', error);
      toast(error.message || 'Could not create the account.', 'warn');
    } finally { setBusy(signupButton, false); }
  };

  if (login) login.onsubmit = async event => {
    event.preventDefault();
    if (!supabaseClient) return toast('Account service is unavailable right now.', 'warn');
    try {
      const data = formDataObject(login);
      const email = String(data.email || '').trim();
      const password = String(data.password || '');
      if (!email || !password) return toast('Enter your email and password.', 'warn');
      setBusy(loginButton, true, 'Signing in…');
      const { data: authData, error } = await supabaseClient.auth.signInWithPassword({ email, password });
      if (error) throw error;
      currentUser = authData.user;
      const result = await syncLocalHistoryToCloud(currentUser);
      showStatus(`Signed in. ${result.synced} local scan${result.synced > 1 ? 's' : ''} synced.`);
      setTimeout(() => { location.href = '/history.html'; }, 500);
    } catch (error) {
      console.error('Login failed:', error);
      const message = String(error?.message || '');
      if (/email not confirmed/i.test(message)) {
        showStatus('Your email is not confirmed yet. Check your inbox, then sign in. You can keep using ACUMEN without an account in the meantime.');
        toast('Confirm your email before signing in.', 'warn');
      } else {
        toast(message || 'Could not sign in.', 'warn');
      }
    } finally { setBusy(loginButton, false); }
  };
}

function settings() {
  const form = $('#settings');
  if (!(form instanceof HTMLFormElement)) return;
  if (form.elements.api_key) form.elements.api_key.value = apiKey();
  if (form.elements.model) form.elements.model.value = model();

  const updateStatus = () => {
    const status = $('#geminiStatus');
    if (!status) return;
    if (!apiKey()) {
      status.textContent = 'No Gemini key saved on this device.';
      status.dataset.state = 'missing';
    } else {
      status.textContent = 'A Gemini key is saved. Test it before using the AI tools.';
      status.dataset.state = 'saved';
    }
  };

  form.onsubmit = event => {
    event.preventDefault();
    try {
      const data = formDataObject(form);
      localStorage.setItem('acumen_key', String(data.api_key || '').trim());
      localStorage.setItem('acumen_model', data.model || 'gemini-2.5-flash');
      toast('Settings saved locally.');
      updateStatus();
    } catch (error) { toast(error.message, 'warn'); }
  };

  $('#testGemini')?.addEventListener('click', async () => {
    const button = $('#testGemini');
    const status = $('#geminiStatus');
    if (!apiKey()) return toast('Add your Gemini API key first.', 'warn');
    setBusy(button, true, 'Testing…');
    if (status) status.textContent = 'Testing Gemini…';
    try {
      const result = await api('/api/ai/test', {
        method:'POST',
        body:JSON.stringify({ api_key:apiKey(), model:model() })
      });
      if (status) {
        status.textContent = result.ok ? 'Gemini is connected and ready.' : 'Gemini responded, but the test was inconclusive.';
        status.dataset.state = result.ok ? 'ready' : 'warn';
      }
      toast(result.ok ? 'Gemini connection OK.' : 'Gemini responded, but check the result.', result.ok ? 'normal' : 'warn');
    } catch (error) {
      if (status) {
        status.textContent = error.message;
        status.dataset.state = 'error';
      }
      toast(error.message, 'warn');
    } finally { setBusy(button, false); }
  });

  updateStatus();
}

function feedback() {
  const form = $('#feedback');
  if (!(form instanceof HTMLFormElement)) return;
  form.onsubmit = async event => {
    event.preventDefault();
    const button = $('button[type="submit"]', form) || $('button', form);
    try {
      const data = formDataObject(form);
      const user = await ensureUser();
      if (user) {
        const result = await dbInsert('acumen_feedback', { profile_id:user.id, target_type:'general', rating:Number(data.rating), liked:Number(data.rating) >= 4, comment:data.message || null });
        if (result.error) throw result.error;
      } else {
        const feedbackItems = store.get('feedback', []);
        feedbackItems.unshift({ ...data, created_at:new Date().toISOString() });
        store.set('feedback', feedbackItems.slice(0, 50));
      }
      form.reset();
      toast('Feedback saved.');
    } catch (error) {
      console.error('Feedback failed:', error);
      toast(error.message || 'Feedback could not be saved.', 'warn');
    } finally { setBusy(button, false); }
  };
}

const pageHandlers = {
  index: home,
  assessment,
  blueprint,
  history: historyPage,
  'mr-brown': chat,
  'what-if': () => simulation('what-if'),
  'old-days': () => simulation('old-days'),
  'quiz-forge': quiz,
  roadmap,
  account,
  settings,
  feedback,
};

window.addEventListener('DOMContentLoaded', async () => {
  nav();
  try {
    await bootSupabase();
    await updateAccountNav();
    const page = location.pathname.split('/').pop().replace('.html', '') || 'index';
    const handler = pageHandlers[page];
    if (handler) await handler();
  } catch (error) {
    console.error('ACUMEN page initialization failed:', error);
    toast('This page hit an error. Open the console for details.', 'warn');
  }
});
