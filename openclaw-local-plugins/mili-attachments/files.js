// Byte-preserving business-file transport. No OCR, shell execution, or public sharing.
import {readFileSync,writeFileSync,mkdirSync,renameSync} from 'node:fs';
import {open,realpath} from 'node:fs/promises';
import {constants} from 'node:fs';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {Readable} from 'node:stream';
import path from 'node:path';

export const MAX_FILE_BYTES=20*1024*1024;
export const WORKSPACE='/home/olekamole/.openclaw/workspace-mili';
const CATALOG='/home/olekamole/.openclaw/mili-attachments';
const digest=(bytes,algorithm='sha256')=>createHash(algorithm).update(bytes).digest('hex');
const fail=message=>{throw new Error(message);};
export function safeName(name) {
  if(typeof name!=='string'||!name.trim()||name.length>240||/[\x00-\x1f\x7f/\\]/.test(name)||name==='.'||name==='..')fail('Use a plain filename without paths or control characters.');
  return name;
}
const fileId=value=>{if(typeof value!=='string'||! /^[A-Za-z0-9_-]{5,200}$/.test(value))fail('Use an exact Drive file/folder ID.');return value;};
export function assertFileRequester(ctx,allowed,workspace=WORKSPACE) {
  if(ctx.agentId!=='mili'||!ctx.sessionKey?.startsWith('agent:mili:'))fail('File transfer belongs to Mili only.');
  const senders=allowed||[...readFileSync(path.join(workspace,'USER.md'),'utf8').matchAll(/WhatsApp `([^`]+)`/g)].map(m=>m[1]);
  if(!ctx.requesterSenderId||!senders.includes(ctx.requesterSenderId))fail('File transfer requires verified current Ibnu or Sindy.');
}
const MIME={'.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.webp':'image/webp','.pdf':'application/pdf','.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','.pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation','.zip':'application/zip','.csv':'text/csv','.txt':'text/plain','.md':'text/markdown','.json':'application/json'};
export function fileResult(name,bytes,mimeType) {
  safeName(name);if(!Buffer.isBuffer(bytes))bytes=Buffer.from(bytes);
  if(!bytes.length||bytes.length>MAX_FILE_BYTES)fail('File must contain 1 byte–20 MiB.');
  // Reject the precise prior failure instead of forwarding a disguised path file.
  if(/\.(?:jpe?g|png|pdf|docx|xlsx|pptx)$/i.test(name)&&bytes.length<4096&&/^(?:\/home\/|\/tmp\/|file:\/\/)[^\r\n]+$/.test(bytes.toString('utf8').trim()))fail('File contains a local path, not original attachment bytes.');
  return {name,bytes,mimeType:mimeType||MIME[path.extname(name).toLowerCase()]||'application/octet-stream',size:bytes.length,sha256:digest(bytes),md5:digest(bytes,'md5')};
}
async function localBytes(file,root) {
  const expected=path.resolve(file),canonicalRoot=await realpath(root),canonical=await realpath(expected);
  if(canonical!==expected||!canonical.startsWith(canonicalRoot+path.sep))fail('File path/symlink is outside approved source.');
  const handle=await open(expected,constants.O_RDONLY|constants.O_NOFOLLOW);
  try {
    const before=await handle.stat();if(!before.isFile()||before.size<1||before.size>MAX_FILE_BYTES)fail('File must be a regular file of 1 byte–20 MiB.');
    const chunks=[];let length=0;
    for(;;) {const b=Buffer.alloc(65536);const {bytesRead}=await handle.read(b,0,b.length,null);if(!bytesRead)break;length+=bytesRead;if(length>MAX_FILE_BYTES)fail('File grew beyond size limit.');chunks.push(b.subarray(0,bytesRead));}
    const after=await handle.stat();if(before.size!==length||after.size!==before.size||after.mtimeMs!==before.mtimeMs)fail('Source changed while reading; inspect again.');
    return Buffer.concat(chunks);
  } finally {await handle.close();}
}
export const fileSourceSchema={type:'object',additionalProperties:false,properties:{attachment_id:{type:'string'},workspace_path:{type:'string'},drive_file_id:{type:'string'},export_mime_type:{type:'string'},name:{type:'string'},mail_attachment:{type:'object',additionalProperties:false,properties:{folder_id:{type:'string'},message_id:{type:'string'},attachment_id:{type:'string'}},required:['folder_id','message_id','attachment_id']}},oneOf:[{required:['attachment_id']},{required:['workspace_path']},{required:['drive_file_id']},{required:['mail_attachment']}]};
export async function resolveFile(source,ctx,{workspace=WORKSPACE,catalog=CATALOG,drive,mailDownload}={}) {
  if(!source||typeof source!=='object'||['attachment_id','workspace_path','drive_file_id','mail_attachment'].filter(k=>source[k]!==undefined).length!==1)fail('Specify exactly one attachment_id, workspace_path, drive_file_id or mail_attachment.');
  if(source.attachment_id) {
    const data=JSON.parse(readFileSync(path.join(catalog,'index.json'),'utf8'));
    const entry=data.entries.find(e=>e.id===source.attachment_id&&e.sessionKey===ctx.sessionKey);
    if(!entry)fail('Attachment is not in this conversation catalog.');
    return fileResult(source.name||entry.name,await localBytes(entry.path,path.join(workspace,'attachments/inbound')));
  }
  if(source.workspace_path) {
    const file=path.resolve(workspace,source.workspace_path),relative=path.relative(workspace,file);
    const parts=relative.split(path.sep);
    if(parts.some(p=>p.startsWith('.'))||['memory','media','attachments'].includes(parts[0])||/^(?:AGENTS|SOUL|USER|IDENTITY|SECURITY|MEMORY|ZOHO_MAIL|GOOGLE_ACCESS|SHEET_WRITE_RULES|ATTACHMENT_OCR|FILE_TRANSFERS|WORKFLOWS|SCOPE|CONVERSATION_STYLE|PRODUCT_KNOWLEDGE)\.md$/i.test(relative)||/(?:credentials|secrets|auth-profiles|token\.json|\.env)(?:$|[./])/i.test(relative))fail('Use catalog IDs for inbound files; agent instructions, memory and credentials cannot be attached.');
    return fileResult(source.name||path.basename(file),await localBytes(file,workspace));
  }
  if(source.drive_file_id) return (drive||await getDriveAdapter()).download(source);
  if(!mailDownload)fail('Mail attachment sources require the connected mail provider.');
  const file=await mailDownload(source.mail_attachment);return fileResult(source.name||file.name,file.bytes,file.mimeType);
}

let googleAdapter;
export async function getDriveAdapter() {
  if(googleAdapter)return googleAdapter;
  const require=createRequire(process.env.MILI_GDRIVE_PACKAGE||'/home/olekamole/.openclaw/mcp-servers/gdrive/package.json');
  const {google}=require('googleapis');
  const credentials=JSON.parse(readFileSync(process.env.GDRIVE_CREDENTIALS_PATH||'/home/olekamole/.openclaw/gdrive-credentials.json','utf8'));
  const tokenPath=process.env.GDRIVE_TOKEN_PATH||'/home/olekamole/.openclaw/gdrive-token.json';
  const token=JSON.parse(readFileSync(tokenPath,'utf8'));const c=credentials.installed||credentials.web;
  const auth=new google.auth.OAuth2(c.client_id,c.client_secret,c.redirect_uris[0]);auth.setCredentials(token);
  auth.on('tokens',tokens=>{const temp=tokenPath+'.'+process.pid+'.tmp';writeFileSync(temp,JSON.stringify({...token,...auth.credentials,...tokens}),{mode:0o600});renameSync(temp,tokenPath);});
  googleAdapter=new DriveFiles(google.drive({version:'v3',auth}));return googleAdapter;
}
const options={timeout:30000,retry:false,maxContentLength:MAX_FILE_BYTES,maxBodyLength:MAX_FILE_BYTES+65536};
export class DriveFiles {
  constructor(drive){this.drive=drive;this.queue=Promise.resolve();}
  async download(source) {
    const id=fileId(source.drive_file_id);
    const meta=(await this.drive.files.get({fileId:id,fields:'id,name,mimeType,size,md5Checksum,trashed',supportsAllDrives:true},options)).data;
    if(meta.trashed||meta.mimeType==='application/vnd.google-apps.folder')fail('Choose an available ordinary file or exportable Google document.');
    if(Number(meta.size||0)>MAX_FILE_BYTES)fail('Drive source exceeds 20 MiB.');
    const native=meta.mimeType.startsWith('application/vnd.google-apps.');
    const exports={'application/pdf':'.pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document':'.docx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':'.xlsx','application/vnd.openxmlformats-officedocument.presentationml.presentation':'.pptx','text/csv':'.csv','text/plain':'.txt'};
    const mime=native?(source.export_mime_type||'application/pdf'):meta.mimeType;
    if(native&&!exports[mime])fail('Unsupported native document export; choose PDF, Office, CSV or text.');
    const response=native?await this.drive.files.export({fileId:id,mimeType:mime},{...options,responseType:'arraybuffer'}):await this.drive.files.get({fileId:id,alt:'media',supportsAllDrives:true},{...options,responseType:'arraybuffer'});
    const file=fileResult(source.name||meta.name+(native&&!meta.name.toLowerCase().endsWith(exports[mime])?exports[mime]:''),Buffer.from(response.data),mime);
    if(!native&&((meta.size!==undefined&&Number(meta.size)!==file.size)||(meta.md5Checksum&&meta.md5Checksum!==file.md5)))fail('Drive source changed or checksum mismatched; inspect before composing.');
    return file;
  }
  async upload(file,folderId) {
    const previous=this.queue;let release;this.queue=new Promise(r=>{release=r;});await previous;
    try {
      fileId(folderId);
      const folder=(await this.drive.files.get({fileId:folderId,fields:'id,mimeType,parents,trashed,capabilities(canAddChildren)',supportsAllDrives:true},options)).data;
      if(folder.trashed||folder.mimeType!=='application/vnd.google-apps.folder'||folder.capabilities?.canAddChildren===false)fail('Requested Drive folder is unavailable or not writable.');
      const uploadKey=digest(Buffer.from(JSON.stringify([folderId,file.name,file.sha256])));
      const list=(await this.drive.files.list({q:"'"+folderId+"' in parents and trashed = false and appProperties has { key='miliUploadId' and value='"+uploadKey+"' }",fields:'files(id)',pageSize:3,supportsAllDrives:true,includeItemsFromAllDrives:true},options)).data.files||[];
      if(list.length>1)fail('Duplicate upload receipts found; inspect before retrying.');
      let id=list[0]?.id;
      if(!id) {
        try {id=(await this.drive.files.create({requestBody:{name:file.name,mimeType:file.mimeType,parents:[folderId],appProperties:{miliUploadId:uploadKey}},media:{mimeType:file.mimeType,body:Readable.from([file.bytes])},fields:'id',supportsAllDrives:true},options)).data.id;}
        catch {fail('Drive upload outcome uncertain. Retry the same source/name/folder once to inspect the persisted upload receipt; never create a renamed duplicate.');}
      }
      const after=(await this.drive.files.get({fileId:id,fields:'id,name,mimeType,size,md5Checksum,parents,webViewLink,trashed',supportsAllDrives:true},options)).data;
      if(after.trashed||after.name!==file.name||after.mimeType!==file.mimeType||!after.parents?.includes(folderId)||Number(after.size)!==file.size||after.md5Checksum!==file.md5)fail('Drive upload verification failed; inspect before any retry.');
      return {status:list.length?'already_uploaded':'verified',...after,sha256:file.sha256,sharing:'inherited; no permissions changed'};
    } finally {release();}
  }
}
export function makeFileTools(ctx,{workspace=WORKSPACE,catalog=CATALOG,drive,allowedSenders,ready=()=>Promise.resolve()}={}) {
  if(ctx.agentId!=='mili'||!ctx.sessionKey?.startsWith('agent:mili:'))return [];
  return [{name:'mili_drive_upload',label:'Mili Drive binary upload',description:'Upload original bytes from a conversation attachment_id or generated workspace business file to an exact requested Drive folder. For an existing Drive file use gdrive__update_file to move it. Preserves sharing, verifies byte checksum, and deduplicates retries. No OCR/conversion required for upload.',parameters:{type:'object',additionalProperties:false,properties:{source:fileSourceSchema,folder_id:{type:'string'}},required:['source','folder_id']},execute:async(_call,p)=>{
    assertFileRequester(ctx,allowedSenders,workspace);
    await ready();
    if(p.source?.drive_file_id||p.source?.mail_attachment)fail('Use local/catalog originals for this upload; move existing Drive files or save mail attachments first.');
    const adapter=drive||await getDriveAdapter();const file=await resolveFile(p.source,ctx,{workspace,catalog,drive:adapter});
    return {content:[{type:'text',text:JSON.stringify(await adapter.upload(file,p.folder_id))}]};
  }}];
}
