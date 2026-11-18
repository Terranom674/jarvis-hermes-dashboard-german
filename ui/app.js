/* JARVIS Live HUD — drives Hermes Agent, streams telemetry.

   The brain is your own `hermes` CLI/profile, so configured Hermes tools,
   browser automation, skills, memory, MCP servers and third-party connectors are live. */
const $ = s => document.querySelector(s);
const RT = {tts:false, stt:false, provider:'browser', browserStt:false, browserTts:false};
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const speechSynth = window.speechSynthesis;
const API_TOKEN = document.querySelector('meta[name="jarvis-token"]')?.content || '';
const apiHeaders = extra => ({'x-jarvis-token': API_TOKEN, ...(extra || {})});

// ── reactor ticks ──
(() => {
  const g = $('#ticks480');
  for (let i = 0; i < 128; i++){
    const a = (i/128) * Math.PI*2, maj = i % 8 === 0;
    const r0 = maj ? 246 : 250, r1 = 260;
    const l = document.createElementNS('http://www.w3.org/2000/svg','line');
    l.setAttribute('x1', 260+Math.cos(a)*r0); l.setAttribute('y1', 260+Math.sin(a)*r0);
    l.setAttribute('x2', 260+Math.cos(a)*r1); l.setAttribute('y2', 260+Math.sin(a)*r1);
    if (maj) l.setAttribute('class','maj');
    g.appendChild(l);
  }
})();

const now = () => new Date().toLocaleTimeString('de-DE', {hour12:false});
const rid = () => 'run_' + (crypto.randomUUID ? crypto.randomUUID().replace(/-/g,'').slice(0,24)
                                              : Math.random().toString(16).slice(2,14));
const esc = s => String(s ?? '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

// ── reactor state ──
function setState(cls, word, sub){
  document.body.className = cls;
  if (word) $('#stword').textContent = word;
  if (sub != null) $('#strun').textContent = sub;
}
function setTag(cls, text){ const t=$('#rtag'); t.className='rtag '+cls; t.textContent=text; }

// ── action log ──
function log(kind, label, msg, jsonHtml){
  const e = document.createElement('div');
  e.className = 'entry k-' + kind;
  e.innerHTML = `<div class="top"><span class="ts">${now()}</span>`
    + `<span class="kind">${esc(label)}</span></div>`
    + (msg ? `<div class="msg">${esc(msg)}</div>` : '')
    + (jsonHtml ? `<div class="jsonblk">${jsonHtml}</div>` : '');
  const box = $('#log');
  box.insertBefore(e, box.firstChild);
  while (box.children.length > 40) box.removeChild(box.lastChild);
}
function usageBlock(u){
  const row = (k,v) => `<span class="k">${esc(k)}</span>: <span class="v">${Number(v)||0}</span>`;
  return [row('Eingabe-Token', u.input_tokens), row('Ausgabe-Token', u.output_tokens),
          row('Token gesamt', u.total_tokens)].join(' · ');
}

// ── the run ──
let running = false, answer = '', firstDelta = false, speakThisRun = true;
let speakDone = Promise.resolve(), activeController = null;

async function transmit(message, options = {}){
  if (!message.trim()) return;
  if (running){
    // don't silently swallow it — say so, so it never looks like nothing happened
    log('note','BESETZT',`Jarvis arbeitet noch – "${message.slice(0,40)}" wurde nicht gesendet. Esc zum Abbrechen.`);
    return;
  }
  running = true; answer = ''; firstDelta = false; speakThisRun = options.speak !== false;

  const fresh = /^\/(?:new|neu)\b/i.test(message.trim());
  const id = rid();
  setState('running', 'ARBEITET', id.slice(0,20) + '…');
  setTag('run', 'ARBEITET');
  $('#response').innerHTML = '<span class="cur"></span>';
  log('run', 'START', `Anfrage ${id} gestartet`);

  // visible elapsed counter — a slow answer should never look like a dead screen
  const t0 = performance.now();
  const tick = setInterval(() => {
    if (!running) return;
    const s = ((performance.now()-t0)/1000).toFixed(1);
    if (!answer) $('#strun').textContent = `Denkt nach … ${s} s`;
  }, 200);

  try {
    activeController = new AbortController();
    const res = await fetch('/api/run', {
      method:'POST', headers:apiHeaders({'content-type':'application/json'}),
      body: JSON.stringify({message, fresh}), signal:activeController.signal
    });
    if (!res.ok) throw new Error(`Server meldet HTTP ${res.status}`);
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true){
      const {value, done} = await reader.read();
      if (done) break;
      buf += dec.decode(value, {stream:true});
      let nl;
      while ((nl = buf.indexOf('\n')) >= 0){
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (line) handle(JSON.parse(line));
      }
    }
  } catch (e){
    if (e?.name === 'AbortError'){
      log('note', 'ABBRUCH', 'Auftrag abgebrochen');
      setState('', 'BEREIT', 'Abgebrochen');
      setTag('', 'BEREIT');
    } else {
      log('error', 'FEHLER', String(e).slice(0,200));
      setState('error', 'FEHLER', 'Verbindung unterbrochen');
      setTag('err', 'FEHLER');
    }
  }
  activeController = null;
  running = false;
  clearInterval(tick);
  await speakDone;                 // don't return until Jarvis has finished talking
}

function handle(ev){
  switch (ev.t){
    case 'status':
      if (ev.session_id) sys('session', ev.session_id.slice(0,8));
        const msg = `Hermes verbunden · Werkzeuge: ${ev.tools ?? 0} · Profil: ${ev.profile||'Standard'} · Berechtigung: ${ev.permission||'normal'}`;
      log('status', 'STATUS', msg);
      break;
    case 'latency':
      log('latency', 'LATENCY', `Erste Antwort nach ${ev.ms} ms`);
      break;
    case 'tool':
      if (ev.phase === 'use')
        log('tool', 'WERKZEUG', `→ ${ev.name}(${ev.input || ''})`);
      else
        log('tool', 'WERKZEUG', `✓ ${ev.ok===false?'Fehler':'OK'}`);
      break;
    case 'delta':
      answer += ev.text;
      renderAnswer();
      if (!firstDelta){
        firstDelta = true;
        log('reason', 'ANTWORT', answer.slice(0, 220));
      }
      break;
    case 'usage':
      log('status', 'FERTIG', 'Auftrag abgeschlossen', usageBlock(ev));
      break;
    case 'complete':
      setState('done', 'FERTIG', (ev.ms!=null?`${ev.ms}ms`:'') );
      setTag('done', 'FERTIG');
      log('complete', 'FERTIG', ev.ms!=null?`Abgeschlossen nach ${ev.ms} ms`:'Auftrag abgeschlossen');
      renderAnswer(true);
      speakDone = speakThisRun ? speak(answer) : Promise.resolve();
      break;
    case 'error':
      setState('error', 'FEHLER', ev.message?.slice(0,40) || 'Fehler');
      setTag('err', 'FEHLER');
      log('error', 'FEHLER', ev.message || 'Unbekannter Fehler');
      // show it in the panel too, so a failure isn't a silent empty box
      if (!answer) $('#response').innerHTML =
        `<span style="color:var(--red)">⚠ ${esc(ev.message || 'Auftrag fehlgeschlagen.')}</span>`;
      else renderAnswer(true);
      break;
    case 'note':
      log('note', 'HINWEIS', ev.message || '');
      break;
  }
}

function renderAnswer(finaldone){
  const el = $('#response');
  el.innerHTML = esc(answer) + (finaldone ? '' : '<span class="cur"></span>');
  el.scrollTop = el.scrollHeight;
}

function cleanForSpeech(text){
  return String(text || '')
    .replace(/\x1b\[[0-9;?]*[A-Za-z]/g, '')
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(line => line && !/^(session_id:|session:|duration:|messages:|query:|initializing agent|resume this session|hermes --resume|[-─=]{3,})/i.test(line))
    .join(' ')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[*_#>`]/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

/* ══════════ continuous voice conversation ══════════
   Click VOICE once. From then on: listen → you stop → transcribe → Jarvis
   answers and speaks → it listens again, automatically. No re-clicking between
   turns. Click VOICE again (or press Esc) to end the conversation.

   The mic is deliberately DEAF while Jarvis is thinking or speaking (`suppress`)
   — otherwise it transcribes his own voice through the speakers and talks to
   itself forever. That's why re-arming happens only after he finishes. */
let convo = false, suppress = false;
let recognition = null;
let micStream=null, recorder=null, chunks=[], actx=null, analyser=null, vdata=null;
let vad=null, spoke=false, loudAt=0, turnStart=0;
let floorSum=0, floorN=0, threshold=0.02, peak=0, calibrating=true;
const SILENCE=900, MIN_TURN_MS=350, MAX_TURN_MS=18000, NO_SPEECH_MS=10000;

// ── voice out ──
let muted = false, player = null;
function speak(text){
  return new Promise(resolve => {
    text = cleanForSpeech(text);
    if (muted || !text) return resolve();
    suppress = true;
    const spoken = text.length > 700 ? text.slice(0, 680).replace(/\s+\S*$/,'') + '…' : text;
    if (!RT.tts && RT.browserTts && speechSynth){
      try{
        speechSynth.cancel();
        const u = new SpeechSynthesisUtterance(spoken);
        u.lang = 'de-DE';
        const germanVoice = speechSynth.getVoices().find(v => v.lang.toLowerCase().startsWith('de'));
        if (germanVoice) u.voice = germanVoice;
        u.rate = 0.95; u.pitch = 0.92; u.volume = 1;
        document.body.classList.add('speaking');
        u.onend = u.onerror = () => { document.body.classList.remove('speaking'); resolve(); };
        speechSynth.speak(u);
        return;
      }catch(_){ return resolve(); }
    }
    if (!RT.tts) return resolve();
    fetch('/api/speak', {method:'POST', headers:apiHeaders({'content-type':'application/json'}),
                         body: JSON.stringify({text:spoken})})
      .then(async r => {
        if (!r.ok){
          const e = await r.json().catch(() => ({}));
          throw new Error(e.error || 'HTTP ' + r.status);
        }
        return r.blob();
      })
      .then(blob => {
        const url = URL.createObjectURL(blob);
        if (player) player.pause();
        player = new Audio(url);
        document.body.classList.add('speaking');
        const done = () => { document.body.classList.remove('speaking');
          URL.revokeObjectURL(url); resolve(); };
        player.onended = done; player.onerror = done;
        return player.play();
      })
      .catch(e => { log('error','SPRACHE',`Sprachausgabe fehlgeschlagen: ${e.message || e}`); document.body.classList.remove('speaking'); resolve(); });
  });
}

// ── start / stop the whole conversation ──
async function micToggle(){
  if (convo){ stopConvo(); return; }
  // Prefer ElevenLabs server-side STT when configured. Browser STT is unreliable
  // across Chrome profiles and often fails silently; ElevenLabs receives the
  // actual microphone recording from MediaRecorder and is much more consistent.
  if (RT.stt){
    if (!window.MediaRecorder || !navigator.mediaDevices?.getUserMedia){
      log('error','SPRACHE','Dieser Browser unterstützt keine sichere Mikrofonaufnahme. HTTPS oder localhost prüfen.');
      return;
    }
    try {
      micStream = await navigator.mediaDevices.getUserMedia(
        {audio:{echoCancellation:true, noiseSuppression:true, autoGainControl:true}});
    } catch(e){ log('error','SPRACHE','Mikrofon gesperrt – bitte Browserberechtigung prüfen'); return; }
    actx = new (window.AudioContext||window.webkitAudioContext)();
    await actx.resume();
    analyser = actx.createAnalyser(); analyser.fftSize = 1024;
    actx.createMediaStreamSource(micStream).connect(analyser);
    vdata = new Uint8Array(analyser.fftSize);
    convo = true; suppress = false;
    $('#mic').classList.add('on'); $('#mic').textContent = '● ' + (RT.provider === 'hermes' ? 'Hermes hört zu' : 'ElevenLabs hört zu');
    log('voice','SPRACHE',`${RT.provider} – Sprachdialog geöffnet`);
    beginTurn();
    return;
  }
  if (SpeechRecognition){
    convo = true; suppress = false;
    $('#mic').classList.add('on'); $('#mic').textContent = '● Browser hört zu';
    log('voice','SPRACHE','Browser-Spracherkennung aktiv – höre zu');
    setState('listening','HÖRT ZU','Browser-Spracherkennung aktiv');
    startBrowserRecognition();
    return;
  }
  log('error','SPRACHE','Keine Spracherkennung verfügbar. Nutze einen unterstützten Browser.');
}

function stopConvo(){
  convo = false; suppress = false;
  if (recognition){ try{ recognition.onend = null; recognition.stop(); }catch(_){} recognition=null; }
  if (vad){ clearInterval(vad); vad=null; }
  if (recorder && recorder.state==='recording'){ recorder._cancel=true; try{recorder.stop();}catch(_){} }
  recorder = null;
  if (player){ try{player.pause();}catch(_){} }
  if (speechSynth){ try{speechSynth.cancel();}catch(_){} }
  if (micStream){ micStream.getTracks().forEach(t=>t.stop()); micStream=null; }
  if (actx){ actx.close().catch(()=>{}); actx=null; analyser=null; }
  document.body.classList.remove('speaking');
  $('#mic').classList.remove('on'); $('#mic').textContent = '◉ Sprachdialog';
  log('voice','SPRACHE','Sprachdialog beendet');
  setState('', 'BEREIT', 'warte auf Eingabe');
}

// ── browser speech turn ──
function startBrowserRecognition(){
  if (!convo || suppress || !SpeechRecognition) return;
  recognition = new SpeechRecognition();
  recognition.lang = 'de-DE';
  recognition.interimResults = true;
  recognition.continuous = false;
  let finalText = '';
  recognition.onresult = e => {
    let interim = '';
    for (let i=e.resultIndex; i<e.results.length; i++){
      const txt = e.results[i][0].transcript;
      if (e.results[i].isFinal) finalText += txt;
      else interim += txt;
    }
    const shown = (finalText || interim || '').trim();
    if (shown) $('#strun').textContent = 'ERKANNT: ' + shown.slice(0,42);
  };
  recognition.onerror = e => {
    log('error','SPRACHE',`Browser-Spracherkennung: ${e.error || 'Fehler'}`);
    if (['not-allowed','service-not-allowed','audio-capture'].includes(e.error)){
      stopConvo();
      setState('error','FEHLER','Mikrofon oder Spracherkennung nicht verfügbar');
    }
  };
  recognition.onend = async () => {
    const text = finalText.trim();
    if (!convo) return;
    if (!text){ if (!suppress) setTimeout(startBrowserRecognition, 250); return; }
    log('voice','SPRACHE',`Im Browser erkannt: "${text}"`);
    const armed = $('#input').dataset.cmd || '';
    const full = (armed ? armed + ' ' : '') + text;
    $('#input').value = ''; disarm();
    log('send','GESENDET',`Gesprochene Anweisung: ${full}`);
    await transmit(full);
    suppress = false;
    if (convo) setTimeout(startBrowserRecognition, 350);
  };
  setState('listening','HÖRT ZU','Browser-Spracherkennung aktiv');
  try{ recognition.start(); }catch(e){ log('error','SPRACHE','Spracherkennung konnte nicht gestartet werden'); }
}

// ── one server-side ElevenLabs listening turn ──
function beginTurn(){
  if (!convo || suppress || !micStream) return;
  chunks = []; spoke = false; peak = 0;
  floorSum = 0; floorN = 0; calibrating = true; threshold = 0.02;
  recorder = new MediaRecorder(micStream, pickMime());
  recorder.ondataavailable = e => { if (e.data?.size) chunks.push(e.data); };
  recorder.onstop = ship;
  recorder.start(250);                          // timeslice → data flows reliably
  turnStart = loudAt = performance.now();
  setState('listening','HÖRT ZU','höre zu…');
  if (!vad) vad = setInterval(vtick, 40);
}

function meter(rms){
  // live input bar in the reactor subtitle, so you can SEE it hearing you
  const n = Math.max(0, Math.min(14, Math.round(rms * 90)));
  $('#strun').textContent = 'MIKROFON ' + '▮'.repeat(n) + '▯'.repeat(14 - n);
}

function endTurn(reason){
  log('voice','SPRACHE',`${reason} · Spitzenpegel ${peak.toFixed(3)} · Schwelle ${threshold.toFixed(3)}`);
  try { recorder.stop(); } catch(_){}           // → ship()
}

function pickMime(){
  for (const m of ['audio/webm;codecs=opus','audio/webm','audio/mp4'])
    if (window.MediaRecorder?.isTypeSupported?.(m)) return {mimeType:m};
  return undefined;
}

function vtick(){
  if (!analyser || suppress || !recorder || recorder.state!=='recording') return;
  analyser.getByteTimeDomainData(vdata);
  let s=0; for (let i=0;i<vdata.length;i++){ const v=(vdata[i]-128)/128; s+=v*v; }
  const rms = Math.sqrt(s/vdata.length);
  const t = performance.now();
  peak = Math.max(peak, rms);
  meter(rms);

  // first 300ms: measure the room's noise floor, set a threshold just above it
  if (calibrating){
    floorSum += rms; floorN++;
    if (t - turnStart > 300){
      const floor = floorSum / Math.max(1, floorN);
      threshold = Math.max(0.006, floor * 1.6 + 0.003);
      calibrating = false;
    }
    return;
  }

  if (rms > threshold){
    loudAt = t;
    if (!spoke){ spoke = true; log('voice','SPRACHE','Sprache erkannt'); }
  } else if (spoke && t - loudAt > SILENCE){
    return endTurn('Sprechpause');
  }

  // failsafes so it can never hang: cap the length, re-listen if no speech at all
  if (t - turnStart > MAX_TURN_MS) return endTurn('maximale Aufnahmelänge');
  if (!spoke && t - turnStart > NO_SPEECH_MS) return endTurn('keine Sprache');
}

async function ship(){
  const cancel = recorder?._cancel;
  const blob = new Blob(chunks, {type: recorder?.mimeType || 'audio/webm'}); chunks=[];
  if (cancel){ return; }
  // no speech heard, too short, or too small — just listen again, don't ship ambient noise
  if (!spoke || blob.size < 1400 || performance.now()-turnStart < MIN_TURN_MS){
    if (convo && !suppress) beginTurn();
    return;
  }
  setState('running','ERKENNT SPRACHE','…');
  log('voice','SPRACHE',`Übertrage ${Math.round(blob.size/1024)} KB zur Spracherkennung`);
  const t0 = performance.now();
  try {
    const response = await fetch('/api/listen', {method:'POST',
      headers:apiHeaders({'content-type':blob.type||'audio/webm'}), body:blob});
    const r = await response.json();
    if (!response.ok) throw new Error(r.error || `HTTP ${response.status}`);
    const text = (r.text||'').trim();
    const ms = Math.round(performance.now() - t0);
    if (!text){
      log('voice','SPRACHE','Keine Sprache erkannt');
      if (convo) beginTurn(); else setState('','BEREIT','Nichts gehört');
      return;
    }
    log('voice','SPRACHE',`Transkribiert durch ${RT.provider} in ${ms} ms: "${text}"`);
    const armed = $('#input').dataset.cmd || '';
    const full = (armed ? armed + ' ' : '') + text;
    $('#input').value = ''; disarm();
    log('send','SEND',`auto-sent voice: ${full}`);
    await transmit(full);                       // runs, then speaks; both with mic deaf
    // turn's done — hand the floor back and listen again
    suppress = false;
    if (convo) beginTurn();
  } catch(e){
    log('error','SPRACHE',`Transkription fehlgeschlagen: ${e.message || e}`);
    stopConvo();
    setState('error','FEHLER','Spracherkennung fehlgeschlagen');
  }
}

// ══════════ command matrix ══════════
function disarm(){
  document.querySelectorAll('.cmd').forEach(c=>c.classList.remove('armed'));
  $('#input').dataset.cmd = '';
}
const PAYLOAD_COMMANDS = new Set(['/ziel','/browser','/hintergrund','/auftrag','/tonfall']);
$('#cmds').addEventListener('click', e => {
  const b = e.target.closest('.cmd'); if (!b) return;
  const cmd = b.dataset.cmd;
  if (running){
    log('note','BESETZT',`${cmd} wurde nicht gesendet – Jarvis arbeitet noch.`);
    return;
  }

  // Every matrix button executes its base command immediately. Commands that
  // accept an argument remain armed afterwards so the next typed or spoken
  // payload is sent as `/command payload`.
  disarm();
  if (PAYLOAD_COMMANDS.has(cmd)){
    b.classList.add('armed');
    $('#input').dataset.cmd = cmd;
    $('#input').focus();
    $('#tip').textContent = `${TIPS[cmd] || cmd} Der Befehl bleibt für die nächste Eingabe aktiviert.`;
  } else {
    $('#tip').textContent = defaultTip;
  }
  log('command', 'BEFEHL', `Starte ${cmd} über Hermes`);
  transmit(cmd, {speak: !['/werkzeuge','/befehle'].includes(cmd)});
});
const TIPS = {
  '/neu': 'Ein neues Hermes-Gespräch beginnen.',
  '/ziel': 'Ein dauerhaftes Ziel eingeben oder mit /ziel status ansehen.',
  '/werkzeuge': 'Aktivierte Werkzeuge im Hermes-Profil anzeigen.',
  '/werkzeugsaetze': 'Aktive Werkzeugsätze und externe Verbindungen anzeigen.',
  '/browser': 'Einen Auftrag für den Browser formulieren.',
  '/hintergrund': 'Einen Hintergrundauftrag formulieren.',
  '/auftrag': 'Eine Aufgabe ergänzen oder die Auftragsliste ansehen.',
  '/tonfall': 'Den gewünschten Tonfall beschreiben.',
  '/aufgaben': 'Auftragsliste verwalten.',
  '/befehle': 'Alle verfügbaren Kurzbefehle anzeigen.'
};
let defaultTip = '';

// ══════════ controls ══════════
function sendFromInput(){
  const armed = $('#input').dataset.cmd || '';
  const raw = $('#input').value.trim();
  if (!raw && !armed) return;
  const full = (armed && !raw.startsWith('/')) ? `${armed} ${raw}` : (raw || armed);
  $('#input').value = ''; disarm(); $('#tip').textContent = defaultTip;
  log('send','GESENDET',`Anweisung: ${full}`);
  transmit(full);
}
$('#run').onclick = sendFromInput;
$('#mic').onclick = micToggle;
$('#showCommands').onclick = () => transmit('/befehle', {speak:false});
$('#missionBtn').onclick = () => transmit('/auftrag');
$('#clearBtn').onclick = () => { answer=''; $('#response').innerHTML='<span class="rplaceholder">Anzeige geleert. Jarvis ist bereit.</span>'; log('note','LEEREN','Antwortanzeige geleert'); };
document.querySelectorAll('[data-quick]').forEach(b => b.onclick = () =>
  transmit(b.dataset.quick, {speak:false}));
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  if (running && activeController){
    fetch('/api/cancel', {method:'POST', headers:apiHeaders({'content-type':'application/json'}), body:'{}'}).catch(()=>{});
    activeController.abort();
    return;
  }
  if (convo) stopConvo();
});
$('#mute').onclick = () => {
  muted = !muted; const b=$('#mute');
  b.textContent = muted?'🔇':'🔊'; b.classList.toggle('on',!muted); b.classList.toggle('off',muted);
  if (muted && player) player.pause();
  if (muted && speechSynth) speechSynth.cancel();
};
$('#input').addEventListener('keydown', e => {
  if (e.key==='Enter' && (e.metaKey||e.ctrlKey)){ e.preventDefault(); sendFromInput(); }
});

// ══════════ system panel ══════════
function sys(id, val, cls){
  const el = $('#sy-' + id); if (!el) return;
  el.textContent = val; if (cls != null) el.className = cls;
}
// live clock in the system panel
setInterval(() => sys('clock', now()), 1000);

// poll for finished /background missions and report them when they land
setInterval(async () => {
  try {
    const j = await fetch('/api/jobs', {headers:apiHeaders()}).then(r => r.json());
    for (const d of (j.done || [])){
      log('complete','AUFTRAG', `${d.mission} → ${(d.result||'').slice(0,200)}`);
      if (!running) speak(`Auftrag abgeschlossen. ${(d.result||'').slice(0,300)}`);
    }
  } catch(_){}
}, 4000);

// ══════════ boot ══════════
(async () => {
  defaultTip = $('#tip').textContent;
  try {
    const s = await fetch('/api/status').then(r=>r.json());
    RT.provider = s.stt || 'browser';
    RT.tts = ['hermes','elevenlabs'].includes(s.tts);
    RT.stt = ['hermes','elevenlabs'].includes(s.stt);
    RT.browserStt = !!SpeechRecognition; RT.browserTts = !!speechSynth;

    const port = location.port || '8730';
    sys('gw', `Erreichbar · :${port}`, 'ok');
    sys('brain', s.runtime === 'hermes' ? 'Hermes Agent' : 'Hermes nicht erreichbar', s.runtime === 'hermes' ? 'ok' : 'warn');
    const label = p => p === 'hermes' ? 'Hermes' : p === 'elevenlabs' ? 'ElevenLabs' : 'Browser';
    sys('voice', `${label(s.stt)} (Eingabe) / ${label(s.tts)} (Ausgabe)`, (RT.browserStt||RT.stt) ? '' : 'warn');
    sys('profile', s.profile || 'Standard');
    sys('runtime', s.runtime === 'hermes' ? 'Hermes aktiv' : 'Hermes nicht verbunden', s.runtime === 'hermes' ? 'ok' : 'warn');
    sys('clock', now());
    $('#top-gw').textContent = `Verbindung: erreichbar (${location.origin})`;
    $('#top-profile').textContent = 'Profil: ' + (s.profile || 'Standard');
    $('#top-voice').textContent = `Sprache: ${label(s.stt)} (Eingabe) / ${label(s.tts)} (Ausgabe)`;
    const tools = (s.tools || []).slice(0, 12);
    $('#toolsList').innerHTML = tools.length ? tools.map(t => `<span class="chip">${esc(t)}</span>`).join('') : '<span class="chip ghost">Hermes-Werkzeuge nicht abrufbar – HERMES_CMD prüfen</span>';

    log('status', 'START',
        `Verbindung hergestellt · KI: ${s.runtime} · Profil: ${s.profile || 'Standard'} · Berechtigung: ${s.permission}`);
    log('voice', 'SPRACHE', `Sprachkanal bereit – Eingabe: ${s.stt}, Ausgabe: ${s.tts}`);
    $('#mic').textContent = s.stt === 'hermes' ? '◉ Hermes-Sprachdialog' : (s.stt === 'elevenlabs' ? '◉ ElevenLabs-Sprachdialog' : '◉ Browser-Sprachdialog');
    setState('', 'BEREIT', 'warte auf Eingabe');
  } catch(e){
    sys('gw','offline','warn');
    log('error','STATUS',`Server nicht erreichbar: ${e.message || e}`);
  }
})();
