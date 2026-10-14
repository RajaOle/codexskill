import {createServer} from 'node:http';
import {existsSync} from 'node:fs';
import {randomBytes,timingSafeEqual} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {PRIVATE_ROOT,REGIONS,SCOPES,fetchJSON,savePrivate,readPrivate,ZohoMailbox} from './index.js';

const PORT=18891,ORIGIN='http://localhost:'+PORT,REDIRECT=ORIGIN+'/callback';
const equal=(a,b)=>typeof a==='string'&&typeof b==='string'&&Buffer.byteLength(a)===Buffer.byteLength(b)&&timingSafeEqual(Buffer.from(a),Buffer.from(b));
const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function setupPage(token,{homepage=ORIGIN,redirect=REDIRECT}={}) {
  return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mili · Connect Sindy Zoho Mail</title>
<style>body{font:17px system-ui;background:#f3f5f8;color:#152338;max-width:760px;margin:40px auto;padding:24px}main{background:white;padding:30px;border-radius:16px}label{display:block;margin:18px 0}input,select,button{font:inherit;padding:10px;box-sizing:border-box;width:100%;margin-top:7px}button{background:#174b87;color:white;border:0;border-radius:6px}code{overflow-wrap:anywhere}small{color:#42536a}</style>
<main><h1>Connect Sindy’s Zoho Mail to Mili</h1><p>One-time OAuth setup. Credentials stay in a private operator directory outside Mili’s workspace. This setup reads account metadata to verify mailbox identity; it sends no email.</p>
<ol><li>Sign in as Sindy at <a href="https://api-console.zoho.com/" target="_blank" rel="noreferrer">Zoho API Console</a> (use the matching region).</li><li>Create or edit a <strong>Server-based Application</strong>, client name <strong>Mili Orvena Mail</strong>, homepage <code>${escape(homepage)}</code>.</li><li>Set authorized redirect URI exactly: <code>${escape(redirect)}</code>.</li><li>Enter client details below, then approve access while signed in to Sindy’s Zoho account.</li></ol>
<p>Scopes: <code>${SCOPES}</code>. Mailbox messages plus folder reads; no organization/admin access.</p>
<form method="post" action="/connect" autocomplete="off"><input type="hidden" name="csrf" value="${escape(token)}">
<label>Sindy’s mailbox<input name="mailbox" type="email" required value="sindy@example.com"></label>
<label>Zoho data centre<select name="region">${Object.entries(REGIONS).map(([key,[host]])=>`<option value="${key}">${host}</option>`).join('')}</select></label>
<label>OAuth Client ID<input name="clientId" required autocomplete="off" maxlength="300"></label>
<label>OAuth Client Secret<input name="clientSecret" type="password" required autocomplete="new-password" maxlength="500"></label>
<button>Connect with Zoho</button></form><p><small>If Zoho reports an invalid client, check the selected data centre and console region. If it reports a redirect mismatch, use the exact URI above.</small></p></main></html>`;
}
export function createSetupHandler({fetcher=fetch,root=PRIVATE_ROOT,publicOrigin='',homepage=ORIGIN,accessKey=''}={}) {
  if(publicOrigin) {
    const u=new URL(publicOrigin);
    if(u.protocol!=='https:'||u.origin!==publicOrigin)throw new Error('Public setup origin must be an exact HTTPS origin.');
    if(!/^[a-f0-9]{64}$/.test(accessKey))throw new Error('Public setup requires a private access key.');
  }
  const publicHost=publicOrigin?new URL(publicOrigin).host:'';
  const redirect=(publicOrigin||ORIGIN)+'/callback';
  const csrf=randomBytes(32).toString('hex');let pending=null,busy=false;
  return async(req,res)=>{
    const authHosts=Object.values(REGIONS).map(([host])=>'https://'+host).join(' ');
    // no-referrer causes Origin:null on ordinary browser form POSTs. Same-origin
    // retains CSRF origin checks while suppressing cross-site callback referrers.
    const headers={'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','Referrer-Policy':'same-origin','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; connect-src 'self'; style-src 'unsafe-inline'; form-action 'self' "+authHosts+"; frame-ancestors 'none'; base-uri 'none'"};
    const reply=(status,html)=>{res.writeHead(status,headers);res.end(html);};
    const isPublic=Boolean(publicHost&&req.headers.host===publicHost);
    if(!isPublic&&req.headers.host!=='localhost:'+PORT&&req.headers.host!=='127.0.0.1:'+PORT)return reply(403,'Invalid host.');
    const url=new URL(req.url,ORIGIN);
    try {
      if(req.method==='GET'&&url.pathname==='/.well-known/appspecific/com.chrome.devtools.json')return reply(204,'');
      if(req.method==='GET'&&url.pathname==='/open'&&!isPublic&&publicOrigin) {
        res.writeHead(303,{...headers,'Referrer-Policy':'no-referrer',Location:publicOrigin+'/setup?key='+accessKey});res.end();return;
      }
      if(req.method==='GET'&&url.pathname==='/setup'&&isPublic) {
        if(!equal(url.searchParams.get('key'),accessKey))return reply(403,'Private setup link required.');
        res.writeHead(303,{...headers,'Referrer-Policy':'no-referrer',Location:'/',
          'Set-Cookie':'__Host-mili_setup='+accessKey+'; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=3600'});res.end();return;
      }
      const cookie=/(?:^|;\s*)__Host-mili_setup=([^;]*)/.exec(req.headers.cookie||'')?.[1];
      if(isPublic&&url.pathname!=='/callback'&&!equal(cookie,accessKey))return reply(403,'Private setup link required. Open the link provided by the operator.');
      if(req.method==='GET'&&url.pathname==='/')return reply(200,setupPage(csrf,{homepage,redirect}));
      if(req.method==='POST'&&url.pathname==='/connect') {
        const expectedOrigin=isPublic?publicOrigin:'http://'+req.headers.host;
        // Chrome can send an opaque Origin from a stale no-referrer document.
        // Fetch Metadata is browser-controlled; require same-origin AND the
        // existing CSRF proof below. Never allow an explicit foreign Origin.
        const opaqueOrigin=(req.headers.origin===undefined||req.headers.origin==='null')&&req.headers['sec-fetch-site']==='same-origin';
        if(req.headers.origin!==expectedOrigin&&!opaqueOrigin)return reply(403,'Invalid origin. <a href="/">Reload setup here</a>, then submit again from the new page.');
        if(busy)return reply(409,'A connection attempt is already in progress.');
        let raw='';for await(const chunk of req){raw+=chunk;if(raw.length>6000)return reply(413,'Form too large.');}
        const form=new URLSearchParams(raw);
        if(!equal(form.get('csrf'),csrf))return reply(403,'Setup page expired after restart. <a href="/">Reload setup here</a> and enter the client details again.');
        const c=Object.fromEntries(['region','mailbox','clientId','clientSecret'].map(k=>[k,form.get(k)?.trim()]));
        if(!REGIONS[c.region]||c.mailbox!=='sindy@example.com'||!c.clientId||!c.clientSecret||c.clientId.length>300||c.clientSecret.length>500)return reply(400,'Invalid client details or mailbox.');
        const state=randomBytes(32).toString('hex');pending={...c,state,expires:Date.now()+10*60*1000};
        const auth=new URL('https://'+REGIONS[c.region][0]+'/oauth/v2/auth');
        for(const [k,v]of Object.entries({scope:SCOPES,client_id:c.clientId,response_type:'code',access_type:'offline',prompt:'consent',redirect_uri:redirect,state}))auth.searchParams.set(k,v);
        res.writeHead(303,{...headers,Location:auth.href});res.end();return;
      }
      if(req.method==='GET'&&url.pathname==='/callback') {
        if(busy||!pending||pending.expires<Date.now()||!equal(url.searchParams.get('state'),pending.state))return reply(403,'Expired or invalid OAuth callback. Start again.');
        const c=pending;pending=null;busy=true;
        try {
          const code=url.searchParams.get('code');if(!code||url.searchParams.has('error'))return reply(400,'Zoho authorization declined. Start again.');
          const token=await fetchJSON(fetcher,'https://'+REGIONS[c.region][0]+'/oauth/v2/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({grant_type:'authorization_code',client_id:c.clientId,client_secret:c.clientSecret,redirect_uri:redirect,code})});
          if(!token.refresh_token)throw new Error('Zoho returned no refresh token. Repeat with offline consent.');
          const credentials={region:c.region,mailbox:c.mailbox,clientId:c.clientId,clientSecret:c.clientSecret,refreshToken:token.refresh_token};
          const mailbox=new ZohoMailbox({load:()=>credentials,fetcher});await mailbox.authenticate();
          credentials.accountId=mailbox.auth.accountId;savePrivate(path.join(root,'credentials.json'),credentials);
          return reply(200,'<h1>Sindy’s mailbox connected</h1><p>Mili can now use Zoho mail tools. Verified primary mailbox: '+escape(credentials.mailbox)+'. No email sent. You may close this tab.</p>');
        } finally {busy=false;}
      }
      reply(404,'Not found.');
    } catch(error) {reply(400,'<h1>Connection incomplete</h1><p>'+escape(error.message)+'</p><p><a href="/">Restart setup</a></p>');}
  };
}
export function startSetup() {
  const publicOrigin=process.env.MILI_ZOHO_PUBLIC_ORIGIN||'';
  const homepage=process.env.MILI_ZOHO_HOMEPAGE||ORIGIN;
  let accessKey='';
  if(publicOrigin) {
    const file=path.join(PRIVATE_ROOT,'setup-access.json');
    if(!existsSync(file))savePrivate(file,{key:randomBytes(32).toString('hex')});
    accessKey=readPrivate(file).key;
  }
  const server=createServer(createSetupHandler({publicOrigin,homepage,accessKey}));
  server.on('error',error=>{console.error('Zoho setup server failed:',error.code||'server error');process.exitCode=1;});
  server.listen(PORT,'127.0.0.1',()=>console.log(new Date().toISOString()+' Zoho setup: '+ORIGIN));
  return server;
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===path.resolve(process.argv[1]))startSetup();
