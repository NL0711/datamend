// Builds Project_Report.docx in the FRCRCE project-report template layout.
// Usage: NODE_PATH=<dir with docx> node docs/project/build_report.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, ImageRun, PageBreak, Footer, PageNumber, NumberFormat, TableOfContents, LevelFormat, SectionType, TabStopType,
} = require("docx");
const C = require("./content.js");

const FONT = "Times New Roman";
const A4 = { width: 11906, height: 16838 };
// Template text block: 160 mm wide, 30 mm left (binding) margin, 20 mm right, 22 mm bottom
const MARGIN = { top: 1134, bottom: 1247, left: 1701, right: 1134 };
const TEXT_W = A4.width - MARGIN.left - MARGIN.right; // 9071 twips
const FIG = path.join(__dirname, "figures");
const NAMES = C.STUDENTS.map(([n, r]) => `${n} (${r})`);

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
const body = (text) => new Paragraph({ children: runs(text, { size: 24 }), alignment: AlignmentType.JUSTIFIED, spacing: { line: 360, after: 100 } });
const centered = (text, o = {}) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: o.after ?? 120, before: o.before ?? 0, line: o.line ?? 276 },
  children: [new TextRun({ text, font: FONT, size: o.size ?? 24, bold: !!o.bold, italics: !!o.italics })] });
const blank = (n = 1) => Array.from({ length: n }, () => new Paragraph({ children: [new TextRun({ text: "", font: FONT })] }));
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });

// Template: each chapter starts on a fresh page with an extra top margin; "Chapter N" and the title are centred, bold, 18 pt,
// with a gap of about 12 mm before the first paragraph. One Heading 1 paragraph, so the contents list shows one line per chapter.
const CHAPTER_TOP = 1300; // twips of extra top space (template asks for about 75 mm; reduced to respect the 15-page limit)
const chapterHeading = (n, title, label = `Chapter ${n}`) => [
  new Paragraph({ pageBreakBefore: true, spacing: { before: 0, after: CHAPTER_TOP, line: 240 }, children: [] }),
  new Paragraph({ heading: HeadingLevel.HEADING_1, alignment: AlignmentType.CENTER, spacing: { before: 0, after: 480, line: 340 },
    children: [new TextRun({ text: label, font: FONT, size: 36, bold: true }), new TextRun({ text: title, font: FONT, size: 36, bold: true, break: 1 })] }),
];
const h2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: t, font: FONT })] });
const h3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: t, font: FONT })] });
const bullets = (items) => items.map((t) => new Paragraph({ numbering: { reference: "bul", level: 0 }, alignment: AlignmentType.JUSTIFIED, spacing: { line: 300, after: 60 }, children: runs(t, { size: 24 }) }));
const numbered = (items, ref) => items.map((t) => new Paragraph({ numbering: { reference: ref, level: 0 }, alignment: AlignmentType.JUSTIFIED, spacing: { line: 300, after: 60 }, children: runs(t, { size: 24 }) }));

const border = { style: BorderStyle.SINGLE, size: 4, color: "808080" };
const borders = { top: border, bottom: border, left: border, right: border };
function table(spec) {
  const total = spec.cols.reduce((a, b) => a + b, 0);
  const cell = (t, w, head) => new TableCell({
    width: { size: w, type: WidthType.DXA }, borders, margins: { top: 40, bottom: 40, left: 80, right: 80 },
    shading: head ? { fill: "D9E2F3", type: ShadingType.CLEAR, color: "auto" } : undefined,
    children: [new Paragraph({ keepNext: true, children: runs(t, { size: 20, bold: !!head }) })],
  });
  return [
    new Paragraph({ keepNext: true, alignment: AlignmentType.CENTER, spacing: { before: 140, after: 60 }, children: [new TextRun({ text: spec.caption, font: FONT, size: 22, bold: true })] }),
    new Table({
      width: { size: total, type: WidthType.DXA }, columnWidths: spec.cols,
      rows: [new TableRow({ tableHeader: true, cantSplit: true, children: spec.head.map((h, i) => cell(h, spec.cols[i], true)) }),
        ...spec.rows.map((r) => new TableRow({ cantSplit: true, children: r.map((t, i) => cell(t, spec.cols[i], false)) }))],
    }),
    new Paragraph({ spacing: { after: 100 }, children: [] }),
  ];
}
function figure(f) {
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 100, after: 40 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(path.join(FIG, f.file)), transformation: { width: f.w, height: f.h },
        altText: { title: f.caption, description: f.caption, name: f.file } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 140 }, children: [new TextRun({ text: f.caption, font: FONT, size: 22, italics: true })] }),
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

// ---- front matter (follows the template order) -------------------------------------------------------------------
// Cover page in the template order: title, degree block, names, guide, college logo, department, college, university.
const LOGO = path.join(FIG, "college_logo.jpeg");
const cover = [
  centered(C.TITLE, { size: 32, bold: true, before: 120, after: 560, line: 340 }),
  centered("A project report submitted in partial fulfillment of the requirements", { size: 24, after: 20 }),
  centered("for the degree of", { size: 24, after: 360 }),
  centered("Bachelor of Technology", { size: 26, bold: true, after: 0 }),
  centered("In", { size: 26, bold: true, after: 0 }),
  centered("Computer Engineering", { size: 26, bold: true, after: 400 }),
  centered("by", { size: 24, after: 280 }),
  ...NAMES.map((n) => centered(n, { size: 24, bold: true, after: 40 })),
  centered("Under the guidance of", { size: 24, before: 560, after: 100 }),
  centered(C.GUIDE, { size: 24, bold: true, after: C.GUIDE_DESIG ? 20 : 480 }),
  ...(C.GUIDE_DESIG ? [centered(`(${C.GUIDE_DESIG})`, { size: 24, bold: true, after: 480 })] : []),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 160 },
    children: [new ImageRun({ type: "jpg", data: fs.readFileSync(LOGO), transformation: { width: 189, height: 135 },
      altText: { title: "Fr. Conceicao Rodrigues College of Engineering emblem", description: "College emblem", name: "college_logo.jpeg" } })] }),
  centered("DEPARTMENT OF COMPUTER ENGINEERING", { size: 24, after: 100 }),
  centered("Fr. Conceicao Rodrigues College of Engineering, Bandra (W), Mumbai - 400050", { size: 24, bold: true, after: 100 }),
  centered("University of Mumbai (2026 - 27)", { size: 24 }),
];
const dedication = [
  ...blank(14),
  centered("This work is dedicated to our families.", { size: 24, italics: true, after: 60 }),
  centered("We are very thankful for their motivation and support.", { size: 24, italics: true }),
];
const titleOf = (t) => centered(t, { size: 28, bold: true, after: 240, before: 120 });
// Front-matter titles that the template lists in the contents (Abstract, lists, glossary) are Heading 1 so the contents picks them up
const frontHeading = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, alignment: AlignmentType.CENTER, spacing: { before: 120, after: 240 },
  children: [new TextRun({ text: t, font: FONT, size: 28, bold: true })] });
const sigRow = (a, b) => new Paragraph({ tabStops: [{ type: TabStopType.CENTER, position: Math.round(TEXT_W * 0.25) }, { type: TabStopType.CENTER, position: Math.round(TEXT_W * 0.75) }],
  spacing: { after: 20 }, children: [new TextRun({ text: `\t${a}\t${b}`, font: FONT, size: 24 })] });
const approvalSheet = [
  titleOf("Internal Approval Sheet"), titleOf("CERTIFICATE"),
  body(`This is to certify that the project entitled **"${C.TITLE}"** is a bonafide work of **${NAMES.join(", ")}** submitted to the University of Mumbai in partial fulfillment of the requirement for the award of the degree of Bachelor in **Computer Engineering.**`),
  ...blank(4),
  centered("(Name and sign)", { size: 24, after: 20 }),
  centered("Supervisor/Guide", { size: 24, after: 20 }),
  ...blank(4),
  sigRow("Dr. Sujata Deshmukh", "Dr. Sapna Prabhu"), sigRow("Head of Department", "Principal"),
];
const approval = [
  titleOf("Approval Sheet"), titleOf("Project Report Approval"),
  body(`This project report entitled **${C.TITLE}** by **${C.STUDENTS.map(([n]) => n).join(", ")}** is approved for the degree of Bachelor of Engineering in Computer Engineering.`),
  ...blank(3),
  body("Examiner 1. --------------------------------------"), body("Examiner 2. --------------------------------------"),
  ...blank(2), body("Date:"), body("Place:"),
];
const declaration = [
  titleOf("Declaration"),
  body("We declare that this written submission represents our ideas in our own words and where others' ideas or words have been included, we have adequately cited and referenced the original sources. We also declare that we have adhered to all principles of academic honesty and integrity and have not misrepresented or fabricated or falsified any idea/data/fact/source in our submission. We understand that any violation of the above will be cause for disciplinary action by the Institute and can also evoke penal action from the sources which have thus not been properly cited or from whom proper permission has not been taken when needed."),
  ...blank(2),
  ...NAMES.map((n) => new Paragraph({ indent: { left: 3600 }, spacing: { after: 160 },
    children: [new TextRun({ text: `${n} `, font: FONT, size: 24 }), new TextRun({ text: "(sign) ", bold: true, font: FONT, size: 24 }), new TextRun({ text: "____________", font: FONT, size: 24 })] })),
  ...blank(1),
  body("Date:"),
];
const abstractPage = [
  frontHeading("Abstract"), ...C.abstract.map(body),
  new Paragraph({ spacing: { before: 100 }, children: [new TextRun({ text: "Keywords: ", bold: true, font: FONT, size: 24 }), new TextRun({ text: C.keywords, italics: true, font: FONT, size: 24 })] }),
];
const ack = [
  titleOf("Acknowledgments"),
  body(`We have great pleasure in presenting the report on "${C.TITLE}". We take this opportunity to express our sincere thanks towards our guide ${C.GUIDE}, C.R.C.E, Bandra (W), Mumbai, for providing the technical guidelines and suggestions regarding the line of this work. We enjoyed discussing the work progress with the guide during our visits to the department.`),
  body("We thank Dr. Sujata Deshmukh, Head of Computer Engineering department, the Principal and the management of C.R.C.E., Mumbai for encouragement and providing necessary infrastructure for pursuing the project."),
  body("We also thank all non-teaching staff for their valuable support to complete our project."),
  ...blank(1),
  ...NAMES.map((n) => new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: n, font: FONT, size: 24 })] })),
  body("Date:"),
];

const figs = [], tabs = [];
C.chapters.forEach((ch) => ch.blocks.forEach((b) => { if (b.figure) figs.push(b.figure.caption); if (b.table) tabs.push(b.table.caption); }));
const listPage = (title, items) => [frontHeading(title), ...items.map((t) => new Paragraph({ spacing: { after: 100, line: 300 }, children: [new TextRun({ text: t, font: FONT, size: 24 })] }))];
const glossary = [frontHeading("Glossary"), ...C.glossary.map(([a, b]) => new Paragraph({ spacing: { after: 90, line: 300 }, children: [new TextRun({ text: a + ": ", bold: true, font: FONT, size: 24 }), new TextRun({ text: b, font: FONT, size: 24 })] }))];
const contents = [titleOf("Contents"), new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" })];

// ---- main matter ---------------------------------------------------------------------------------------------------
const counter = { n: 0 };
const main = [];
C.chapters.forEach((ch, i) => { main.push(...chapterHeading(i + 1, ch.title)); main.push(...blocks(ch.blocks, counter)); });
// Appendix A (before the References, as in the template): the first page of the similarity (plagiarism) report of this report
main.push(...chapterHeading(null, "Plagiarism Report", "Appendix A"));
main.push(h2("A.1 Similarity Report"));
main.push(body("The similarity report generated for this project report is reproduced below (first page of the report). It shows an overall similarity of 9 per cent, made up of 8 per cent from the internet database, 6 per cent from the publications database and 7 per cent from the submitted works database. Bibliographic, quoted and cited material and small matches of fewer than 8 words were excluded."));
main.push(...figure({ file: "similarity_report_p1.png", w: 300, h: 424, caption: "Figure A.1: First page of the similarity report" }));
main.push(new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, alignment: AlignmentType.CENTER, spacing: { before: 400, after: 240 }, children: [new TextRun({ text: "References", font: FONT, size: 36, bold: true })] }));
C.references.forEach((r, i) => main.push(new Paragraph({ spacing: { after: 70, line: 264 }, indent: { left: 540, hanging: 540 }, alignment: AlignmentType.JUSTIFIED,
  children: [new TextRun({ text: `[${i + 1}]\t`, font: FONT, size: 21 }), new TextRun({ text: r, font: FONT, size: 21 })], tabStops: [{ type: TabStopType.LEFT, position: 540 }] })));

const footer = () => ({ default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 22 })] })] }) });
const numberingConfig = [{ reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] }];
for (let i = 1; i <= counter.n; i++) numberingConfig.push({ reference: "num" + i, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] });

const doc = new Document({
  creator: C.STUDENTS[0][0], title: C.TITLE, description: "Project report, Computer Engineering, FRCRCE",
  features: { updateFields: true },
  styles: {
    default: { document: { run: { font: FONT, size: 24 } } },
    paragraphStyles: [
      // chapter 18 pt, section 14 pt (flush left, bold), sub-section 12 pt bold, as in the template guidelines
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 36, bold: true }, paragraph: { spacing: { before: 0, after: 240 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 28, bold: true }, paragraph: { spacing: { before: 240, after: 100 }, keepNext: true, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 24, bold: true }, paragraph: { spacing: { before: 160, after: 80 }, keepNext: true, outlineLevel: 2 } },
    ],
  },
  numbering: { config: numberingConfig },
  sections: [
    { properties: { page: { size: A4, margin: MARGIN } }, children: [...cover, pageBreak(), ...dedication] },
    { properties: { type: SectionType.NEXT_PAGE, page: { size: A4, margin: MARGIN, pageNumbers: { start: 1, formatType: NumberFormat.LOWER_ROMAN } } }, footers: footer(),
      children: [...approvalSheet, pageBreak(), ...approval, pageBreak(), ...declaration, pageBreak(), ...abstractPage, pageBreak(), ...ack, pageBreak(), ...contents,
        pageBreak(), ...listPage("List of Figures", figs), pageBreak(), ...listPage("List of Tables", tabs), pageBreak(), ...glossary] },
    { properties: { type: SectionType.NEXT_PAGE, page: { size: A4, margin: MARGIN, pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL } } }, footers: footer(), children: main },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  const out = path.join(__dirname, "Project_Report.docx");
  fs.writeFileSync(out, buf);
  console.log("wrote", out, buf.length, "bytes; figures:", figs.length, "tables:", tabs.length);
});
