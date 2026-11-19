// Builds Seminar_Report.docx in the FRCRCE seminar-report layout (front matter, chapters 1-8, references, appendix).
// Usage: node docs/seminar/build_report.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, ImageRun, PageBreak, Footer, PageNumber, NumberFormat, TableOfContents, LevelFormat, SectionType, TabStopType,
} = require("docx");
const C = require("./content.js");

const FONT = "Times New Roman";
const A4 = { width: 11906, height: 16838 };
const MARGIN = { top: 1440, bottom: 1440, left: 1440, right: 1440 };
const CONTENT_W = A4.width - MARGIN.left - MARGIN.right; // 9026
const FIG = path.join(__dirname, "figures");

// ---- helpers --------------------------------------------------------------------------------------------------
function runs(text, base = {}) {
  const out = [];
  text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/).forEach((part) => {
    if (!part) return;
    if (part.startsWith("**")) out.push(new TextRun({ text: part.slice(2, -2), bold: true, font: FONT, ...base }));
    else if (part.startsWith("*")) out.push(new TextRun({ text: part.slice(1, -1), italics: true, font: FONT, ...base }));
    else out.push(new TextRun({ text: part, font: FONT, ...base }));
  });
  return out;
}
const body = (text) => new Paragraph({ children: runs(text, { size: 24 }), alignment: AlignmentType.JUSTIFIED, spacing: { line: 360, after: 120 } });
const centered = (text, o = {}) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: o.after ?? 120, before: o.before ?? 0, line: o.line ?? 276 },
  children: [new TextRun({ text, font: FONT, size: o.size ?? 24, bold: !!o.bold, italics: !!o.italics, allCaps: !!o.caps })] });
const blank = (n = 1) => Array.from({ length: n }, () => new Paragraph({ children: [new TextRun({ text: "", font: FONT })] }));
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });

const chapterHeading = (n, title, newPage = true) => [
  new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: newPage, alignment: AlignmentType.CENTER, children: [new TextRun({ text: `Chapter ${n}: ${title}`, font: FONT })] }),
];
const h2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: t, font: FONT })] });
const h3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: t, font: FONT })] });
const bullets = (items) => items.map((t) => new Paragraph({ numbering: { reference: "bul", level: 0 }, alignment: AlignmentType.JUSTIFIED, spacing: { line: 336, after: 80 }, children: runs(t, { size: 24 }) }));
const numbered = (items, ref) => items.map((t) => new Paragraph({ numbering: { reference: ref, level: 0 }, alignment: AlignmentType.JUSTIFIED, spacing: { line: 336, after: 80 }, children: runs(t, { size: 24 }) }));

const border = { style: BorderStyle.SINGLE, size: 4, color: "808080" };
const borders = { top: border, bottom: border, left: border, right: border };
function table(spec) {
  const total = spec.cols.reduce((a, b) => a + b, 0);
  const cell = (t, w, head) => new TableCell({
    width: { size: w, type: WidthType.DXA }, borders, margins: { top: 60, bottom: 60, left: 90, right: 90 },
    shading: head ? { fill: "D9E2F3", type: ShadingType.CLEAR, color: "auto" } : undefined,
    children: [new Paragraph({ children: runs(t, { size: 20, bold: !!head }) })],
  });
  return [
    new Paragraph({ keepNext: true, alignment: AlignmentType.CENTER, spacing: { before: 200, after: 80 }, children: [new TextRun({ text: spec.caption, font: FONT, size: 22, bold: true })] }),
    new Table({
      width: { size: total, type: WidthType.DXA }, columnWidths: spec.cols,
      rows: [new TableRow({ tableHeader: true, cantSplit: true, children: spec.head.map((h, i) => cell(h, spec.cols[i], true)) }),
        ...spec.rows.map((r) => new TableRow({ cantSplit: true, children: r.map((t, i) => cell(t, spec.cols[i], false)) }))],
    }),
    new Paragraph({ spacing: { after: 160 }, children: [] }),
  ];
}
function figure(f) {
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 160, after: 60 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(path.join(FIG, f.file)), transformation: { width: f.w, height: f.h },
        altText: { title: f.caption, description: f.caption, name: f.file } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 }, children: [new TextRun({ text: f.caption, font: FONT, size: 22, italics: true })] }),
  ];
}
function blocks(list, counter) {
  const out = [];
  list.forEach((b) => {
    if (b.p) out.push(body(b.p));
    else if (b.h2) out.push(h2(b.h2));
    else if (b.h3) out.push(h3(b.h3));
    else if (b.bullets) out.push(...bullets(b.bullets));
    else if (b.numbered) { counter.n += 1; out.push(...numbered(b.numbered, "num" + counter.n)); }
    else if (b.table) out.push(...table(b.table));
    else if (b.figure) out.push(...figure(b.figure));
  });
  return out;
}

// ---- front matter -----------------------------------------------------------------------------------------------
const cover = [
  ...blank(2),
  centered(C.TITLE, { size: 36, bold: true, before: 240, after: 360, line: 360 }),
  centered("A Course Seminar report submitted in partial fulfillment of the requirements for the degree of", { size: 24, after: 240 }),
  centered("Bachelor of Technology", { size: 28, bold: true, after: 120 }),
  centered("In", { size: 24, after: 120 }),
  centered("Computer Engineering", { size: 28, bold: true, after: 360 }),
  centered("by", { size: 24, after: 120 }),
  centered(`${C.STUDENT} (${C.ROLL})`, { size: 26, bold: true, after: 360 }),
  centered("Under the guidance of", { size: 24, after: 120 }),
  centered(C.GUIDE, { size: 26, bold: true, after: C.GUIDE_DESIG ? 60 : 480 }),
  ...(C.GUIDE_DESIG ? [centered(`(${C.GUIDE_DESIG})`, { size: 24, after: 480 })] : []),
  centered("DEPARTMENT OF COMPUTER ENGINEERING", { size: 26, bold: true, after: 120 }),
  centered("Fr. Conceicao Rodrigues College of Engineering, Bandra (W), Mumbai - 400050", { size: 24, after: 60 }),
  centered("University of Mumbai", { size: 24, after: 60 }),
  centered("(2026 - 27)", { size: 24 }),
];

const titleOf = (t) => centered(t, { size: 28, bold: true, after: 240, before: 120, caps: false });
const approvalSheet = [
  titleOf("Internal Approval Sheet"), titleOf("CERTIFICATE"),
  body(`This is to certify that the course seminar entitled "${C.TITLE}" is a bonafide work of ${C.STUDENT} (${C.ROLL}) submitted to the University of Mumbai in partial fulfillment of the requirement for the award of the degree of Bachelor in Computer Engineering.`),
  ...blank(3),
  new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "(Name and sign)", font: FONT, size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "Supervisor/Guide", font: FONT, size: 24 })] }),
  ...blank(3),
  new Paragraph({ tabStops: [{ type: TabStopType.CENTER, position: 4500 }, { type: TabStopType.RIGHT, position: 9000 }],
    children: [new TextRun({ text: "(Dr. Sujata Deshmukh)\tDr. Sapna Prabhu", font: FONT, size: 24 }),
      new TextRun({ text: "", font: FONT })] }),
  new Paragraph({ tabStops: [{ type: TabStopType.CENTER, position: 4500 }, { type: TabStopType.RIGHT, position: 9000 }],
    children: [new TextRun({ text: "Head of Department\tPrincipal", font: FONT, size: 24 })] }),
];
const approval = [
  titleOf("Approval Sheet"), titleOf("Seminar Report Approval"),
  body(`This Seminar report entitled "${C.TITLE}" by ${C.STUDENT}, is approved for the degree of Bachelor of Engineering in Computer Engineering.`),
  ...blank(3),
  body("Examiner 1. ------------------------------------------"),
  ...blank(2), body("Date:"), body("Place:"),
];
const declaration = [
  titleOf("Declaration"),
  body("I declare that this written submission represents my ideas in my own words and where others' ideas or words have been included, I have adequately cited and referenced the original sources. I also declare that I have adhered to all principles of academic honesty and integrity and have not misrepresented or fabricated or falsified any idea/data/fact/source in my submission. I understand that any violation of the above will be cause for disciplinary action by the Institute and can also evoke penal action from the sources which have thus not been properly cited or from whom proper permission has not been taken when needed."),
  ...blank(3),
  new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: `${C.STUDENT} (${C.ROLL}) (sign)`, font: FONT, size: 24 })] }),
  body("Date:"),
];
const abstractPage = [
  titleOf("Abstract"),
  ...C.abstract.map(body),
  new Paragraph({ spacing: { before: 120 }, children: [new TextRun({ text: "Keywords: ", bold: true, font: FONT, size: 24 }), new TextRun({ text: C.keywords, italics: true, font: FONT, size: 24 })] }),
];
const ack = [
  titleOf("Acknowledgments"),
  body(`I have great pleasure in presenting the report on "${C.TITLE}". I take this opportunity to express my sincere thanks towards the guide ${C.GUIDE}, C.R.C.E, Bandra (W), Mumbai, for providing the technical guidelines and the suggestions regarding the line of this work. I enjoyed discussing the work progress during our visits to the department.`),
  body("I thank Dr. Sujata Deshmukh, Head of Computer Engineering department, the Principal and the management of C.R.C.E., Mumbai for encouragement and providing necessary support for the seminar."),
  body("I also thank all non-teaching staff for their valuable support to complete my seminar."),
  ...blank(2),
  new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: `${C.STUDENT} (${C.ROLL})`, font: FONT, size: 24 })] }),
  body("Date:"),
];

// figure and table lists (captions pulled from the content so they cannot drift from the body)
const figs = [], tabs = [];
const CHAPTERS = require("./chapters.js").chapters; // condensed chapters 1-8 (content.js keeps the longer draft)
CHAPTERS.forEach((ch) => ch.blocks.forEach((b) => { if (b.figure) figs.push(b.figure.caption); if (b.table) tabs.push(b.table.caption); }));
const listPage = (title, items) => [
  titleOf(title),
  ...items.map((t) => new Paragraph({ spacing: { after: 100, line: 300 }, children: [new TextRun({ text: t, font: FONT, size: 24 })] })),
];
const glossary = [
  titleOf("Glossary"),
  ...C.glossary.map(([a, b]) => new Paragraph({ spacing: { after: 90, line: 300 }, children: [new TextRun({ text: a + ": ", bold: true, font: FONT, size: 24 }), new TextRun({ text: b, font: FONT, size: 24 })] })),
];
const contents = [
  titleOf("Contents"),
  new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }),
];

// ---- main matter -----------------------------------------------------------------------------------------------
const counter = { n: 0 };
const main = [];
CHAPTERS.forEach((ch, i) => { main.push(...chapterHeading(i + 1, ch.title, i > 0)); main.push(...blocks(ch.blocks, counter)); });
main.push(new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "References", font: FONT })] }));
C.references.forEach((r, i) => main.push(new Paragraph({ spacing: { after: 100, line: 300 }, indent: { left: 540, hanging: 540 }, alignment: AlignmentType.JUSTIFIED,
  children: [new TextRun({ text: `[${i + 1}]\t`, font: FONT, size: 22 }), new TextRun({ text: r, font: FONT, size: 22 })], tabStops: [{ type: TabStopType.LEFT, position: 540 }] })));
main.push(new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Appendix A", font: FONT })] }));
main.push(...blocks(C.appendix, counter));

// ---- document ---------------------------------------------------------------------------------------------------
const footer = (fmt) => ({ default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 22 })] })] }) });
const numberingConfig = [{ reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] }];
for (let i = 1; i <= counter.n; i++) numberingConfig.push({ reference: "num" + i, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] });

const doc = new Document({
  creator: C.STUDENT, title: C.TITLE, description: "Course seminar report, Sem VII, Computer Engineering, FRCRCE",
  features: { updateFields: true },
  styles: {
    default: { document: { run: { font: FONT, size: 24 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 32, bold: true }, paragraph: { spacing: { before: 240, after: 160 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 28, bold: true }, paragraph: { spacing: { before: 280, after: 120 }, keepNext: true, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 25, bold: true, italics: true }, paragraph: { spacing: { before: 200, after: 100 }, keepNext: true, outlineLevel: 2 } },
    ],
  },
  numbering: { config: numberingConfig },
  sections: [
    { properties: { page: { size: A4, margin: MARGIN } }, children: cover },
    { properties: { type: SectionType.NEXT_PAGE, page: { size: A4, margin: MARGIN, pageNumbers: { start: 1, formatType: NumberFormat.LOWER_ROMAN } } }, footers: footer(),
      children: [...approvalSheet, pageBreak(), ...approval, pageBreak(), ...declaration, pageBreak(), ...abstractPage, pageBreak(), ...ack, pageBreak(), ...contents,
        pageBreak(), ...listPage("List of Figures", figs), pageBreak(), ...listPage("List of Tables", tabs), pageBreak(), ...glossary] },
    { properties: { type: SectionType.NEXT_PAGE, page: { size: A4, margin: MARGIN, pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL } } }, footers: footer(), children: main },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  const out = path.join(__dirname, "Seminar_Report.docx");
  fs.writeFileSync(out, buf);
  console.log("wrote", out, buf.length, "bytes; figures:", figs.length, "tables:", tabs.length);
});
