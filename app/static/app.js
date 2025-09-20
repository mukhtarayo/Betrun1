async function postJSON(url, data){
  const res = await fetch(url, {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify(data)
  });
  if(!res.ok){
    const txt = await res.text().catch(()=> '');
    throw new Error(`Request failed ${res.status}: ${txt}`);
  }
  return await res.json();
}
async function getJSON(url){
  const res = await fetch(url);
  if(!res.ok){
    const txt = await res.text().catch(()=> '');
    throw new Error(`GET failed ${res.status}: ${txt}`);
  }
  return await res.json();
}
function el(id){ return document.getElementById(id); }

function tableFromRows(headers, rows){
  let h = '<table class="table"><thead><tr>' + headers.map(x=>`<th>${x}</th>`).join('') + '</tr></thead><tbody>';
  for (const r of rows){ h += '<tr>' + r.map(c=>`<td>${c}</td>`).join('') + '</tr>'; }
  h += '</tbody></table>'; return h;
}
function tableFromKeyMap(title, m){
  if(!m) return '';
  const rows = Object.keys(m).map(k=>[k, m[k]]);
  return `<h4>${title}</h4>${tableFromRows(['Key','Value'], rows)}`;
}
function flattenIfNeeded(v){
  const out = {};
  for (const k in v){
    if (v && typeof v[k]==='object' && !Array.isArray(v[k])){
      for (const kk in v[k]) out[`${k} ${kk}`] = v[k][kk];
    } else {
      out[k] = v[k];
    }
  }
  return out;
}
function selectedMarkets(){
  return Array.from(document.querySelectorAll('.mk:checked')).map(x=>x.value);
}

/* ---------------- Get Matches (with odds) ---------------- */
async function fetchMatches(){
  const leagueId = parseInt(el('leagueId').value);
  const season = parseInt(el('season').value);
  const date = el('fxDate').value.trim() || undefined;

  if(!leagueId || !season){
    el('matchesBox').innerHTML = `<span class="muted">Enter league_id & season.</span>`;
    return;
  }
  el('matchesBox').innerHTML = `<span class="muted">Loading…</span>`;
  try{
    const data = await getJSON(`/api/matches?league_id=${leagueId}&season=${season}${date?`&date=${encodeURIComponent(date)}`:''}`);
    if(!data.items || !data.items.length){
      el('matchesBox').innerHTML = `<span class="muted">No fixtures found.</span>`;
      return;
    }
    const rows = data.items.map((it, idx)=>{
      const o = it.odds || {};
      const o1 = o["1"]? Number(o["1"]).toFixed(2): '—';
      const ox = o["X"]? Number(o["X"]).toFixed(2): '—';
      const o2 = o["2"]? Number(o["2"]).toFixed(2): '—';
      const btn = `<button class="ghost" data-idx="${idx}" data-fixture="${it.fixture_id||''}" data-home="${it.home||''}" data-away="${it.away||''}" data-o1="${o["1"]||''}" data-ox="${o["X"]||''}" data-o2="${o["2"]||''}">Analyze</button>`;
      return [
        it.utc ? new Date(it.utc).toLocaleString() : '—',
        it.home || '—',
        it.away || '—',
        o1, ox, o2,
        btn
      ];
    });
    el('matchesBox').innerHTML = tableFromRows(
      ['UTC Time','Home','Away','Odds 1','Odds X','Odds 2',''],
      rows
    );
    // Wire buttons
    el('matchesBox').querySelectorAll('button[data-idx]').forEach(btn=>{
      btn.addEventListener('click', ()=>{
        // Prefill analyzer
        el('home').value = btn.dataset.home || '';
        el('away').value = btn.dataset.away || '';
        el('odds1').value = btn.dataset.o1 || '';
        el('oddsX').value = btn.dataset.ox || '';
        el('odds2').value = btn.dataset.o2 || '';
        // Optional: set your league label manually in the analyzer UI
        window.scrollTo({top: document.body.scrollHeight, behavior:'smooth'});
      });
    });
  }catch(err){
    el('matchesBox').innerHTML = `<span class="muted">Error: ${err.message}</span>`;
  }
}

/* ---------------- Analyze ---------------- */
async function analyzeFootball(){
  const ouLines = el('ouLines').value.trim().split(',').map(v=>parseFloat(v)).filter(v=>!isNaN(v));
  const homeTG = el('homeTG').value.trim().split(',').map(v=>parseFloat(v)).filter(v=>!isNaN(v));
  const awayTG = el('awayTG').value.trim().split(',').map(v=>parseFloat(v)).filter(v=>!isNaN(v));
  const payload = {
    league: el('league').value,
    season: parseInt(el('seasonA').value || 2025),
    home: el('home').value,
    away: el('away').value,
    odds: {"1": parseFloat(el('odds1').value || 0), "X": parseFloat(el('oddsX').value || 0), "2": parseFloat(el('odds2').value || 0)},
    context: { derby: el('derby').checked },
    markets: selectedMarkets(),
    ou_lines: ouLines.length? ouLines : [1.5,2.5,3.5],
    team_goal_lines: {"home": (homeTG.length? homeTG:[0.5,1.5]), "away": (awayTG.length? awayTG:[0.5,1.5])},
    cs_groups: [[1,0],[2,0],[2,1]]
  };
  const data = await postJSON('/analyze/football', payload);
  renderFootball(data);
}
function renderFootball(data){
  const out = el('output'); const card = document.createElement('div'); card.className='card';
  const cls = (data.status==='FINAL_PICK') ? 'good' : ((data.status==='OMITTED'||data.status==='SKIPPED')?'warn':'bad');
  const statusBadge = `<span class="badge ${cls}">${data.status}</span>`;
  let marketsHTML = '';
  if(data.markets){
    for (const [k,v] of Object.entries(data.markets)){
      if(typeof v === 'object'){
        marketsHTML += tableFromKeyMap(k, flattenIfNeeded(v));
      }
    }
  }
  const agree = data.agreement ? `<span class="pill">${data.agreement}</span>` : '';
  card.innerHTML = `
    <h2>${data.league||''} — ${data.home} vs ${data.away} ${statusBadge}</h2>
    ${data.remark? `<div class="note">Remark: ${data.remark} ${agree}</div>` : ''}
    <div class="grid grid-2">
      <div><h3>Winner Mode</h3>
        ${tableFromRows(['Outcome','Poisson%','Bayesian%','DixonColes%','FairOdds','Notes'],
          (data.winner_mode_table?.rows||[]).map(r=>[r.outcome, r['Poisson%'], r['Bayesian%'], r['DixonColes%'], r['FairOdds']||'-', r['notes']]))}
      </div>
      <div><h3>Value Mode</h3>
        ${tableFromKeyMap('Implied %', data.value_mode_table?.implied_percent)}
        ${tableFromKeyMap('True %', data.value_mode_table?.true_percent)}
        ${tableFromKeyMap('Fair Odds', data.value_mode_table?.fair_odds)}
        ${tableFromKeyMap('Edge (pp)', data.value_mode_table?.edge_percent_points)}
        <p><small>Best Edge: ${data.value_mode_table?.best_edge_sel || '-'}</small></p>
      </div>
    </div>
    <div class="grid grid-2">
      <div><h3>Alignment</h3>
        ${tableFromRows(['WM Best','VM Best','WM=VM','Edge (best, pp)','Remark'], [[
          data.alignment?.wm_best || '-', data.alignment?.vm_best || '-', data.alignment?.wm_equals_vm ? 'Yes':'No',
          data.alignment?.edge_best_pp ?? '-', data.alignment?.remark || '-'
        ]])}
      </div>
      <div><h3>Audit</h3>
        ${tableFromRows(['Parameters','Formula','EV Sim','Calibration'], [[
          data.audit?.parameters_ok ? 'OK':'Check', data.audit?.formula_ok ? 'OK':'Check', data.audit?.ev_sim ?? '-', data.audit?.calibration_note || '-'
        ]])}
      </div>
    </div>
    <h3>Markets</h3>
    ${marketsHTML || '<p><small>No markets calculated.</small></p>'}
    <p class="muted"><small>Sources: ${(data.sources || []).join(' • ')}</small></p>
  `;
  out.prepend(card);
}

/* ---------------- Misc ---------------- */
async function checkEnv(){
  try{
    const env = await getJSON('/env_status');
    el('envOut').textContent = JSON.stringify(env);
  }catch(e){
    el('envOut').textContent = `Error: ${e.message}`;
  }
}

document.addEventListener('DOMContentLoaded', ()=>{
  el('btnFetch').addEventListener('click', fetchMatches);
  el('btnClear').addEventListener('click', ()=> el('matchesBox').innerHTML = `<span class="muted">Cleared.</span>`);
  el('btnAnalyze').addEventListener('click', analyzeFootball);
  el('btnEnv').addEventListener('click', checkEnv);
});
