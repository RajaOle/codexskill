import test from 'node:test';
import assert from 'node:assert/strict';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {extractText} from './index.js';

const exec=promisify(execFile);
// An operator supplies an existing authorized local PDF; no production delivery.
const source=process.env.MILI_OCR_TEST_PDF;
function jpegSize(data) {
  let offset=2;
  while(offset<data.length) {
    if(data[offset++]!==0xff) throw new Error('Invalid JPEG marker');
    const marker=data[offset++],length=data.readUInt16BE(offset);
    if([0xc0,0xc1,0xc2].includes(marker)) return {height:data.readUInt16BE(offset+3),width:data.readUInt16BE(offset+5)};
    offset+=length;
  }
  throw new Error('JPEG size not found');
}
function scanPdf(jpeg) {
  const size=jpegSize(jpeg),parts=[Buffer.from('%PDF-1.4\n')],offsets=[0];
  const objects=[
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /XObject << /Img 4 0 R >> >> /Contents 5 0 R >>',
    Buffer.concat([Buffer.from(`<< /Type /XObject /Subtype /Image /Width ${size.width} /Height ${size.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`),jpeg,Buffer.from('\nendstream')]),
    '<< /Length 31 >>\nstream\nq 595 0 0 842 0 0 cm /Img Do Q\n\nendstream',
  ];
  objects.forEach((body,i)=>{offsets.push(parts.reduce((n,p)=>n+p.length,0));parts.push(Buffer.from(`${i+1} 0 obj\n`),Buffer.isBuffer(body)?body:Buffer.from(body),Buffer.from('\nendobj\n'));});
  const xref=parts.reduce((n,p)=>n+p.length,0);
  parts.push(Buffer.from(`xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map(o=>String(o).padStart(10,'0')+' 00000 n ').join('\n')}\ntrailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`));
  return Buffer.concat(parts);
}

test('real image OCR and image-only PDF OCR extract readable text',{skip:!source},async()=>{
  const temp=await mkdtemp(path.join(os.tmpdir(),'mili-ocr-integration-'));
  try {
    const prefix=path.join(temp,'source');
    await exec('/usr/bin/pdftoppm',['-f','1','-l','1','-singlefile','-scale-to','1800','-jpeg',source,prefix],{timeout:45000});
    const image=await extractText(prefix+'.jpg');
    assert.equal(image.mode,'image-local-ocr');assert.ok(image.text.trim().length>100);
    const scan=path.join(temp,'scan.pdf');await writeFile(scan,scanPdf(await readFile(prefix+'.jpg')));
    const result=await extractText(scan);
    assert.equal(result.mode,'pdf-text-and-local-ocr');assert.ok(result.text.trim().length>100);assert.equal(result.partial,false);
  } finally {await rm(temp,{recursive:true,force:true});}
});
