const $ = id => document.getElementById(id);
let settings = {}, busy = false, connected = false, pendingCapture = null, previewEnabled = true, lastAudit = null, seriesRunning = false;
let settingPending = false, capturedForTransfer = null;
const settingFeedback = new Map();
let messageTimer, connectionMode = null, connectionOnline = false, lastHeartbeat = 0, lastConnection = null, connectionPolling = false, statusPolling = false, imageLoading = false;
function message(text) { $('message').textContent = text; $('message').hidden = false; clearTimeout(messageTimer); messageTimer = setTimeout(() => $('message').hidden = true, 12000); }
async function api(path, method = 'GET', body) {
  const response = await fetch('/api/' + path, {signal:AbortSignal.timeout((path === 'captures' || path === 'save-local') ? 150000 : path === 'connection' ? 3500 : 15000), method, headers: body === undefined ? {} : {'Content-Type':'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data;
}
function newId() { $('capture-id').value = 'capture-' + crypto.randomUUID(); pendingCapture = null; }
function renderSettings(data) {
  const drafts = new Map();
  for (const [name, spec] of Object.entries(settings)) {
    const input = $('setting-' + name);
    if (input && input.value !== String(name === 'ExposureTime' ? spec.value / 1000 : spec.value)) drafts.set(name, input.value);
  }
  const expanded = new Map([...document.querySelectorAll('.control-group')].map(group => [group.querySelector('summary').textContent, group.open]));
  settings = data; $('settings').replaceChildren();
  const groups = {};
  function groupFor(name) {
    if (/^(ExposureTime|Gain|ExposureAuto|GainAuto)$/.test(name)) return 'Brightness';
    if (/Exposure|Gain|BlackLevel|Balance/.test(name)) return 'Advanced exposure & color';
    if (/Width|Height|Offset|Reverse|Binning|Decimation|Pixel|BitDepth|Sensor/.test(name)) return 'Sensor format & geometry';
    if (/Device|Acquisition/.test(name)) return 'Transport & device';
    return 'Camera image processing';
  }
  for (const [name, cameraSpec] of Object.entries(data)) {
    const scale = name === 'ExposureTime' ? 1000 : 1;
    const spec = {...cameraSpec};
    if (scale !== 1) {
      spec.unit = 'ms';
      for (const field of ['value', 'min', 'max', 'step']) {
        if (typeof spec[field] === 'number') spec[field] /= scale;
      }
    }
    const groupName = groupFor(name);
    if (!groups[groupName]) { const group = document.createElement('details'); group.className = 'control-group'; group.open = expanded.get(groupName) ?? (groupName === 'Brightness'); const summary = document.createElement('summary'); summary.textContent = groupName; group.append(summary); groups[groupName] = group; $('settings').append(group); }
    const section = document.createElement('div'); section.className = 'setting';
    const label = document.createElement('label'); label.textContent = ({ExposureTime:'Exposure time',Gain:'Gain',ExposureAuto:'Automatic exposure',GainAuto:'Automatic gain'}[name] || name) + (spec.unit ? ' (' + spec.unit + ')' : ''); label.htmlFor = 'setting-' + name;
    const row = document.createElement('div'); row.className = 'setting-row';
    let input;
    if (spec.kind === 'enum' || spec.kind === 'bool') {
      input = document.createElement('select');
      for (const choice of spec.kind === 'bool' ? [false, true] : spec.choices) { const option = document.createElement('option'); option.value = String(choice); option.textContent = String(choice); input.append(option); }
    } else { input = document.createElement('input'); input.type = 'number'; input.min = spec.min; input.max = spec.max; input.step = spec.step || 'any'; }
    input.id = 'setting-' + name; input.value = drafts.get(name) ?? String(spec.value); input.disabled = !spec.writable || settingPending;
    const apply = document.createElement('button'); apply.textContent = 'Apply'; apply.disabled = !spec.writable;
    const feedback = document.createElement('small'); feedback.className = 'setting-feedback';
    feedback.setAttribute('role', 'status'); feedback.setAttribute('aria-live', 'polite');
    feedback.textContent = settingFeedback.get(name) || '';
    apply.disabled = !spec.writable || settingPending;
    apply.onclick = async () => {
      if (settingPending) return;
      if (!input.reportValidity() || input.value === '') return;
      const value = spec.kind === 'bool' ? input.value === 'true' : spec.kind === 'enum' ? input.value : Number(input.value) * scale;
      settingPending = true;
      for (const control of document.querySelectorAll('#settings input, #settings select, #settings button')) control.disabled = true;
      $('refresh').disabled = true; $('import').disabled = true;
      section.setAttribute('aria-busy', 'true'); apply.classList.add('applying'); apply.textContent = 'Applying…';
      feedback.textContent = 'Sending to camera…';
      const started = performance.now();
      const slow = setTimeout(() => { feedback.textContent = 'Still working — waiting for the current exposure or connection. Do not resend yet.'; }, 2000);
      let readback;
      try {
        await api('settings/' + name, 'PUT', {value});
        clearTimeout(slow); apply.textContent = 'Checking…'; feedback.textContent = 'Reading the value back from the camera…';
        // Retry reads only. Never repeat a write whose response might have been lost.
        for (let attempt = 0; attempt < 3; attempt++) {
          try { readback = await api('settings'); if (readback[name]?.value !== undefined) break; }
          catch (error) { if (attempt === 2) throw error; }
          await new Promise(resolve => setTimeout(resolve, 400));
        }
        if (readback?.[name]?.value === undefined) throw new Error('Camera did not return this setting');
        const actual = readback[name].value;
        const matches = typeof value === 'number' ? Math.abs(actual - value) <= Math.max(1e-6, Math.abs(value) * 1e-6) : actual === value;
        const shown = typeof actual === 'number' ? Number((actual / scale).toPrecision(8)) : actual;
        settingFeedback.set(name, `${matches ? 'Confirmed' : 'Camera returned a different value'}: ${shown}${spec.unit ? ' ' + spec.unit : ''} · ${((performance.now()-started)/1000).toFixed(1)} s`);
        input.value = String(spec.value); // Replace this submitted draft with confirmed readback.
      } catch (error) {
        settingFeedback.set(name, 'Not confirmed: ' + error.message + '. The setting may have changed; refresh to check before retrying.');
      } finally {
        clearTimeout(slow); settingPending = false; $('refresh').disabled = false; $('import').disabled = false;
        renderSettings(readback || settings);
      }
    };
    row.append(input, apply); section.append(label, row);
    const hint = document.createElement('small'); hint.textContent = (spec.writable ? '' : 'Read-only · ') + (spec.min !== undefined ? `${spec.min} – ${spec.max}${spec.step ? ' · step ' + spec.step : ''}` : ''); section.append(hint, feedback); groups[groupName].append(section);
  }
}
async function refreshSettings() { if (settingPending) return; try { const data = await api('settings'); if (!settingPending) renderSettings(data); } catch (e) { message(e.message); } }
async function status() { if(statusPolling || !connectionOnline) return; statusPolling=true; try {
  const data = await api('status'); const wasConnected = connected; connected = data.connected;
  $('camera-health').textContent = connected ? 'Camera: ready' : 'Camera: unavailable';
  $('badge').textContent = connected ? (data.camera.simulated ? 'Simulation' : 'Camera connected') : 'Camera disconnected';
  $('badge').className = connected ? 'ready' : '';
  $('camera').textContent = data.camera ? `${data.camera.model} · ${data.camera.serial}` : data.error || 'No camera';
  $('demo').hidden = !data.camera?.simulated;
  $('storage').textContent = `${(data.free_bytes / 1024**3).toFixed(1)} GiB free on capture storage`;
  seriesRunning = data.series.state === 'running';
  previewEnabled = data.preview_enabled;
  $('pause-preview').textContent = previewEnabled ? 'Pause preview' : 'Resume preview';
  $('capture').disabled = !connectionOnline || !connected || busy || seriesRunning;
  $('start-series').disabled = !connected || seriesRunning;
  $('cancel-series').disabled = !seriesRunning;
  $('series-progress').max = data.series.total || 1; $('series-progress').value = data.series.completed || 0;
  $('series-status').textContent = data.series.state === 'idle' ? 'No series started.' : `${data.series.series_id}: ${data.series.state}\n${data.series.completed} / ${data.series.total} captures${data.series.error ? '\n' + data.series.error : ''}`;
  $('preview').style.opacity = connected ? '1' : '.25'; $('preview-placeholder').hidden=connected;
  if (connected && !wasConnected) { await refreshSettings(); await loadSetup(); }
} catch (e) { connected = false; $('badge').textContent = 'Camera status unavailable'; disableCaptureControls(); } finally {statusPolling=false;} }
$('reconnect').onclick = async () => { try { await api('connect', 'POST'); await status(); await refreshSettings(); } catch(e) { message(e.message); } };
$('refresh').onclick = refreshSettings;
$('new-id').onclick = newId;
$('capture').onclick = async () => {
  busy = true; $('capture').disabled = true; $('capture').classList.add('applying'); $('capture').textContent = capturedForTransfer ? 'Transferring…' : 'Capturing…';
  try {
    const capture_id = $('capture-id').value;
    if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/.test(capture_id)) throw new Error('Use letters, digits, underscores and hyphens for the capture ID.');
    const context = JSON.parse($('context').value);
    if (!context || Array.isArray(context) || typeof context !== 'object') throw new Error('Metadata must be a JSON object.');
    const destination = $('save-folder').value.trim();
    if (connectionMode === 'desktop' && !destination.startsWith('/')) throw new Error('Enter an absolute desktop folder path.');
    pendingCapture = pendingCapture || {capture_id, context};
    $('save-folder').disabled = true;
    try { localStorage.setItem('capture-destination', destination); } catch (_) {}
    $('capture-id').disabled = $('context').disabled = $('new-id').disabled = true;
    const result = capturedForTransfer || await api('captures', 'POST', pendingCapture);
    capturedForTransfer = result;
    let saved;
    if (connectionMode === 'desktop') {
      $('capture').textContent = 'Transferring…';
      $('result').textContent = 'Saved on Pi. Transferring to desktop and verifying files…';
      saved = await api('save-local', 'POST', {capture_id: result.capture_id, destination});
    }
    $('result').textContent = `${saved ? 'Saved and verified' : result.replayed ? 'Already saved on Pi' : 'Saved on Pi'}: ${result.capture_id}\n${saved ? saved.path + '\n' : ''}${result.shape.join(' × ')} · ${result.dtype} · ${result.pixel_format}\n${Object.keys(result.files).join(' + ')} + metadata.json\n${result.camera.simulated ? 'SIMULATED DATA — for development only' : 'Camera output in DN — not yet absolute radiance'}`;
    capturedForTransfer = null; pendingCapture = null; $('save-folder').disabled = false; newId(); $('capture-id').disabled = $('context').disabled = $('new-id').disabled = false;
  } catch (e) { if(pendingCapture) $('result').textContent=capturedForTransfer ? 'Saved on Pi; desktop transfer not confirmed. Retry transfer to finish without taking another image.' : 'Save not confirmed. Reconnect, then retry this same capture. The Pi may already have saved it.'; message(e.message + ' — retry the same ID if the result is uncertain.'); }
  finally { busy = false; $('capture').classList.remove('applying'); if (!pendingCapture || capturedForTransfer) $('save-folder').disabled = false; $('capture').textContent = capturedForTransfer ? 'Retry transfer' : pendingCapture ? 'Retry this capture' : 'Save capture'; $('capture').disabled = !connectionOnline || !connected || seriesRunning; }
};
$('export').onclick = () => { const data = {schema_version:1, settings:Object.fromEntries(Object.entries(settings).filter(([,s]) => s.writable).map(([key,s]) => [key,s.value]))}; const link = document.createElement('a'); const url = URL.createObjectURL(new Blob([JSON.stringify(data,null,2)], {type:'application/json'})); link.href=url; link.download='camera-settings.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); };
$('import').onchange = async event => { try {
  const file = event.target.files[0]; if (!file) return; const preset = JSON.parse(await file.text());
  if (preset.schema_version !== 1 || !preset.settings || typeof preset.settings !== 'object' || Array.isArray(preset.settings)) throw new Error('Invalid settings file');
  for (const [key,value] of Object.entries(preset.settings)) { renderSettings(await api('settings/' + key, 'PUT', {value})); }
  message('Settings imported');
} catch(e) { message('Import stopped; earlier settings may have applied. ' + e.message); await refreshSettings(); } finally { event.target.value=''; } };
function downloadJson(value, name) { const link = document.createElement('a'); const url = URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})); link.href=url; link.download=name; link.click(); setTimeout(() => URL.revokeObjectURL(url),1000); }
async function readAudit() { lastAudit = null; try {
  lastAudit = await api('measurement-state');
  $('audit-checks').replaceChildren();
  const checks = lastAudit.audit.checks;
  $('audit-summary').textContent = `${checks.filter(c=>c.status==='review').length} controls to review · ${checks.filter(c=>c.status==='unknown').length} unknown · Raw sensor status unverified`;
  for (const check of checks) { const row=document.createElement('div'); row.className='audit-row'; const name=document.createElement('strong'); name.textContent=check.feature; const state=document.createElement('span'); state.className='audit-status '+check.status; state.textContent=check.status==='observed_neutral' ? 'Observed neutral' : check.status==='review' ? 'Review: '+String(check.observed) : 'Unknown'; const note=document.createElement('small'); note.textContent=check.note; row.append(name,state,note); $('audit-checks').append(row); }
} catch(e) { message(e.message); } }
$('audit-refresh').onclick=readAudit;
$('download-audit').onclick=async()=>{ await readAudit(); if(lastAudit) downloadJson(lastAudit,'camera-state.json'); };
$('enable-chunks').onclick=async()=>{ try { const r=await api('chunks/enable','POST'); message(JSON.stringify(r)); await readAudit(); } catch(e){message(e.message);} };
$('pause-preview').onclick=async()=>{ try { await api('preview','PUT',{enabled:!previewEnabled}); await status(); } catch(e){message(e.message);} };
function refreshImage() {
 if(!connectionOnline || !connected || imageLoading) return;
 imageLoading=true;
 const raw=$('view-mode').value==='raw';
 $('preview').src=raw ? `/api/raw-preview.jpg?black=${encodeURIComponent($('window-black').value)}&white=${encodeURIComponent($('window-white').value)}&t=${Date.now()}` : '/api/preview.jpg?t='+Date.now();
}
$('preview').onload=()=>{imageLoading=false;};
$('preview').onerror=()=>{imageLoading=false;$('preview-health').textContent='Live image: waiting';};
$('view-mode').onchange=refreshImage;
$('window-black').onchange=refreshImage; $('window-white').onchange=refreshImage;
setInterval(()=>{if(previewEnabled)refreshImage();},1000);
$('inspect-raw').onclick=async()=>{ try {
  const r=await api(`raw?x=${encodeURIComponent($('raw-x').value)}&y=${encodeURIComponent($('raw-y').value)}&width=8&height=8`);
  $('raw-values').textContent=`Latest acquired frame: ${r.frame} · ${r.pixel_format} · DN\n`+r.values.map(row=>row.map(v=>String(v).padStart(5)).join(' ')).join('\n');
  const s=r.statistics; $('raw-summary').textContent=`Full array ${s.shape.join(' × ')} · min ${s.min} · max ${s.max} · mean ${s.mean.toFixed(3)} DN · zero ${(100*s.zero_fraction).toFixed(3)}% · at code maximum ${s.at_or_above_code_max_fraction===undefined?'unknown':(100*s.at_or_above_code_max_fraction).toFixed(3)+'%'} · physical saturation not measured`;
  const canvas=$('histogram'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);
  if(s.histogram){const counts=s.histogram.counts,max=Math.max(...counts,1); ctx.fillStyle='#92d9c3';counts.forEach((n,i)=>ctx.fillRect(i*canvas.width/counts.length,canvas.height-20-n/max*(canvas.height-30),canvas.width/counts.length-1,n/max*(canvas.height-30)));ctx.fillStyle='#9aaeb8';ctx.font='12px system-ui';ctx.fillText('0 DN',0,canvas.height-3);ctx.fillText(String(s.nominal_code_max)+' DN',canvas.width-75,canvas.height-3);}
}catch(e){message(e.message);} };
const setupFields={session_id:'setup-session',lens_id:'setup-lens',aperture_f_number:'setup-aperture',focus_distance_m:'setup-focus',filters:'setup-filters',calibration_reference_ids:'setup-calibration',notes:'setup-notes'};
async function loadSetup(){try{const data=await api('setup');for(const [key,id] of Object.entries(setupFields))$(id).value=data[key]??'';$('setup-state').textContent=Object.keys(data).length?'Loaded recorded setup.':'No setup recorded; unknown fields will stay unknown.';}catch(e){message(e.message);}}
$('save-setup').onclick=async()=>{try{const data={};for(const [key,id] of Object.entries(setupFields)){const value=$(id).value.trim();data[key]=value===''?null:$(id).type==='number'?Number(value):value;}data.source='operator-entered, not independently verified';await api('setup','PUT',data);$('setup-state').textContent='Saved. Included in subsequent capture metadata.';}catch(e){message(e.message);}};
$('start-series').onclick=async()=>{try{
 const plan={series_id:$('series-id').value,kind:$('series-kind').value,exposures_us:$('series-exposures').value.split(',').map(v=>Number(v.trim()) * 1000),repeats:Number($('series-repeats').value),settle_frames:Number($('series-settle').value),dark_occlusion_confirmed:$('dark-confirm').checked,context:JSON.parse($('context').value)};
 await api('series','POST',plan);await status();
}catch(e){message(e.message);}};
$('cancel-series').onclick=async()=>{try{await api('series/cancel','POST');message('Stop requested. The current exposure and save will finish.');}catch(e){message(e.message);}};
$('series-id').value='series-'+crypto.randomUUID().slice(0,8);
function disableCaptureControls(){
 $('capture').disabled=$('start-series').disabled=$('cancel-series').disabled=true;
 $('preview').style.opacity='.3';
}
function paintConnection(){
 const stale=lastHeartbeat && performance.now()-lastHeartbeat>6000;
 const online=Boolean(lastConnection?.state==='online' && !stale);
 connectionOnline=online;
 const state=stale?'reconnecting':lastConnection?.state || 'connecting';
 $('connection-dot').className='connection-dot '+(online?'online':state);
 $('connection-title').textContent=online?(connectionMode==='direct'?'Capture service connected':'Raspberry Pi connected'):state==='disconnected'?'Raspberry Pi disconnected':state==='service_unavailable'?'Pi connected · camera service stopped':state==='authentication_failed'?'SSH sign-in needs attention':'Connecting to Raspberry Pi…';
 $('connection-message').textContent=stale?'No recent reply. Retrying automatically.':lastConnection?.message || 'Waiting for a reply.';
 const age=lastConnection?.last_seen_seconds;
 $('heartbeat-age').textContent=online?`Heartbeat received${lastConnection.latency_ms===null?'':' · '+lastConnection.latency_ms+' ms'}`:age===null || age===undefined?'No heartbeat yet':`Last reply ${Math.floor(age+(performance.now()-lastHeartbeat)/1000)}s ago`;
 $('connection-warning').hidden=online || state==='disconnected' || !lastConnection?.pi;
 $('disconnect-pi').disabled=state==='disconnected';
 $('connect-pi').textContent=online?'Reconnect':'Connect';
 if(!online){$('badge').textContent='Camera offline';$('preview-placeholder').hidden=false;connected=false; disableCaptureControls(); $('camera-health').textContent='Camera: waiting for Pi';$('preview-health').textContent='Live image: offline';}
 else {
 const pi=lastConnection.pi;
 const imageAge=pi?.preview_updated_utc_ns ? (pi.utc_ns-pi.preview_updated_utc_ns)/1e9 : null;
 $('preview-health').textContent=!previewEnabled?'Live image: paused':imageAge===null?'Live image: waiting':imageAge>15?'Live image: waiting for a fresh frame':'Live image: receiving';
 }
}
async function checkConnection(){
 if(connectionPolling) return; connectionPolling=true;
 try{
 const data=await api('connection'); lastHeartbeat=performance.now(); lastConnection=data;
 if(connectionMode===null){connectionMode=data.mode;
 if (connectionMode === 'desktop') {
   $('save-location').hidden = false;
   try { $('save-folder').value = localStorage.getItem('capture-destination') || ''; } catch (_) {}
   if (!$('save-folder').value) api('save-location').then(value => { if (!$('save-folder').value) $('save-folder').value = value.destination; }).catch(error => message(error.message));
 }
 $('connection-actions').hidden=data.mode!=='desktop'; if(data.target){$('pi-address').value=data.target.address;$('pi-username').value=data.target.username;}}
 paintConnection(); if(connectionOnline) void status();
 }catch(e){connectionOnline=false; lastConnection={...lastConnection,state:'reconnecting',message:'Dashboard connection interrupted. Checking again…'};paintConnection();}
 finally{connectionPolling=false;}
}
$('connect-pi').onclick=async()=>{try{lastConnection=await api('connection','POST',{address:$('pi-address').value.trim(),username:$('pi-username').value.trim()});paintConnection();checkConnection();}catch(e){message(e.message);}};
$('disconnect-pi').onclick=async()=>{try{lastConnection=await api('connection','DELETE');paintConnection();}catch(e){message(e.message);}};
for(const id of ['measurement','processing'])document.querySelector(`a[href="#${id}"]`).onclick=()=>{$(id).open=true;};
newId(); checkConnection(); setInterval(checkConnection,2000); setInterval(paintConnection,1000);
