const assert=require('node:assert/strict');
const {scanHour}=require('../scripts/changuanjia_cua.cjs');
(async()=>{
 const start='2026-11-20T14:00:00+08:00',end='2026-11-20T15:00:00+08:00';
 let active=0;
 const app={click:async p=>{active=p[0]},getAXState:async()=>`1 文本 11-20 14:${String(active).padStart(2,'0')}\n2 文本 销售额：增量\n3 文本 ${active===2?'870.2':'0'}`};
 let r=await scanHour(app,Array.from({length:60},(_,i)=>[i,1]),start,end,'2026-11-19T10:56:00+08:00','2026-11-20T15:00:00+08:00');
 assert.equal(r.coverage,60);assert.equal(r.selected[0].sales,870.2);
 let partial=await scanHour(app,Array.from({length:59},(_,i)=>[i,1]),start,end,'2026-11-19T10:56:00+08:00','2026-11-20T15:00:00+08:00');
 assert.equal(partial.coverage,59);assert.equal(partial.status,'incomplete');assert.deepEqual(partial.selected,[]);
 console.log('hourly scan coverage tests passed');
})().catch(e=>{console.error(e);process.exitCode=1});
