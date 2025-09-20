async function postJSON(url, data){
  const res = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)});
  if(!res.ok){ throw new Error('Request failed'); }
  return await res.json();
}
function el(id){return document.getElementById(id)}
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
function selectedMarkets(){
  return Array.from(document.querySelectorAll('.mk:checked')).map(x=>x.value);
}
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
  renderFootball(data);
}
function renderFootball(data){
  const out = el('output'); const card = document.createElement('div'); card.className='card';
  const statusClass = data.status==='FINAL_PICK'?'good':(data.status==='OMITTED'?'warn':'bad');
  const statusBadge = `<span class="badge ${statusClass}">${data.status||'SKIPPED'}</span>`;
  let marketsHTML = '';
  if(data.markets){
    for (const [k,v] of Object.entries(data.markets)){
      if(typeof v === 'object'){
        marketsHTML += tableFromKeyMap(k, flattenIfNeeded(v));
      }
    }
  }
  card.innerHTML = `
    <h2>${data.league||''} — ${data.home||''} vs ${data.away||''} ${statusBadge}</h2>
    <div class="grid grid-3">
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
      <div><h3>Alignment</h3>
        ${tableFromRows(['WM Best','VM Best','WM=VM','Edge (best, pp)','Remark'], [[
          data.alignment?.wm_best || '-', data.alignment?.vm_best || '-', data.alignment?.wm_equals_vm ? 'Yes':'No',
          data.alignment?.edge_best_pp ?? '-', data.alignment?.remark || '-'
        ]])}
        <p><small>Agreement: ${data.agreement||'-'}</small></p>
      </div>
    </div>
    <h3>Markets</h3>
    ${marketsHTML || '<p><small>No markets calculated.</small></p>'}
    <p><small>Sources: ${(data.sources || []).join(' • ')}</small></p>
  `;
  out.prepend(card);
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
async function showEnv(){
  const res = await fetch('/env_status'); const data = await res.json();
  el('env').textContent = JSON.stringify(data,null,2);
}
