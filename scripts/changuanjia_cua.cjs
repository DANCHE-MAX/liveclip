/* Pure parsers plus CUA-only actions; no direct website requests or cookies. */
function chooseLatest(state) {
  const re = /^\s*(\d+) link [^\n]*Value: changuanjia\.com\/analyse\/(\d+)\s*\n\s*\d+ 文本 (\d{4}\/\d{2}\/\d{2} \d{2}:\d{2})\s*$/gm;
  const rows = Array.from(state.matchAll(re), m => ({ element: Number(m[1]), streamId: m[2], start: m[3] }));
  if (!rows.length) throw new Error('No dated ended livestreams observed');
  rows.sort((a,b) => b.start.localeCompare(a.start));
  return rows[0];
}


function parseMinuteTooltip(state, streamStart, streamEnd) {
  const begin=Date.parse(streamStart), end=Date.parse(streamEnd);
  if (!Number.isFinite(begin) || !Number.isFinite(end) || begin>end || !/[+-]\d\d:\d\d$/.test(streamStart) || !/[+-]\d\d:\d\d$/.test(streamEnd)) throw new Error('Unverified stream time range');
  const match=state.match(/\b\d+ 文本 (\d{2}-\d{2} \d{2}:\d{2})\s*\n[\s\S]{0,150}?\b\d+ (?:text|文本) 销售额：增量( 最高)?\s*\n\s*\d+ 文本 ([\d,]+(?:\.\d+)?)/);
  if (!match) throw new Error('Minute sales tooltip not observable');
  const localStart=new Date(begin+8*3600000).getUTCFullYear(), localEnd=new Date(end+8*3600000).getUTCFullYear();
  let matches=[];
  for(let year=localStart;year<=localEnd;year++){
    const value=`${year}-${match[1].replace(' ','T')}:00+08:00`, ms=Date.parse(value);
    if(Number.isFinite(ms) && ms>=begin && ms<=end) matches.push(value);
  }
  if(matches.length!==1) throw new Error('Minute date ambiguous for this livestream');
  return {time:matches[0],sales:Number(match[3].replaceAll(',','')),isHighest:!!match[2]};
}

function findExistingWindow(state, streamStart, start, end) {
  const lines = state.split('\n');
  const found = [];
  for (let i = 0; i < lines.length; i++) {
    if (!lines[i].includes('text ' + streamStart)) continue;
    const tail = lines.slice(i + 1, i + 8);
    if (![lines[i], ...tail].some(x => x.includes(`${start} - ${end}`) && x.includes('(6分)'))) continue;
    const btn = tail.map(x => x.match(/^\s*(\d+) 按钮 下载视频\s*$/)).find(Boolean);
    if (btn) found.push({ downloadElement: Number(btn[1]), streamStart, start, end });
  }
  if (found.length !== 1) throw new Error('History match is missing or ambiguous');
  return found[0];
}

async function selectLatestInVisibleList(app) {
  const state = await app.getAXState({ emit: false, disableDiffing: true });
  const chosen = chooseLatest(state);
  await app.click(chosen.element);
  const after = await app.getAXState({ emit: false, disableDiffing: true });
  if (!after.includes(`changuanjia.com/analyse/${chosen.streamId}`)) throw new Error('Stream navigation not verified');
  return chosen;
}

function findDownloadConfirm(state) {
  if (!state.includes('下载确认提示')) throw new Error('Download dialog not observable');
  const matches=Array.from(state.matchAll(/^\s*(\d+) 按钮 确定下载\s*$/gm));
  if (matches.length !== 1) throw new Error('Download confirmation ambiguous');
  return Number(matches[0][1]);
}

async function requestExistingDownload(app, streamStart, start, end, registry, streamId, peak, downloadContext) {
  if (!registry || typeof registry.reserve !== 'function') throw new Error('Download registry reservation is required');
  if (!streamId || !peak) throw new Error('Download registry requires stream ID and peak time');
  const reservation = await registry.reserve(streamId, peak);
  if (reservation.status === 'reuse') return {status:'reused', path:reservation.path};
  if (reservation.status !== 'reserved') throw new Error('Download registry did not reserve this window');
  if (!downloadContext || typeof downloadContext.waitForDownload !== 'function' || !downloadContext.startIso || !downloadContext.endIso || typeof registry.finish !== 'function') throw new Error('Download completion and registry verification are required');
  if (typeof downloadContext.prepare === 'function') await downloadContext.prepare();
  const before=await app.getAXState({emit:false,disableDiffing:true});
  if (!/^\d+$/.test(streamId)) throw new Error('Invalid livestream ID');
  const pagePattern=new RegExp('changuanjia\\.com/(?:analyse|console)/'+streamId+'(?:[\\s?#]|$)');
  if (!pagePattern.test(before)) throw new Error('Selected livestream does not match registry stream');
  const match=findExistingWindow(before,streamStart,start,end);
  await app.click(match.downloadElement);
  const dialog=await app.getAXState({emit:false,disableDiffing:true});
  const confirmation=findDownloadConfirm(dialog);
  await app.click(confirmation);
  await app.getAXState({emit:false,disableDiffing:true});
  const path = await downloadContext.waitForDownload();
  return registry.finish(streamId, peak, path, downloadContext.startIso, downloadContext.endIso);
}

function createRegistry({ python, projectRoot, database, dailyBudgetDay }) {
  const { execFile } = require('node:child_process');
  const { promisify } = require('node:util');
  const run = promisify(execFile);
  async function invoke(command, args) {
    const options = ['-m', 'liveclip.download_registry'];
    if (database) options.push('--db', database);
    options.push(command, ...args);
    const { stdout } = await run(python, options, { cwd: projectRoot, timeout: 60000, maxBuffer: 1024*1024 });
    return JSON.parse(stdout);
  }
  return {
    reserve: (streamId, peak) => dailyBudgetDay ? invoke('reserve-daily', [streamId, peak, dailyBudgetDay]) : invoke('reserve', [streamId, peak]),
    finish: (streamId, peak, file, start, end) => invoke('finish', [streamId, peak, file, start, end])
  };
}

function chartPoints({left,right,y}) {
  if (![left,right,y].every(Number.isInteger) || left<0 || right<left || right-left>2500 || y<0) throw new Error('Invalid chart bounds');
  return Array.from({length:right-left+1},(_,i)=>[left+i,y]);
}

async function scanForHighest(app, points, streamStart, streamEnd) {
  if (!Array.isArray(points) || !points.length) throw new Error('No calibrated chart points');
  for (const point of points) {
    if (!Array.isArray(point) || point.length!==2 || !point.every(Number.isFinite)) throw new Error('Invalid chart point');
    await app.click(point);
    const state=await app.getAXState({emit:false,disableDiffing:true});
    let sample;
    try { sample=parseMinuteTooltip(state,streamStart,streamEnd); } catch { continue; }
    if(sample.isHighest) return sample;
  }
  throw new Error('No platform-confirmed highest minute was observed');
}

async function scanHour(app, points, hourStart, hourEnd, streamStart, streamEnd) {
  const start=Date.parse(hourStart), end=Date.parse(hourEnd);
  if(!Number.isFinite(start)||end-start!==3600000 || start%60000!==0)throw new Error('Invalid hour');
  if(!Array.isArray(points)||!points.length)throw new Error('No calibrated chart points');
  const samples=new Map();
  for(const point of points){
    if(!Array.isArray(point)||point.length!==2||!point.every(Number.isFinite))throw new Error('Invalid chart point');
    await app.click(point);
    const state=await app.getAXState({emit:false,disableDiffing:true});
    let sample;try{sample=parseMinuteTooltip(state,streamStart,streamEnd)}catch{continue}
    const t=Date.parse(sample.time);if(t<start||t>=end)continue;
    if(samples.has(t)&&samples.get(t).sales!==sample.sales)throw new Error('Conflicting minute data');
    samples.set(t,sample);
  }
  const missing=[];for(let t=start;t<end;t+=60000)if(!samples.has(t))missing.push(new Date(t).toISOString());
  if(missing.length)return {status:'incomplete',coverage:samples.size,missing,selected:[]};
  const rows=[...samples.values()].sort((a,b)=>Date.parse(a.time)-Date.parse(b.time));
  const high=rows.filter(x=>x.sales>=1000);
  if(high.length)return {status:'complete',coverage:60,missing:[],selected:high};
  const best=rows.reduce((a,b)=>b.sales>a.sales?b:a);
  return {status:'complete',coverage:60,missing:[],selected:best.sales>=600?[best]:[]};
}

function createDownloadWatcher({python, projectRoot, directory, snapshotFile, startIso, endIso, timeout=600}) {
  const { promisify } = require('node:util');
  const run=promisify(require('node:child_process').execFile);
  async function invoke(args, ms) {
    const {stdout}=await run(python,['-m','liveclip.download_wait',...args],{cwd:projectRoot,timeout:ms,maxBuffer:1024*1024});
    return JSON.parse(stdout);
  }
  return {
    startIso, endIso,
    prepare: () => invoke(['snapshot',directory,snapshotFile],30000),
    waitForDownload: async () => (await invoke(['wait',directory,snapshotFile,startIso,endIso,'--timeout',String(timeout)],(timeout+10)*1000)).path
  };
}

module.exports = { inferStreamRange: require('./chart_vision.mjs').inferStreamRange, chartPoints, scanForHighest, scanHour, createDownloadWatcher, parseMinuteTooltip, chooseLatest, findExistingWindow, selectLatestInVisibleList, findDownloadConfirm, requestExistingDownload, createRegistry };
