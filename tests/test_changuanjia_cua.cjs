const assert = require('node:assert/strict');
const { chooseLatest, findExistingWindow, findDownloadConfirm } = require('../scripts/changuanjia_cua.cjs');
const state = `111 link 在播, Value: changuanjia.com/console/12
112 文本 2026/11/19 10:00
120 link 上场, Value: changuanjia.com/analyse/56
121 文本 2026/11/18 10:00
130 link 更早, Value: changuanjia.com/analyse/78
131 文本 2026/11/17 10:00`;
assert.equal(chooseLatest(state).streamId, '56');
assert.throws(() => chooseLatest('无已结束直播'));
const history = `10 text 2026-11-17 19:45 (直播)
11 text 15:40:00 - 15:46:00  (6分)
12 文本 生成时间：11/19 14:05
13 按钮 查看话术
14 按钮 下载视频`;
assert.equal(findExistingWindow(history, '2026-11-17 19:45', '15:40:00', '15:46:00').downloadElement, 14);
assert.throws(() => findExistingWindow(history, '2026-11-15 11:37', '15:40:00', '15:46:00'));
assert.equal(findDownloadConfirm('12 文本 下载确认提示\n13 按钮 确定下载'),13);
assert.throws(() => findDownloadConfirm('12 文本 其他操作\n13 按钮 确定下载'));
console.log('changuanjia CUA parser tests passed');
const { requestExistingDownload } = require('../scripts/changuanjia_cua.cjs');
requestExistingDownload({getAXState(){throw new Error('must not touch page');}},'2026-11-17 19:45','15:40:00','15:46:00').then(()=>{throw new Error('missing registry guard accepted');},e=>{assert.match(e.message,/registry/i);});
const { createRegistry } = require('../scripts/changuanjia_cua.cjs');
assert.equal(typeof createRegistry, 'function');
const { parseMinuteTooltip } = require('../scripts/changuanjia_cua.cjs');
const tip = `102 文本 11-18 15:43\n103 container\n104 text 销售额：增量 最高\n105 文本 1234\n106 文本 销售额：累计\n107 文本 120134.73`;
assert.deepEqual(parseMinuteTooltip(tip,'2026-11-17T19:45:00+08:00','2026-11-19T10:34:00+08:00'), {time:'2026-11-18T15:43:00+08:00',sales:1234,isHighest:true});
assert.throws(()=>parseMinuteTooltip('11-18 15:43 销售额：累计 120134', '2026-11-17T19:45:00+08:00','2026-11-19T10:34:00+08:00'));
assert.throws(()=>parseMinuteTooltip(tip,'2025-11-17T19:45:00+08:00','2026-11-19T10:34:00+08:00'));
const {inferStreamRange}=require('../scripts/changuanjia_cua.cjs');
assert.deepEqual(inferStreamRange('直播 开播: 11-17 19:45 38 : 48 : 22 概览','2026/11/17 19:45'),{start:'2026-11-17T19:45:00+08:00',end:'2026-11-19T10:33:22+08:00'});
assert.throws(()=>inferStreamRange('直播 开播: 11-16 19:45 38 : 48 : 22 概览','2026/11/17 19:45'));
const liveHistory = `URL: changuanjia.com/console/9000000000000009\n117 text 2026-11-19 10:56 (直播) 16:40:00 - 16:46:00 (6分) 生成时间：11/20 10:25\n118 按钮 导出话术\n119 按钮 下载视频`;
assert.equal(findExistingWindow(liveHistory,'2026-11-19 10:56','16:40:00','16:46:00').downloadElement,119);
const liveTip=`369 图像\n370 文本 11-20 14:02\n371 文本 销售额：增量\n372 文本 870.2\n373 文本 销售额：累计\n374 文本 248170.07`;
assert.deepEqual(parseMinuteTooltip(liveTip,'2026-11-19T10:56:00+08:00','2026-11-20T15:00:00+08:00'),{time:'2026-11-20T14:02:00+08:00',sales:870.2,isHighest:false});
