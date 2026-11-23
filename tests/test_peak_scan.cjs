const assert=require('node:assert/strict');
const {scanForHighest}=require('../scripts/changuanjia_cua.cjs');
(async()=>{
 let i=0;const a={click:async()=>{},getAXState:async()=>['1 文本 11-18 15:42\n2 text 销售额：增量\n3 文本 10','1 文本 11-18 15:43\n2 text 销售额：增量 最高\n3 文本 1234'][i++]};
 let r=await scanForHighest(a,[[1,1],[2,1]],'2026-11-17T19:45:00+08:00','2026-11-19T10:34:00+08:00');
 assert.equal(r.time,'2026-11-18T15:43:00+08:00');assert.equal(r.sales,1234);
 let bad={click:async()=>{},getAXState:async()=> 'unavailable'};
 await assert.rejects(()=>scanForHighest(bad,[[1,1]],'2026-11-17T19:45:00+08:00','2026-11-19T10:34:00+08:00'));
 console.log('peak scan tests passed');
})().catch(e=>{console.error(e);process.exitCode=1});
const { chartPoints }=require('../scripts/changuanjia_cua.cjs');
assert.deepEqual(chartPoints({left:3,right:5,y:10}),[[3,10],[4,10],[5,10]]);
assert.throws(()=>chartPoints({left:5,right:3,y:10}));
