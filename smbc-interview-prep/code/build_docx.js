// build_docx.js — converts content.md (a restricted Markdown) into a styled Word document.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, AlignmentType, ImageRun, LevelFormat,
  PageBreak, TableOfContents, Footer, PageNumber, Header, LineRuleType,
} = require("docx");

const SRC = process.argv[2] || "content.md";
const OUT = process.argv[3] || "out.docx";
const lines = fs.readFileSync(SRC, "utf8").split("\n");

const FONT = "Calibri";
const MONO = "Consolas";
const ACCENT = "1F4E79";
const TABLE_W = 9026; // A4 with 1" margins (11906 - 2*1440)

// ---------- inline parsing: **bold**, *italic*, `code`, [text](url) ----------
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*|\[[^\]]+\]\([^)]+\))/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else if (t.startsWith("`")) out.push(new TextRun({ text: t.slice(1, -1), font: MONO, size: 19, color: "7A2E0E", ...base }));
    else if (t.startsWith("[")) {
      const mm = t.match(/\[([^\]]+)\]\(([^)]+)\)/);
      out.push(new TextRun({ text: `${mm[1]} (${mm[2]})`, color: "1F4E79", ...base }));
    } else out.push(new TextRun({ text: t.slice(1, -1), italics: true, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}

// ---------- blocks ----------
const children = [];
let numInstance = 0;
let inNumbered = false;

function flushNumbered() { inNumbered = false; }

function tableFrom(rows) {
  const cells = rows.map(r => r.replace(/^\|/, "").replace(/\|\s*$/, "").split("|").map(c => c.trim()));
  const header = cells[0];
  const body = cells.slice(2); // skip separator
  const n = header.length;
  // column widths proportional to max content length (bounded)
  const lens = header.map((_, i) => Math.min(60, Math.max(8, ...cells.filter((_, k) => k !== 1).map(r => (r[i] || "").length))));
  const total = lens.reduce((a, b) => a + b, 0);
  const minW = header.map((_, i) => Math.max(...cells.filter((_, k) => k !== 1).map(r => Math.max(0, ...((r[i] || '').replace(/[*`]/g,'').split(/\s+/).map(w => w.length))))) * 105 + 240);
  let widths = lens.map(l => Math.round((l / total) * TABLE_W));
  for (let pass = 0; pass < 3; pass++) {
    const short = widths.map((w, k) => Math.max(0, minW[k] - w));
    const need = short.reduce((a, b) => a + b, 0);
    if (!need) break;
    const donors = widths.map((w, k) => (short[k] ? 0 : Math.max(0, w - minW[k])));
    const pool = donors.reduce((a, b) => a + b, 0) || 1;
    widths = widths.map((w, k) => short[k] ? minW[k] : Math.round(w - donors[k] * Math.min(1, need / pool)));
  }
  widths[n - 1] += TABLE_W - widths.reduce((a, b) => a + b, 0);
  const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
  const borders = { top: border, bottom: border, left: border, right: border };
  const mk = (row, isHead) => new TableRow({
    tableHeader: isHead,
    children: row.map((c, i) => new TableCell({
      width: { size: widths[i], type: WidthType.DXA },
      borders,
      shading: isHead ? { type: ShadingType.CLEAR, color: "auto", fill: "1F4E79" } : undefined,
      margins: { top: 60, bottom: 60, left: 100, right: 100 },
      children: [new Paragraph({
        spacing: { before: 0, after: 0 },
        children: runs(c || "", isHead ? { bold: true, color: "FFFFFF", size: 19 } : { size: 19 }),
      })],
    })),
  });
  return new Table({
    width: { size: TABLE_W, type: WidthType.DXA },
    columnWidths: widths,
    rows: [mk(header, true), ...body.map(r => mk(r, false))],
  });
}

let i = 0;
while (i < lines.length) {
  const line = lines[i];
  const t = line.trim();

  if (t === "") { i++; continue; }

  if (t === "\\pagebreak") {
    flushNumbered();
    children.push(new Paragraph({ children: [new PageBreak()] }));
    i++; continue;
  }
  if (t === "\\toc") {
    children.push(new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }));
    i++; continue;
  }
  const title = t.match(/^\\title (.+)$/);
  if (title) {
    children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 2400, after: 240 },
      children: [new TextRun({ text: title[1], bold: true, size: 56, color: ACCENT, font: FONT })] }));
    i++; continue;
  }
  const subtitle = t.match(/^\\subtitle (.+)$/);
  if (subtitle) {
    children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 160 },
      children: [new TextRun({ text: subtitle[1], size: 28, color: "595959", font: FONT })] }));
    i++; continue;
  }

  // code fence
  if (t.startsWith("```")) {
    flushNumbered();
    const code = [];
    i++;
    while (i < lines.length && !lines[i].trim().startsWith("```")) { code.push(lines[i]); i++; }
    i++;
    const shade = { type: ShadingType.CLEAR, color: "auto", fill: "F4F4F4" };
    code.forEach((cl, k) => children.push(new Paragraph({
      shading: shade,
      spacing: { before: k === 0 ? 120 : 0, after: k === code.length - 1 ? 120 : 0, line: 240 },
      indent: { left: 120, right: 120 },
      children: [new TextRun({ text: cl.length ? cl : " ", font: MONO, size: 16 })],
    })));
    continue;
  }

  // image
  const img = t.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
  if (img) {
    flushNumbered();
    const file = img[2];
    const buf = fs.readFileSync(file);
    const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
    const dispW = 560, dispH = Math.round(dispW * h / w);
    const maxH = 780;
    const scale = dispH > maxH ? maxH / dispH : 1;
    children.push(new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120, after: 60, line: 240, lineRule: LineRuleType.AUTO },
      children: [new ImageRun({ type: "png", data: buf, transformation: { width: Math.round(dispW * scale), height: Math.round(dispH * scale) },
        altText: { title: img[1], description: img[1], name: path.basename(file) } })] }));
    if (img[1]) children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
      children: [new TextRun({ text: img[1], italics: true, size: 18, color: "595959" })] }));
    i++; continue;
  }

  // table
  if (t.startsWith("|")) {
    flushNumbered();
    const rows = [];
    while (i < lines.length && lines[i].trim().startsWith("|")) { rows.push(lines[i].trim()); i++; }
    children.push(tableFrom(rows));
    children.push(new Paragraph({ spacing: { after: 120 }, children: [] }));
    continue;
  }

  // headings
  const h = t.match(/^(#{1,4}) (.+)$/);
  if (h) {
    flushNumbered();
    const level = [HeadingLevel.HEADING_1, HeadingLevel.HEADING_2, HeadingLevel.HEADING_3, HeadingLevel.HEADING_4][h[1].length - 1];
    children.push(new Paragraph({ heading: level, children: runs(h[2]) }));
    i++; continue;
  }

  // blockquote
  if (t.startsWith(">")) {
    flushNumbered();
    const q = [];
    while (i < lines.length && lines[i].trim().startsWith(">")) { q.push(lines[i].trim().replace(/^>\s?/, "")); i++; }
    children.push(new Paragraph({
      style: "Quote",
      children: runs(q.join(" ")),
    }));
    continue;
  }

  // bullets (indent by 2 spaces per level)
  const b = line.match(/^(\s*)[-*] (.+)$/);
  if (b) {
    const level = Math.min(2, Math.floor(b[1].length / 2));
    children.push(new Paragraph({ numbering: { reference: "bullets", level }, spacing: { after: 60 }, children: runs(b[2]) }));
    i++; continue;
  }

  // numbered
  const n = line.match(/^(\s*)\d+\. (.+)$/);
  if (n) {
    const level = Math.min(1, Math.floor(n[1].length / 2));
    if (!inNumbered && level === 0) { numInstance++; inNumbered = true; }
    children.push(new Paragraph({ numbering: { reference: "numbers", level, instance: numInstance }, spacing: { after: 60 }, children: runs(n[2]) }));
    i++; continue;
  }

  // paragraph (join continuation lines)
  flushNumbered();
  const para = [t];
  i++;
  while (i < lines.length && lines[i].trim() !== "" && !/^(#|>|\||```|!\[|\s*[-*] |\s*\d+\. |\\)/.test(lines[i])) {
    para.push(lines[i].trim()); i++;
  }
  children.push(new Paragraph({ spacing: { after: 120 }, children: runs(para.join(" ")) }));
}

const doc = new Document({
  creator: "Kwet",
  title: "SMBC Head of AI Engineering — Interview Preparation",
  features: { updateFields: true },
  styles: {
    default: { document: { run: { font: FONT, size: 21 }, paragraph: { spacing: { line: 276, lineRule: LineRuleType.AUTO } } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, color: ACCENT, font: FONT }, paragraph: { spacing: { before: 360, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, color: ACCENT, font: FONT }, paragraph: { spacing: { before: 300, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, color: "2E75B6", font: FONT }, paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 2 } },
      { id: "Heading4", name: "Heading 4", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, color: "404040", font: FONT }, paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 3 } },
      { id: "Quote", name: "Quote", basedOn: "Normal", next: "Normal",
        run: { italics: true, color: "1F3864" },
        paragraph: { indent: { left: 360, right: 360 }, spacing: { before: 120, after: 160 },
          border: { left: { style: BorderStyle.SINGLE, size: 18, color: "2E75B6", space: 8 } },
          shading: { type: ShadingType.CLEAR, color: "auto", fill: "EAF1FB" } } },
    ],
  },
  numbering: {
    config: [
      { reference: "bullets", levels: [
        { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 260 } } } },
        { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 260 } } } },
        { level: 2, format: LevelFormat.BULLET, text: "◦", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 1080, hanging: 260 } } } },
      ] },
      { reference: "numbers", levels: [
        { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 300 } } } },
        { level: 1, format: LevelFormat.LOWER_LETTER, text: "%2)", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 300 } } } },
      ] },
    ],
  },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
      children: [new TextRun({ text: "SMBC Head of AI Engineering — Interview Preparation", size: 16, color: "808080" })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: ["Page ", PageNumber.CURRENT, " of ", PageNumber.TOTAL_PAGES], size: 16, color: "808080" })] })] }) },
    children,
  }],
});

Packer.toBuffer(doc).then(buf => { fs.writeFileSync(OUT, buf); console.log("wrote", OUT); });
