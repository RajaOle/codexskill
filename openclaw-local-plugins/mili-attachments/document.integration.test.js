import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {extractText} from './index.js';

test('RTF converts locally with macros disabled; text chunks continue',async()=>{
  const temp=await mkdtemp(path.join(os.tmpdir(),'mili-document-test-'));
  try {
    const file=path.join(temp,'sample.rtf');
    await writeFile(file,'{\\rtf1\\ansi BSI trade finance. Bank Mandiri contact list for internal operations. This document contains enough readable text for direct PDF extraction.}');
    const result=await extractText(file);
    assert.match(result.mode,/office-converted/);assert.match(result.text,/BSI trade finance/);
    const text=path.join(temp,'long.txt');await writeFile(text,'x'.repeat(40020)+'END');
    const first=await extractText(text),second=await extractText(text,{startChar:first.nextChar});
    assert.equal(first.nextChar,40000);assert.match(second.text,/END$/);assert.equal(second.nextChar,null);
  } finally {await rm(temp,{recursive:true,force:true});}
});
