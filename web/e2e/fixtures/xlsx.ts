import { readFile } from "node:fs/promises";
import { inflateRawSync } from "node:zlib";

type ZipInputEntry = {
  name: string;
  data: Buffer;
};

const crc32Table = new Uint32Array(256).map((_, index) => {
  let value = index;
  for (let bit = 0; bit < 8; bit += 1) {
    value = (value & 1) !== 0 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
  }
  return value >>> 0;
});

function crc32(data: Buffer) {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc = crc32Table[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function xmlEscape(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function xmlUnescape(value: string) {
  return value
    .replace(/&quot;/g, "\"")
    .replace(/&gt;/g, ">")
    .replace(/&lt;/g, "<")
    .replace(/&amp;/g, "&");
}

function columnName(index: number) {
  let current = index + 1;
  let name = "";
  while (current > 0) {
    const remainder = (current - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    current = Math.floor((current - 1) / 26);
  }
  return name;
}

function buildSharedStringModel(rows: string[][]) {
  const indexByValue = new Map<string, number>();
  const values: string[] = [];
  const indexedRows = rows.map((row) => row.map((cell) => {
    const existing = indexByValue.get(cell);
    if (existing !== undefined) {
      return existing;
    }
    const nextIndex = values.length;
    indexByValue.set(cell, nextIndex);
    values.push(cell);
    return nextIndex;
  }));
  return { indexedRows, values };
}

function zip(entries: ZipInputEntry[]) {
  const localParts: Buffer[] = [];
  const centralParts: Buffer[] = [];
  let offset = 0;

  for (const entry of entries) {
    const name = Buffer.from(entry.name, "utf8");
    const data = entry.data;
    const entryCrc = crc32(data);

    const localHeader = Buffer.alloc(30);
    localHeader.writeUInt32LE(0x04034b50, 0);
    localHeader.writeUInt16LE(20, 4);
    localHeader.writeUInt16LE(0x0800, 6);
    localHeader.writeUInt16LE(0, 8);
    localHeader.writeUInt16LE(0, 10);
    localHeader.writeUInt16LE(33, 12);
    localHeader.writeUInt32LE(entryCrc, 14);
    localHeader.writeUInt32LE(data.length, 18);
    localHeader.writeUInt32LE(data.length, 22);
    localHeader.writeUInt16LE(name.length, 26);
    localHeader.writeUInt16LE(0, 28);
    localParts.push(localHeader, name, data);

    const centralHeader = Buffer.alloc(46);
    centralHeader.writeUInt32LE(0x02014b50, 0);
    centralHeader.writeUInt16LE(20, 4);
    centralHeader.writeUInt16LE(20, 6);
    centralHeader.writeUInt16LE(0x0800, 8);
    centralHeader.writeUInt16LE(0, 10);
    centralHeader.writeUInt16LE(0, 12);
    centralHeader.writeUInt16LE(33, 14);
    centralHeader.writeUInt32LE(entryCrc, 16);
    centralHeader.writeUInt32LE(data.length, 20);
    centralHeader.writeUInt32LE(data.length, 24);
    centralHeader.writeUInt16LE(name.length, 28);
    centralHeader.writeUInt16LE(0, 30);
    centralHeader.writeUInt16LE(0, 32);
    centralHeader.writeUInt16LE(0, 34);
    centralHeader.writeUInt16LE(0, 36);
    centralHeader.writeUInt32LE(0, 38);
    centralHeader.writeUInt32LE(offset, 42);
    centralParts.push(centralHeader, name);

    offset += localHeader.length + name.length + data.length;
  }

  const centralDirectory = Buffer.concat(centralParts);
  const centralOffset = offset;
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(0, 4);
  end.writeUInt16LE(0, 6);
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(centralDirectory.length, 12);
  end.writeUInt32LE(centralOffset, 16);
  end.writeUInt16LE(0, 20);

  return Buffer.concat([...localParts, centralDirectory, end]);
}

export function createMinimalXlsx(rows: string[][], sheetName = "Sheet1") {
  const { indexedRows, values } = buildSharedStringModel(rows);
  const sharedStringsXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="${rows.flat().length}" uniqueCount="${values.length}">${values.map((value) => `<si><t>${xmlEscape(value)}</t></si>`).join("")}</sst>`;
  const sheetDataXml = indexedRows.map((row, rowIndex) => {
    const cells = row.map((sharedStringIndex, columnIndex) => {
      const ref = `${columnName(columnIndex)}${rowIndex + 1}`;
      return `<c r="${ref}" t="s"><v>${sharedStringIndex}</v></c>`;
    }).join("");
    return `<row r="${rowIndex + 1}">${cells}</row>`;
  }).join("");

  const entries: ZipInputEntry[] = [
    {
      name: "[Content_Types].xml",
      data: Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>`, "utf8"),
    },
    {
      name: "_rels/.rels",
      data: Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`, "utf8"),
    },
    {
      name: "xl/workbook.xml",
      data: Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="${xmlEscape(sheetName)}" sheetId="1" r:id="rId1"/></sheets>
</workbook>`, "utf8"),
    },
    {
      name: "xl/_rels/workbook.xml.rels",
      data: Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`, "utf8"),
    },
    {
      name: "xl/worksheets/sheet1.xml",
      data: Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${sheetDataXml}</sheetData></worksheet>`, "utf8"),
    },
    {
      name: "xl/sharedStrings.xml",
      data: Buffer.from(sharedStringsXml, "utf8"),
    },
    {
      name: "xl/styles.xml",
      data: Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>`, "utf8"),
    },
  ];

  return zip(entries);
}

function readZipEntries(buffer: Buffer) {
  const entries = new Map<string, Buffer>();
  let offset = 0;
  while (offset + 30 <= buffer.length && buffer.readUInt32LE(offset) === 0x04034b50) {
    const flags = buffer.readUInt16LE(offset + 6);
    const method = buffer.readUInt16LE(offset + 8);
    const compressedSize = buffer.readUInt32LE(offset + 18);
    const nameLength = buffer.readUInt16LE(offset + 26);
    const extraLength = buffer.readUInt16LE(offset + 28);
    const nameStart = offset + 30;
    const name = buffer.toString((flags & 0x0800) !== 0 ? "utf8" : "latin1", nameStart, nameStart + nameLength);
    const dataStart = nameStart + nameLength + extraLength;
    const dataEnd = dataStart + compressedSize;
    const compressed = buffer.subarray(dataStart, dataEnd);
    if (method === 0) {
      entries.set(name, compressed);
    } else if (method === 8) {
      entries.set(name, inflateRawSync(compressed));
    } else {
      throw new Error(`Unsupported XLSX zip compression method ${method} for ${name}`);
    }
    offset = dataEnd;
  }
  return entries;
}

function extractSharedStrings(sharedStringsXml: string) {
  return Array.from(sharedStringsXml.matchAll(/<si>([\s\S]*?)<\/si>/g)).map((match) => {
    const textParts = Array.from(match[1].matchAll(/<t(?:\s[^>]*)?>([\s\S]*?)<\/t>/g));
    return textParts.map((textMatch) => xmlUnescape(textMatch[1])).join("");
  });
}

export async function readXlsxText(path: string) {
  const buffer = await readFile(path);
  const entries = readZipEntries(buffer);
  const sharedStrings = extractSharedStrings(entries.get("xl/sharedStrings.xml")?.toString("utf8") ?? "");
  const sheetXml = entries.get("xl/worksheets/sheet1.xml")?.toString("utf8");
  if (!sheetXml) {
    throw new Error("XLSX workbook does not contain xl/worksheets/sheet1.xml");
  }

  return Array.from(sheetXml.matchAll(/<c\b([^>]*)>([\s\S]*?)<\/c>/g)).map((match) => {
    const attributes = match[1];
    const body = match[2];
    const value = body.match(/<v>([\s\S]*?)<\/v>/)?.[1] ?? "";
    if (/\bt="s"/.test(attributes)) {
      return sharedStrings[Number(value)] ?? "";
    }
    const inlineText = body.match(/<t(?:\s[^>]*)?>([\s\S]*?)<\/t>/)?.[1];
    return xmlUnescape(inlineText ?? value);
  }).join("\n");
}
