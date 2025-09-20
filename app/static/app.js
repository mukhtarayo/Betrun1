// app/static/app.js

async function postJSON(url, data){
  const res = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)});
  if(!res.ok){ const t = await res.text(); throw new Error(`POST ${url} failed: ${res.status} ${t}`); }
  return await res.json();
}
async function getJSON(url){
  const res = await fetch(url);
  if(!res.ok){ const t = await res.text(); throw new Error(`GET ${url} failed: ${res.status} ${t}`); }
  return await res.json();
}
function el(id){return document.getElementById(id)}
function tableFromRows(headers, rows){
  let h = '<table><thead><tr>' + headers.map(x=>`<th>${x}</th>`).join('') + '</tr></thead><tbody>';
  for (const r of rows){ h += '<tr>' + r.map(c=>`<td>${c ?? ''}</td>`).join('') + '</tr>'; }
  h += '</tbody></table>'; return h;
}
function tableFromKeyMap(title, m){
  if(!m) return '';
  const rows = Object.keys(m).map(k=>[k, m[k]]);
  return `<h4>${title}</h4>${tableFromRows(['Key','Value'], rows)}`;
}
function selectedMarkets(){
  return Array.from(document.querySelectorAll('.mk:checked')).map(x=>x.value);
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

// -------- Single analysis --------
async function analyzeFootball(){
  const ouLines = el('ouLines').value.trim().split(',').map(v=>parseFloat(v)).filter(v=>!isNaN(v));
  const homeTG = el('homeTG').value.trim().split(',').map(v=>parseFloat(v)).filter(v=>!isNaN(v));
  const awayTG = el('awayTG').value.trim().split(',').map(v=>parseFloat(v)).filter(v=>!isNaN(v));
  const payload = {
    league: el('league').value,
    season: parseInt(el('season').value || 2025),
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
  renderFootball(data, el('output'));
}

function renderFootball(data, mount){
  const card = document.createElement('div'); card.className='card';
  const statusBadge = `<span class="badge ${data.status==='FINAL_PICK'?'good':(data.status==='OMITTED' || data.status==='SKIPPED'?'warn':'bad')}">${data.status}</span>`;
  let marketsHTML = '';
  if(data.markets){
    for (const [k,v] of Object.entries(data.markets)){
      if(typeof v === 'object'){
        marketsHTML += tableFromKeyMap(k, flattenIfNeeded(v));
      }
    }
  }
  const agreement = data.agreement ? `<div class="pill"><small>Agreement: <b>${data.agreement}</b></small></div>` : '';
  card.innerHTML = `
    <h3 style="margin:0 0 6px;">${data.league||''} — ${data.home} vs ${data.away} ${statusBadge}</h3>
    ${agreement}
    <div class="grid g-2">
      <div><h4>Winner Mode</h4>
        ${tableFromRows(['Outcome','Poisson%','Bayesian%','DixonColes%','FairOdds','Notes'],
          (data.winner_mode_table?.rows||[]).map(r=>[r.outcome, r['Poisson%'], r['Bayesian%'], r['DixonColes%'], r['FairOdds']||'-', r['notes']]))}
      </div>
      <div><h4>Value Mode</h4>
        ${tableFromKeyMap('Implied %', data.value_mode_table?.implied_percent)}
        ${tableFromKeyMap('True %', data.value_mode_table?.true_percent)}
        ${tableFromKeyMap('Fair Odds', data.value_mode_table?.fair_odds)}
        ${tableFromKeyMap('Edge (pp)', data.value_mode_table?.edge_percent_points)}
        <p><small>Best Edge: ${data.value_mode_table?.best_edge_sel || '-'}</small></p>
      </div>
    </div>
    <div class="grid g-2">
      <div><h4>Alignment</h4>
        ${tableFromRows(['WM Best','VM Best','WM=VM','Edge (best, pp)','Remark'], [[
          data.alignment?.wm_best || '-', data.alignment?.vm_best || '-', data.alignment?.wm_equals_vm ? 'Yes':'No',
          data.alignment?.edge_best_pp ?? '-', data.alignment?.remark || '-'
        ]])}
      </div>
      <div><h4>Audit</h4>
        ${tableFromRows(['Parameters','Formula','EV Sim','Calibration'], [[
          data.audit?.parameters_ok ? 'OK':'Check', data.audit?.formula_ok ? 'OK':'Check', data.audit?.ev_sim ?? '-', data.audit?.calibration_note || '-'
        ]])}
      </div>
    </div>
    <h4>Markets</h4>
    ${marketsHTML || '<p><small>No markets calculated.</small></p>'}
    <p><small>Sources: ${(data.sources || []).join(' • ')}</small></p>
  `;
  mount.prepend(card);
}

// -------- Env & Debug --------
async function checkEnv(){
  try{
    const data = await getJSON('/env_status');
    el('envStatus').innerHTML = `<code>${JSON.stringify(data)}</code>`;
  }catch(err){
    el('envStatus').innerHTML = `<span class="badge bad">Env check failed</span>`;
  }
}
async function debugTeam(){
  const name = el('dbgTeamName').value.trim();
  if(!name){ el('dbgTeamOut').innerHTML = '<small>Enter a team name…</small>'; return; }
  try{
    const data = await getJSON('/debug/team?name=' + encodeURIComponent(name));
    if(!data.found){ el('dbgTeamOut').innerHTML = '<small>Not found.</small>'; return; }
    const rows = data.candidates.map(c=>[c.id, c.name, c.code || '-', c.country || '-', c.venue || '-']);
    el('dbgTeamOut').innerHTML = tableFromRows(['ID','Name','Code','Country','Venue'], rows);
  }catch(err){
    el('dbgTeamOut').innerHTML = `<small>Error: ${err.message}</small>`;
  }
}

// -------- Fixtures flow --------
async function fetchFixtures(){
  const league = el('fxLeague').value.trim();
  const season = el('fxSeason').value.trim();
  const date = el('fxDate').value.trim();
  const team = el('fxTeam').value.trim();

  const params = new URLSearchParams();
  if(league) params.set('league', league);
  if(season) params.set('season', season);
  if(date)   params.set('date', date);
  if(team)   params.set('team', team);

  el('fixturesBox').innerHTML = '<small class="muted">Loading…</small>';
  try{
    const data = await getJSON('/fixtures?' + params.toString());
    renderFixtures(data.items || []);
  }catch(err){
    el('fixturesBox').innerHTML = `<small class="badge bad">Error: ${err.message}</small>`;
  }
}
function renderFixtures(items){
  if(!items.length){ el('fixturesBox').innerHTML = '<small>No fixtures returned.</small>'; return; }
  const rows = items.map(it=>{
    const id = it.fixture_id;
    const h  = it.home, a = it.away;
    const when = it.utc ? new Date(it.utc).toISOString().replace('T',' ').slice(0,16) : '-';
    const inputs = `
      <div class="row" style="gap:6px;">
        <input placeholder="1.90" id="o1-${id}" style="min-width:80px;">
        <input placeholder="3.20" id="ox-${id}" style="min-width:80px;">
        <input placeholder="3.50" id="o2-${id}" style="min-width:80px;">
        <button class="btn" onclick="analyzeFromRow(${id}, '${it.league}', ${it.season || 'null'}, '${h.replace(/'/g,"\\'")}', '${a.replace(/'/g,"\\'")}')">Analyze</button>
      </div>`;
    return [it.league || '-', when, `${h} vs ${a}`, inputs];
  });
  el('fixturesBox').innerHTML = tableFromRows(['League','UTC','Match','Analyze'], rows);
}
async function analyzeFromRow(id, leagueName, season, home, away){
  const o1 = parseFloat((el(`o1-${id}`)?.value || '').trim() || '0');
  const ox = parseFloat((el(`ox-${id}`)?.value || '').trim() || '0');
  const o2 = parseFloat((el(`o2-${id}`)?.value || '').trim() || '0');

  const payload = {
    league: leagueName || '',
    season: Number.isFinite(season)? season : 2025,
    home, away,
    odds: {"1": o1, "X": ox, "2": o2},
    context: { derby: false },
    markets: ["1X2","Double Chance","Draw No Bet","Over/Under","BTTS","Team Goals","1X2 + O/U","DC + BTTS","Result + BTTS","Correct Score","Clean Sheet","Win to Nil","Winning Margin"],
    ou_lines: [1.5,2.5,3.5],
    team_goal_lines: {"home":[0.5,1.5], "away":[0.5,1.5]},
    cs_groups: [[1,0],[2,0],[2,1]]
  };
  const data = await postJSON('/analyze/football', payload);
  renderFootball(data, el('output'));
}
