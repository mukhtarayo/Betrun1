async function postJSON(url, data){
  const res = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)});
  if(!res.ok){ throw new Error(await res.text()); }
  return await res.json();
}
async function getJSON(url){
  const res = await fetch(url);
  if(!res.ok){ throw new Error(await res.text()); }
  return await res.json();
}
function el(id){ return document.getElementById(id); }

function tableFromRows(headers, rows){
  let h = '<table><thead><tr>' + headers.map(x=>`<th>${x}</th>`).join('') + '</tr></thead><tbody>';
  for(const r of rows){ h += '<tr>' + r.map(c=>`<td>${c}</td>`).join('') + '</tr>'; }
  h += '</tbody></table>';
  return h;
}
function tableFromKeyMap(title, m){
  if(!m) return '';
  const rows = Object.keys(m).map(k=>[k, m[k]]);
  return `<h4>${title}</h4>${tableFromRows(['Key','Value'], rows)}`;
}
function flattenIfNeeded(v){
  const out = {};
  for(const k in v){
    if (v && typeof v[k]==='object' && !Array.isArray(v[k])){
      for(const kk in v[k]) out[`${k} ${kk}`] = v[k][kk];
    } else {
      out[k] = v[k];
    }
  }
  return out;
}
function selectedMarkets(){
  return Array.from(document.querySelectorAll('.mk:checked')).map(x=>x.value);
}

function bookmakerCell(oddsObj){
  if(!oddsObj) return '—';
  const bk = oddsObj.bookmaker || '—';
  const o1 = oddsObj.odds?.['1'] ?? '—';
  const ox = oddsObj.odds?.['X'] ?? '—';
  const o2 = oddsObj.odds?.['2'] ?? '—';
  return `<div><span class="bookmaker">${bk}</span><div>1: <b>${o1}</b> • X: <b>${ox}</b> • 2: <b>${o2}</b></div></div>`;
}

function statusBadge(s){
  const cls = s==='FINAL_PICK' ? 'good' : (s==='OMITTED' || s==='SKIPPED' ? 'warn' : 'bad');
  return `<span class="badge ${cls}">${s}</span>`;
}

function renderFootball(data){
  const out = el('output'); const card = document.createElement('div'); card.className='card';
  const badge = statusBadge(data.status || '—');

  let marketsHTML = '';
  if(data.markets){
    for(const [k,v] of Object.entries(data.markets)){
      if(typeof v === 'object'){
        marketsHTML += tableFromKeyMap(k, flattenIfNeeded(v));
      }
    }
  }
  const agree = data.agreement ? `<div class="pill">Agreement: ${data.agreement}</div>` : '';

  card.innerHTML = `
    <h2>${data.league||''} — ${data.home} vs ${data.away} ${badge}</h2>
    <div class="grid-2">
      <div>
        <h3>Winner Mode</h3>
        ${tableFromRows(['Outcome','Poisson%','Bayesian%','DixonColes%','FairOdds','Notes'],
          (data.winner_mode_table?.rows||[]).map(r=>[
            r.outcome, r['Poisson%'], r['Bayesian%'], r['DixonColes%'], r['FairOdds']??'-', r['notes']
          ])
        )}
      </div>
      <div>
        <h3>Value Mode</h3>
        ${tableFromKeyMap('Implied %', data.value_mode_table?.implied_percent)}
        ${tableFromKeyMap('True %', data.value_mode_table?.true_percent)}
        ${tableFromKeyMap('Fair Odds', data.value_mode_table?.fair_odds)}
        ${tableFromKeyMap('Edge (pp)', data.value_mode_table?.edge_percent_points)}
        <p><small>Best Edge: ${data.value_mode_table?.best_edge_sel || '-'}</small></p>
      </div>
    </div>

    <div class="grid-2">
      <div>
        <h3>Alignment</h3>
        ${tableFromRows(['WM Best','VM Best','WM=VM','Edge (best, pp)','Remark'], [[
          data.alignment?.wm_best || '-', data.alignment?.vm_best || '-', data.alignment?.wm_equals_vm ? 'Yes':'No',
          data.alignment?.edge_best_pp ?? '-', data.alignment?.remark || '-'
        ]])}
        ${agree}
      </div>
      <div>
        <h3>Audit</h3>
        ${tableFromRows(['Parameters','Formula','EV Sim','Calibration'], [[
          data.audit?.parameters_ok ? 'OK':'Check',
          data.audit?.formula_ok ? 'OK':'Check',
          data.audit?.ev_sim ?? '-',
          data.audit?.calibration_note || '-'
        ]])}
      </div>
    </div>

    <h3>Markets</h3>
    ${marketsHTML || '<p class="note">No markets calculated.</p>'}
    <p class="note">Sources: ${(data.sources || []).join(' • ')}</p>
  `;
  out.prepend(card);
}

async function analyzeFootball(){
  const ouLines = el('ouLines').value.trim().split(',').map(v=>parseFloat(v)).filter(v=>!isNaN(v));
  const homeTG = el('homeTG').value.trim().split(',').map(v=>parseFloat(v)).filter(v=>!isNaN(v));
  const awayTG = el('awayTG').value.trim().split(',').map(v=>parseFloat(v)).filter(v=>!isNaN(v));
  const csGroups = el('csGroups').value.trim().split(',').map(x=>x.trim()).filter(x=>x.includes(':')).map(x=>x.split(':').map(Number));

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
    cs_groups: csGroups.length? csGroups : [[1,0],[2,0],[2,1]]
  };

  const data = await postJSON('/analyze/football', payload);
  renderFootball(data);
}

async function getMatches(){
  const league = parseInt(el('fxLeague').value || 0);
  const season = parseInt(el('fxSeason').value || 0);
  const date = el('fxDate').value.trim() || undefined;
  if(!league || !season){
    el('matchesWrap').innerHTML = `<p class="note">Enter <b>league</b> and <b>season</b> first.</p>`;
    return;
  }
  const url = `/api/matches?league_id=${league}&season=${season}${date?`&date=${encodeURIComponent(date)}`:''}`;
  const res = await getJSON(url);
  const rows = (res.items||[]).map(item=>{
    const hm = item.home?.name || item.home || '-';
    const aw = item.away?.name || item.away || '-';
    const odds = item.odds || null;

    const fillBtn = `<button data-home="${hm}" data-away="${aw}" data-o1="${odds?.odds?.['1']||''}" data-ox="${odds?.odds?.['X']||''}" data-o2="${odds?.odds?.['2']||''}" class="fillAnalyze">Analyze</button>`;
    return [
      new Date(item.utc||item.kickoff||item.date||'').toLocaleString() || '—',
      `${hm} vs ${aw}`,
      bookmakerCell(odds),
      fillBtn
    ];
  });

  el('matchesWrap').innerHTML = tableFromRows(['UTC','Match','Odds (Bookmaker)',''], rows || []);
  // hook buttons
  document.querySelectorAll('.fillAnalyze').forEach(btn=>{
    btn.addEventListener('click', (e)=>{
      const b = e.currentTarget;
      el('home').value = b.getAttribute('data-home') || '';
      el('away').value = b.getAttribute('data-away') || '';
      const o1 = b.getAttribute('data-o1') || '';
      const ox = b.getAttribute('data-ox') || '';
      const o2 = b.getAttribute('data-o2') || '';
      if(o1 && ox && o2){
        el('odds1').value = o1; el('oddsX').value = ox; el('odds2').value = o2;
      }
    });
  });
}

async function showEnv(){
  try{
    const e = await getJSON('/env_status');
    el('envStatus').textContent = `env: APISPORTS_KEY=${e.APISPORTS_KEY?'set':'missing'} · STRICT_TEAM_MATCH=${e.STRICT_TEAM_MATCH}`;
  }catch(err){
    el('envStatus').textContent = 'env: error';
  }
}

async function health(){
  try{
    const r = await fetch('/healthz');
    el('envStatus').textContent = r.ok? 'env: healthy' : 'env: unhealthy';
  }catch(e){
    el('envStatus').textContent = 'env: error';
  }
}

// debug helpers
async function dbgTeam(){
  const q = el('dbgTeamName').value.trim();
  if(!q) return;
  try{
    const res = await getJSON(`/debug/team?name=${encodeURIComponent(q)}`);
    el('dbgTeamOut').textContent = JSON.stringify(res, null, 2);
  }catch(e){ el('dbgTeamOut').textContent = String(e); }
}
async function dbgFixtures(){
  const league = el('dbgLeague').value.trim();
  const season = el('dbgSeason').value.trim();
  const url = `/debug/fixtures?league=${encodeURIComponent(league)}&season=${encodeURIComponent(season)}`;
  try{
    const res = await getJSON(url);
    el('dbgFixturesOut').textContent = JSON.stringify(res, null, 2);
  }catch(e){ el('dbgFixturesOut').textContent = String(e); }
}
async function dbgH2H(){
  const h = el('dbgH').value.trim();
  const a = el('dbgA').value.trim();
  const url = `/debug/h2h?home_id=${encodeURIComponent(h)}&away_id=${encodeURIComponent(a)}`;
  try{
    const res = await getJSON(url);
    el('dbgH2HOut').textContent = JSON.stringify(res, null, 2);
  }catch(e){ el('dbgH2HOut').textContent = String(e); }
}

// wire
window.addEventListener('DOMContentLoaded', ()=>{
  showEnv();
  el('btnHealth').addEventListener('click', health);
  el('btnEnv').addEventListener('click', showEnv);
  el('btnAnalyze').addEventListener('click', analyzeFootball);
  el('btnGetMatches').addEventListener('click', getMatches);

  // debug
  el('btnDbgTeam').addEventListener('click', dbgTeam);
  el('btnDbgFixtures').addEventListener('click', dbgFixtures);
  el('btnDbgH2H').addEventListener('click', dbgH2H);
});
