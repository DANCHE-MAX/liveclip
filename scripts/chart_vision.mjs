/* Pure pixel analysis; a candidate must still be verified against the UI tooltip. */
function findPeakTags(image) {
  const {width,height,data}=image || {};
  if (!Number.isInteger(width)||!Number.isInteger(height)||!data||data.length!==width*height*4) throw new Error('Invalid screenshot');
  const groups=[]; const minLength=Math.max(24,Math.round(width*.03));
  for(let y=Math.floor(height*.35);y<Math.floor(height*.74);y++) {
    let start=-1;
    for(let x=Math.floor(width*.20);x<=Math.floor(width*.97);x++) {
      const i=(y*width+x)*4, r=data[i],g=data[i+1],b=data[i+2];
      const match=x<Math.floor(width*.97) && b>135 && b>r*1.35 && b>g*1.2 && r<150;
      if(match && start<0)start=x;
      if(!match && start>=0) {
        if(x-start>=minLength) {
          const group=groups.find(g=>y-g.bottom<=2 && Math.abs(g.left-start)<=4 && Math.abs(g.right-x)<=8);
          if(group){group.bottom=y;group.rows++;group.left=Math.min(group.left,start);group.right=Math.max(group.right,x);}
          else groups.push({left:start,right:x,top:y,bottom:y,rows:1});
        }
        start=-1;
      }
    }
  }
  return groups.filter(g=>g.rows>=4).sort((a,b)=>b.rows-a.rows || a.top-b.top).slice(0,12);
}
function findChartGeometry(image) {
  const {width,height,data}=image || {};
  if (!Number.isInteger(width)||!Number.isInteger(height)||!data||data.length!==width*height*4) throw new Error('Invalid screenshot');
  let best=null;
  for(let y=Math.floor(height*.55);y<Math.floor(height*.82);y++) {
    let count=0,left=width,right=-1;
    for(let x=Math.floor(width*.20);x<Math.floor(width*.98);x++){
      let i=(y*width+x)*4, r=data[i],g=data[i+1],b=data[i+2];
      if(Math.max(r,g,b)-Math.min(r,g,b)>65 && Math.max(r,g,b)>130){count++;left=Math.min(left,x);right=x;}
    }
    if(!best||count>=best.count)best={count,left,right,y};
  }
  if(!best || best.count<width*.30 || best.right-best.left<width*.35) throw new Error('Chart axis not identifiable');
  let pairs=[];
  for(let y=Math.max(best.y+20,Math.floor(height*.78));y<Math.floor(height*.93);y++){
    let spans=[],start=-1;
    for(let x=Math.max(0,best.left-12);x<=Math.min(width-1,best.right+12)+1;x++){
      let i=(y*width+x)*4,r=data[i],g=data[i+1],b=data[i+2];
      let match=x<=Math.min(width-1,best.right+12) && Math.min(r,g,b)>145 && Math.max(r,g,b)-Math.min(r,g,b)<45;
      if(match&&start<0)start=x;
      if(!match&&start>=0){if(x-start>=8&&x-start<=25)spans.push([start,x-1]);start=-1;}
    }
    if(spans.length===2 && spans[1][0]-spans[0][1]>=8) pairs.push({left:(spans[0][0]+spans[0][1])/2,right:(spans[1][0]+spans[1][1])/2,y});
  }
  if(pairs.length<3)throw new Error('Chart zoom handles not identifiable');
  const mid=pairs[Math.floor(pairs.length/2)];
  return {chartLeft:best.left,chartRight:best.right,axisY:best.y,sliderLeft:mid.left,sliderRight:mid.right,sliderY:mid.y};
}
function parseHighest(state, streamStart, streamEnd) {
  const begin=Date.parse(streamStart),end=Date.parse(streamEnd);
  if(!Number.isFinite(begin)||!Number.isFinite(end)||begin>end||!/[+-]\d\d:\d\d$/.test(streamStart)||!/[+-]\d\d:\d\d$/.test(streamEnd))throw new Error('Unverified stream time range');
  const m=state.match(/\b\d+ 文本 (\d{2}-\d{2} \d{2}:\d{2})\s*\n[\s\S]{0,150}?\b\d+ (?:text|文本) 销售额：增量 最高\s*\n\s*\d+ 文本 ([\d,]+(?:\.\d+)?)/);
  if(!m)return null;
  const startYear=new Date(begin+8*3600000).getUTCFullYear(),endYear=new Date(end+8*3600000).getUTCFullYear(),found=[];
  for(let year=startYear;year<=endYear;year++){
    const iso=`${year}-${m[1].replace(' ','T')}:00+08:00`, n=Date.parse(iso);
    if(Number.isFinite(n)&&n>=begin&&n<=end)found.push(iso);
  }
  if(found.length!==1)throw new Error('Minute date ambiguous for this livestream');
  return {time:found[0],sales:Number(m[2].replaceAll(',','')),isHighest:true};
}

async function locateHighest(app,decode,streamStart,streamEnd){
  async function frame(){return decode(await app.getScreenshot({emit:false}));}
  let initial=await frame(), g=findChartGeometry(initial), tags=findPeakTags(initial);
  if(!tags.length)throw new Error('Peak label not visible');
  let used=[];
  for(const tag of tags){
    if(used.some(x=>Math.abs(x-tag.left)<5))continue;used.push(tag.left);
    const anchor=tag.left-Math.max(6,Math.round(initial.width*.009));
    if(anchor<g.chartLeft||anchor>g.chartRight)continue;
    const fraction=(anchor-g.chartLeft)/(g.chartRight-g.chartLeft);
    const center=g.sliderLeft+fraction*(g.sliderRight-g.sliderLeft);
    const half=Math.max(12,Math.round((g.chartRight-g.chartLeft)*.014));
    if(g.sliderRight-g.sliderLeft>2*half+4){
      const l=Math.max(g.sliderLeft,center-half), r=Math.min(g.sliderRight,center+half);
      if(r-l<16)continue;
      await app.drag([g.sliderLeft,g.sliderY],[l,g.sliderY]);
      await app.drag([g.sliderRight,g.sliderY],[r,g.sliderY]);
    }
    let zoomed=await frame(), z=findChartGeometry(zoomed), newTags=findPeakTags(zoomed);
    let locations=newTags.length?newTags:[tag];
    for(const marker of locations){
      const target=marker.left-Math.max(6,Math.round(zoomed.width*.009));
      const y=Math.min(z.axisY-10,marker.top+32);
      for(let delta=-12;delta<=12;delta++){
        let x=target+delta;if(x<z.chartLeft||x>z.chartRight)continue;
        await app.click([x,y]);
        const result=parseHighest(await app.getAXState({emit:false,disableDiffing:true}),streamStart,streamEnd);
        if(result)return {...result,chart:{chartLeft:z.chartLeft,chartRight:z.chartRight,sliderLeft:z.sliderLeft,sliderRight:z.sliderRight}};
      }
    }
    const current=findChartGeometry(await frame());
    await app.drag([current.sliderLeft,current.sliderY],[g.sliderLeft,current.sliderY]);
    await app.drag([current.sliderRight,current.sliderY],[g.sliderRight,current.sliderY]);
  }
  throw new Error('Peak labels found but the maximum minute could not be verified');
}
async function resetChartZoom(app,decode){
  const image=decode(await app.getScreenshot({emit:false}));
  const g=findChartGeometry(image);
  await app.drag([g.sliderLeft,g.sliderY],[g.chartLeft,g.sliderY]);
  await app.drag([g.sliderRight,g.sliderY],[g.chartRight,g.sliderY]);
  return g;
}
function inferStreamRange(state, listingStart) {
  const m=String(listingStart).match(/^(\d{4})\/(\d{2})\/(\d{2}) (\d{2}):(\d{2})$/);
  const h=state.match(/开播:\s*(\d{2})-(\d{2}) (\d{2}):(\d{2})\s+(\d{1,3})\s*:\s*(\d{2})\s*:\s*(\d{2})/);
  if(!m||!h||m[2]!==h[1]||m[3]!==h[2]||m[4]!==h[3]||m[5]!==h[4]||Number(h[6])>59||Number(h[7])>59)throw new Error('Stream start or duration not verified');
  const start=`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:00+08:00`, t=Date.parse(start);
  if(!Number.isFinite(t))throw new Error('Invalid stream start');
  const seconds=Number(h[5])*3600+Number(h[6])*60+Number(h[7]);
  if(seconds<=0||seconds>14*86400)throw new Error('Invalid stream duration');
  const end=new Date(t+seconds*1000+8*3600000).toISOString().slice(0,19)+'+08:00';
  return {start,end};
}
export {findPeakTags,findChartGeometry,parseHighest,locateHighest,resetChartZoom,inferStreamRange};
