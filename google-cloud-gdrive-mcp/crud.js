import { Readable } from "node:stream";
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const documentTypes = {
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document':'.docx',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':'.xlsx',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation':'.pptx',
  'application/vnd.ms-word.document.macroEnabled.12':'.docm',
  'application/vnd.ms-excel.sheet.macroEnabled.12':'.xlsm',
  'application/vnd.ms-powerpoint.presentation.macroEnabled.12':'.pptm',
  'application/msword':'.doc','application/vnd.ms-excel':'.xls','application/vnd.ms-powerpoint':'.ppt',
  'application/vnd.oasis.opendocument.text':'.odt','application/vnd.oasis.opendocument.spreadsheet':'.ods','application/vnd.oasis.opendocument.presentation':'.odp',
  'application/rtf':'.rtf','text/rtf':'.rtf',
};
async function extractDownload(data, mime, args) {
  const temp=await mkdtemp(path.join(os.tmpdir(),'mili-drive-document-'));
  try {
    const extensions={...documentTypes,'application/pdf':'.pdf','image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp','image/tiff':'.tif'};
    const file=path.join(temp,'document'+(extensions[mime]||'.txt'));
    await writeFile(file,data,{mode:0o600});
    const reader=process.env.MILI_DOCUMENT_READER || '/home/olekamole/.openclaw/local-plugins/mili-attachments/index.js';
    const {extractText}=await import(pathToFileURL(reader).href);
    return await extractText(file,{startPage:args.start_page??1,startChar:args.start_char??0});
  } finally {await rm(temp,{recursive:true,force:true});}
}

const string = { type: "string" };
const tool = (name, description, properties, required) => ({
  name, description, inputSchema: { type: "object", properties, required, additionalProperties: false }
});

export const crudTools = [
  tool("sheet_metadata", "Read workbook tab names, numeric sheet IDs, and grid sizes for structural edits.",
    { fileId: string }, ["fileId"]),
  tool("create_file", "Create a private Drive file or folder from inline text. Inherits parent sharing; never enables public sharing.",
    { name: string, folderId: string, mimeType: string, content: string }, ["name"]),
  tool("read_file", "Read Drive metadata and permissions, optionally download content or export a Google document. Binary content is returned as base64.",
    { fileId: string, content: { type: "boolean" }, exportMimeType: string }, ["fileId"]),
  tool('read_document','Extract readable text from an exact Drive document: Office/OpenDocument, legacy Office/RTF, PDF/scans/images or text. No manual conversion needed. Continue with start_page=nextPage or start_char=nextChar.',
    {fileId:string,start_page:{type:'integer',minimum:1},start_char:{type:'integer',minimum:0}},['fileId']),
  tool("update_file", "Rename, move, or replace text content of an existing Drive file without changing sharing.",
    { fileId: string, name: string, folderId: string, content: string, mimeType: string }, ["fileId"]),
  tool("delete_file", "Delete an explicitly authorized Drive file. Default moves to trash; permanent=true irreversibly deletes it.",
    { fileId: string, permanent: { type: "boolean" } }, ["fileId"]),
  tool("create_spreadsheet", "Create a new Google Sheets workbook with optional named tabs. Sharing remains private.",
    { title: string, tabs: { type: "array", items: string, minItems: 1 } }, ["title"]),
  tool("batch_update_sheet", "Modify spreadsheet structure, formatting, rows, columns or tabs using Google Sheets batchUpdate requests. Delete requests require explicit user authorization.",
    { fileId: string, requests: { type: "array", minItems: 1, items: { type: "object" } } }, ["fileId", "requests"]),
  tool("clear_sheet_range", "Clear values in an explicitly authorized spreadsheet range while preserving formatting.",
    { fileId: string, range: string }, ["fileId", "range"])
];

const result = data => ({ content: [{ type: "text", text: JSON.stringify(data, null, 2) }] });
const fileFields = "id,name,mimeType,parents,webViewLink,trashed,capabilities";
const inlineTextMime = mime => /^(?:text\/|application\/(?:json|xml)$)/i.test(mime||'text/plain');
const misleadingBinaryPath = args => /\.(?:jpe?g|png|pdf|docx?|xlsx?|pptx?|zip)$/i.test(args.name||'') && typeof args.content==='string' && /^(?:\/home\/|\/tmp\/|file:\/\/)[^\r\n]+$/.test(args.content.trim());

export async function handleCrudTool(name, args, { drive, sheets }) {
  const definition = crudTools.find(item => item.name === name);
  if (!definition) return null;
  for (const key of definition.inputSchema.required) {
    if (args?.[key] === undefined || args[key] === "") throw new Error(`Missing required argument: ${key}`);
  }
  if (name === "sheet_metadata") {
    const res = await sheets.spreadsheets.get({ spreadsheetId: args.fileId, fields: "spreadsheetId,spreadsheetUrl,properties,sheets.properties" });
    return result(res.data);
  }
  if (name === "create_file") {
    const nativeDocument=args.mimeType==='application/vnd.google-apps.document';
    if(args.content!==undefined && (typeof args.content!=='string'||(!inlineTextMime(args.mimeType)&&!nativeDocument)||misleadingBinaryPath(args)))throw new Error('create_file supports inline text only (including a NEW Google Doc from text). For binary files use the enabled attachment upload tool; never supply a local path as content.');
    const res = await drive.files.create({
      requestBody: { name: args.name, mimeType: args.mimeType || "text/plain", parents: args.folderId ? [args.folderId] : undefined },
      ...(args.content !== undefined ? { media: { mimeType: nativeDocument ? 'text/plain' : args.mimeType || "text/plain", body: Readable.from([args.content]) } } : {}),
      fields: fileFields, supportsAllDrives: true
    });
    return result(res.data);
  }
  if (name === "read_file" || name === 'read_document') {
    const meta = await drive.files.get({ fileId: args.fileId, fields: fileFields, supportsAllDrives: true });
    if (!args.content && name !== 'read_document') return result(meta.data);
    const mimeType = meta.data.mimeType;
    if(name==='read_document' && mimeType==='application/vnd.google-apps.spreadsheet')throw new Error('Use focused read_sheet_range for native Google Sheets.');
    if (mimeType === "application/vnd.google-apps.folder") throw new Error("Folders have no downloadable content; use list_files.");
    const native = mimeType.startsWith("application/vnd.google-apps.");
    const exportType = args.exportMimeType || (mimeType === "application/vnd.google-apps.spreadsheet" ? "text/csv" : "text/plain");
    const res = native
      ? await drive.files.export({ fileId: args.fileId, mimeType: exportType }, { responseType: "arraybuffer" })
      : await drive.files.get({ fileId: args.fileId, alt: "media", supportsAllDrives: true }, { responseType: "arraybuffer", maxContentLength:20*1024*1024 });
    const data = Buffer.from(res.data);
    if(name==='read_document' || documentTypes[mimeType]) {
      if(data.length>20*1024*1024)throw new Error('Document exceeds 20 MiB extraction limit.');
      if(!native && !documentTypes[mimeType] && !/^(?:text\/|image\/|application\/(?:pdf|json|xml)$)/.test(mimeType))throw new Error('Unsupported document MIME type: '+mimeType);
      return result({...meta.data,extraction:await extractDownload(data,native?exportType:mimeType,args)});
    }
    if (data.length > 5 * 1024 * 1024) throw new Error("Content exceeds 5 MiB response limit; use focused Sheet ranges or read_document.");
    const type = native ? exportType : mimeType;
    const encoding = /^(text\/|application\/(json|xml))/.test(type) ? "utf8" : "base64";
    return result({ ...meta.data, contentMimeType: type, encoding, content: data.toString(encoding) });
  }
  if (name === "update_file") {
    if(args.mimeType?.startsWith('application/vnd.google-apps.'))throw new Error('update_file cannot convert existing files to Google Workspace types. Create a NEW Google Doc using create_file with inline text; a rename does not convert it.');
    if (args.name === undefined && args.folderId === undefined && args.content === undefined) throw new Error("Provide name, folderId, or content to update.");
    if(args.content!==undefined) {
      if(typeof args.content!=='string'||!inlineTextMime(args.mimeType)||misleadingBinaryPath(args))throw new Error('update_file accepts inline text only; upload original binary bytes with the attachment tool.');
      const original=await drive.files.get({fileId:args.fileId,fields:'mimeType',supportsAllDrives:true});
      if(!inlineTextMime(original.data.mimeType))throw new Error('Existing binary file cannot be replaced with inline text/path content. Upload the requested original separately.');
    }
    let parents;
    if (args.folderId) {
      const meta = await drive.files.get({ fileId: args.fileId, fields: "parents", supportsAllDrives: true });
      parents = meta.data.parents || [];
    }
    const res = await drive.files.update({
      fileId: args.fileId, requestBody: args.name !== undefined ? { name: args.name } : {},
      ...(parents ? { addParents: args.folderId, removeParents: parents.join(",") } : {}),
      ...(args.content !== undefined ? { media: { mimeType: args.mimeType || "text/plain", body: Readable.from([args.content]) } } : {}),
      fields: fileFields, supportsAllDrives: true
    });
    return result(res.data);
  }
  if (name === "delete_file") {
    if (args.permanent === true) {
      await drive.files.delete({ fileId: args.fileId, supportsAllDrives: true });
      return result({ fileId: args.fileId, permanentlyDeleted: true });
    }
    const res = await drive.files.update({ fileId: args.fileId, requestBody: { trashed: true }, fields: "id,trashed", supportsAllDrives: true });
    return result(res.data);
  }
  if (name === "create_spreadsheet") {
    const res = await sheets.spreadsheets.create({ requestBody: {
      properties: { title: args.title },
      ...(args.tabs ? { sheets: args.tabs.map(title => ({ properties: { title } })) } : {})
    } });
    return result(res.data);
  }
  if (name === "batch_update_sheet") {
    if (!Array.isArray(args.requests) || !args.requests.length) throw new Error("requests must be a nonempty array.");
    const res = await sheets.spreadsheets.batchUpdate({ spreadsheetId: args.fileId, requestBody: { requests: args.requests } });
    return result(res.data);
  }
  if (name === "clear_sheet_range") {
    const res = await sheets.spreadsheets.values.clear({ spreadsheetId: args.fileId, range: args.range, requestBody: {} });
    return result(res.data);
  }
}
