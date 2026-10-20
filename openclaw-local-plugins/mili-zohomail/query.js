// Read-only mailbox plans. Folder review uses Zoho's listing API, not search syntax.
export const standardFolders=['Inbox','Sent','Drafts','Spam','Trash','Archive'];
const fields=new Set(['search_key','folder','folder_id','status','sender','subject','contains','from_date','to_date','limit','start']);
const keys=new Map(['entire','content','sender','to','cc','subject','fileName','fileContent','has','in','label','fromDate','toDate','inclspamtrash','groupResult'].map(k=>[k.toLowerCase(),k]));
const months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

export function queryError(message,code='MAIL_QUERY_INVALID') {
  return Object.assign(new Error(message),{code});
}
const invalid=()=>{throw queryError('Invalid mail query. For inbox review use folder="Inbox" with no search_key. For filtering use sender, subject, contains, from_date/to_date (YYYY-MM-DD). Do not repeat an unchanged rejected query.');};
function literal(value) {
  if(typeof value!=='string'||!value.trim()||value.length>200||/["\\\x00-\x1f\x7f]/.test(value))invalid();
  return '"'+value.trim()+'"';
}
function isoDate(value) {
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))invalid();
  const d=new Date(value+'T00:00:00.000Z');
  if(!Number.isFinite(d.getTime())||d.toISOString().slice(0,10)!==value)invalid();
  return d.getUTCDate()+'-'+months[d.getUTCMonth()]+'-'+d.getUTCFullYear();
}
function rawDate(value) {
  const m=/^(\d{1,2})-([A-Za-z]{3})-(\d{4})$/.exec(value);
  if(!m)invalid();
  const month=months.findIndex(x=>x.toLowerCase()===m[2].toLowerCase());
  if(month<0)invalid();
  const iso=m[3]+'-'+String(month+1).padStart(2,'0')+'-'+m[1].padStart(2,'0');
  return isoDate(iso);
}
export function normalizeSearch(value) {
  if(typeof value!=='string'||!value.trim()||value.length>500||/[\\\x00-\x1f\x7f]/.test(value))invalid();
  value=value.trim();
  if(value==='newMails')return value;
  const parts=[];let quoted=false,start=0;
  for(let i=0;i<value.length;i++) {
    if(value[i]==='"')quoted=!quoted;
    if(!quoted&&value.slice(i,i+2)==='::') {parts.push(value.slice(start,i));start=i+2;i++;}
  }
  if(quoted)invalid();
  parts.push(value.slice(start));
  return parts.map((part,index)=>{
    part=part.trim();let prefix='';
    if(part.startsWith('or:')) {if(index===0)invalid();prefix='or:';part=part.slice(3);}
    const m=/^([A-Za-z]+):(.+)$/.exec(part);
    if(!m)invalid();
    const key=m[1].toLowerCase()==='from'?'sender':keys.get(m[1].toLowerCase());
    if(!key)invalid();
    let term=m[2].trim();
    const quotedTerm=/^"[^"\x00-\x1f]+"$/.test(term);
    if(!quotedTerm&&!/^[^\s:"]+$/.test(term))invalid();
    if(key==='fromDate'||key==='toDate')term=rawDate(term);
    if(['inclspamtrash','groupResult'].includes(key)&&!['true','false'].includes(term))invalid();
    if(key==='has'&&!['attachment','flags','convo'].includes(term))invalid();
    return prefix+key+':'+term;
  }).join('::');
}
export function planMailQuery(p={}) {
  if(!p||typeof p!=='object'||Array.isArray(p)||Object.keys(p).some(k=>!fields.has(k)))invalid();
  const limit=p.limit??20,start=p.start??1;
  if(!Number.isSafeInteger(limit)||limit<1||limit>50||!Number.isSafeInteger(start)||start<1||!Number.isSafeInteger(start+limit))throw queryError('Invalid pagination. limit must be 1–50 and start a positive safe integer.');
  if(p.search_key!==undefined) {
    if(['folder','folder_id','status','sender','subject','contains','from_date','to_date'].some(k=>p[k]!==undefined))invalid();
    const searchKey=normalizeSearch(p.search_key);
    const singleFolder=/^in:(Inbox|Sent|Drafts|Spam|Trash|Archive)$/.exec(searchKey);
    return singleFolder?{mode:'folder',folder:singleFolder[1],status:'all',limit,start}:{mode:'search',searchKey,limit,start};
  }
  if(p.folder!==undefined&&!standardFolders.includes(p.folder))invalid();
  if(p.folder_id!==undefined&&(typeof p.folder_id!=='string'||!/^\d{1,30}$/.test(p.folder_id)))invalid();
  if(p.folder!==undefined&&p.folder_id!==undefined)invalid();
  if(p.status!==undefined&&!['all','read','unread'].includes(p.status))invalid();
  const filters=[];
  for(const [field,key]of [['sender','sender'],['subject','subject'],['contains','entire']])if(p[field]!==undefined)filters.push(key+':'+literal(p[field]));
  for(const [field,key]of [['from_date','fromDate'],['to_date','toDate']])if(p[field]!==undefined)filters.push(key+':'+isoDate(p[field]));
  if(p.from_date&&p.to_date&&p.from_date>p.to_date)invalid();
  if(filters.length) {
    if(p.folder_id!==undefined||p.status!==undefined)invalid();
    const searchKey='in:'+(p.folder||'Inbox')+'::'+filters.join('::');
    if(searchKey.length>500)invalid();
    return {mode:'search',searchKey,limit,start};
  }
  return {mode:'folder',...(p.folder_id?{folderId:p.folder_id}:{folder:p.folder||'Inbox'}),status:p.status||'all',limit,start};
}
