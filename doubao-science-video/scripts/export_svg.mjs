#!/usr/bin/env node
// Deterministic local HTML/SVG -> PNG pipe -> H.264. No model or credential access.
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import {createRequire} from 'node:module';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {performance} from 'node:perf_hooks';

const opts = {fps:25, width:1280, height:720};
const args = process.argv.slice(2);
for (let i=0;i<args.length;i++) {
  if (args[i] === '--headless') opts.headless = true;
  else if (args[i].startsWith('--')) opts[args[i].slice(2)] = args[++i];
  else if (!opts.input) opts.input = args[i];
  else throw Error('Unexpected argument');
}
if (!opts.input || !opts.output) {
  console.error('Usage: node export_svg.mjs scene.html --output silent.mp4 [--duration seconds] [--fps 25] [--channel chrome] [--headless]');
  process.exit(1);
}
for (const k of ['fps','width','height']) {
  opts[k]=Number(opts[k]);
  if (!Number.isInteger(opts[k]) || opts[k]<=0) throw Error('Invalid '+k);
}
if (opts.width%2 || opts.height%2 || opts.fps>60 || opts.width>3840 || opts.height>2160) throw Error('Unsupported render dimensions/fps');
const input = await fs.realpath(opts.input), base = path.dirname(input);
const output = path.resolve(opts.output), reportPath = output+'.report.json';
for (const file of [output,reportPath]) {
  try {await fs.access(file);throw Error('Output exists: '+file);} catch(e) {if(e.code!=='ENOENT') throw e;}
}
const require = createRequire(import.meta.url);
let chromium;
try {({chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright'));}
catch {throw Error('Install playwright next to this script, or set PLAYWRIGHT_MODULE to an installed module path.');}
await fs.mkdir(path.dirname(output),{recursive:true});
const temp = await fs.mkdtemp(path.join(path.dirname(output),'.svg-render-'));
const candidate = path.join(temp,'render.mp4');
let browser, encoder, server;
const started=performance.now();
try {
  server=http.createServer(async(req,res)=>{
    try {
      if(req.method!=='GET') {res.writeHead(405).end();return;}
      const file=await fs.realpath(path.resolve(base,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname)));
      if(file!==base && !file.startsWith(base+path.sep)) {res.writeHead(403).end();return;}
      const types={'.html':'text/html; charset=utf-8','.js':'text/javascript','.svg':'image/svg+xml','.css':'text/css','.png':'image/png'};
      res.setHeader('Content-Type',types[path.extname(file)]||'application/octet-stream');
      res.end(await fs.readFile(file));
    } catch {res.writeHead(404).end();}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin='http://127.0.0.1:'+server.address().port;
  browser=await chromium.launch({headless:!!opts.headless,...(opts.channel?{channel:opts.channel}:{})});
  const context=await browser.newContext({viewport:{width:opts.width,height:opts.height+100},deviceScaleFactor:1,serviceWorkers:'block'});
  await context.route('**/*',route=>new URL(route.request().url()).origin===origin ? route.continue() : route.abort());
  const page=await context.newPage(), errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(origin+'/'+encodeURIComponent(path.basename(input))+'?export=1',{waitUntil:'networkidle'});
  await page.evaluate(()=>document.fonts.ready);
  const info=await page.evaluate(()=>({duration:window.animationDuration,renderable:typeof window.renderFrame==='function'}));
  const duration=Number(opts.duration ?? info.duration);
  if(!info.renderable || !Number.isFinite(duration) || duration<=0 || duration>600) throw Error('Scene requires renderFrame(seconds) and duration in (0,600]');
  const stage=page.locator('#stage');
  const box=await stage.boundingBox();
  if(!box || Math.abs(box.width-opts.width)>0.1 || Math.abs(box.height-opts.height)>0.1) throw Error('#stage size must match export dimensions');
  const frames=Math.ceil(duration*opts.fps);
  encoder=spawn('ffmpeg',['-nostdin','-v','error','-f','image2pipe','-vcodec','png','-framerate',String(opts.fps),'-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',candidate],{stdio:['pipe','ignore','pipe']});
  let stderr='', encoderError;
  encoder.stderr.on('data',b=>{stderr=(stderr+b.toString()).slice(-2000);});
  encoder.stdin.on('error',e=>{encoderError=e;});
  const completion=new Promise(resolve=>{
    encoder.once('error',e=>{encoderError=e;resolve(-1);});
    encoder.once('close',resolve);
  });
  for(let i=0;i<frames;i++) {
    if(encoderError) throw encoderError;
    await page.evaluate(async t=>{await window.renderFrame(t);},i/opts.fps);
    const png=await stage.screenshot({type:'png',animations:'allow'});
    if(!encoder.stdin.write(png)) await once(encoder.stdin,'drain');
    if(i%opts.fps===0) console.log(`Frame ${i}/${frames}`);
  }
  encoder.stdin.end();
  const code=await completion;
  if(code!==0 || encoderError) throw Error(stderr || String(encoderError));
  if(errors.length) throw Error('Scene errors: '+errors.join('; '));
  await fs.copyFile(candidate,output,fs.constants.COPYFILE_EXCL);
  const report={status:'silent_video_exported',duration:frames/opts.fps,fps:opts.fps,width:opts.width,height:opts.height,frames,render_seconds:Number(((performance.now()-started)/1000).toFixed(2)),model_calls:0,human_review:'pending'};
  await fs.writeFile(reportPath,JSON.stringify(report,null,2),{flag:'wx'});
  console.log(JSON.stringify(report));
} finally {
  if(encoder && encoder.exitCode===null) encoder.kill();
  if(browser) await browser.close();
  if(server) await new Promise(resolve=>server.close(resolve));
  await fs.rm(temp,{recursive:true,force:true});
}
