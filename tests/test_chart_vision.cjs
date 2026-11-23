const assert=require('node:assert/strict');
const {findPeakTags}=require('../scripts/chart_vision.mjs');
const width=500,height=300,data=new Uint8Array(width*height*4);
function rect(x1,y1,x2,y2,r,g,b){for(let y=y1;y<y2;y++)for(let x=x1;x<x2;x++){const i=(y*width+x)*4;data[i]=r;data[i+1]=g;data[i+2]=b;data[i+3]=255;}}
rect(250,130,320,143,72,50,230);
rect(80,130,90,141,72,50,230);
assert.deepEqual(findPeakTags({width,height,data}).map(x=>x.left),[250]);
assert.deepEqual(findPeakTags({width,height,data:new Uint8Array(data.length)}),[]);
console.log('chart vision tests passed');
const {findChartGeometry}=require('../scripts/chart_vision.mjs');
const w=500,h=300,px=new Uint8Array(w*h*4);
function fill(x1,y1,x2,y2,r,g,b){for(let y=y1;y<y2;y++)for(let x=x1;x<x2;x++){let i=(y*w+x)*4;px[i]=r;px[i+1]=g;px[i+2]=b;}}
fill(120,210,480,214,230,60,150); fill(120,255,134,265,180,180,190);fill(466,255,480,265,180,180,190);
const geo=findChartGeometry({width:w,height:h,data:px});assert.equal(geo.chartLeft,120);assert.equal(geo.chartRight,479);assert.ok(geo.sliderLeft<geo.sliderRight);
const {locateHighest}=require('../scripts/chart_vision.mjs');
(async()=>{
 fill(250,130,320,143,72,50,230);
 let drag=0,click=0;const app={getScreenshot:async()=>({width:w,height:h,data:px}),drag:async()=>{drag++},click:async()=>{click++},getAXState:async()=>`10 文本 11-18 15:43\n11 text 销售额：增量 最高\n12 文本 1234`};
 let result=await locateHighest(app,x=>x,'2026-11-17T19:45:00+08:00','2026-11-19T10:34:00+08:00');
 assert.equal(result.time,'2026-11-18T15:43:00+08:00');assert.ok(drag>=2);assert.ok(click>=1);console.log('auto chart scan test passed');
})().catch(e=>{console.error(e);process.exitCode=1});
const {resetChartZoom}=require('../scripts/chart_vision.mjs');
(async()=>{let moves=[];const app={getScreenshot:async()=>({width:w,height:h,data:px}),drag:async(a,b)=>moves.push([a,b])};await resetChartZoom(app,x=>x);assert.equal(moves.length,2);console.log('chart reset test passed');})().catch(e=>{console.error(e);process.exitCode=1});
const {parseHighest}=require('../scripts/chart_vision.mjs');
assert.equal(parseHighest('10 文本 11-18 15:43\n11 text 销售额：增量\n12 文本 1234','2026-11-17T19:45:00+08:00','2026-11-19T10:34:00+08:00'),null);
assert.throws(()=>parseHighest('10 文本 11-18 15:43\n11 text 销售额：增量 最高\n12 文本 1234','2025-11-17T19:45:00+08:00','2026-11-19T10:34:00+08:00'));
