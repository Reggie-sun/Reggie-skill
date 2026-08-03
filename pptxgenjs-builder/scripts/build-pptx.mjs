#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import pptxgen from "pptxgenjs";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const THEME_PATH = path.resolve(SCRIPT_DIR, "../templates/enterprise-theme.json");
const FONT_FACE = "Microsoft YaHei";
const FALLBACK_FONT = "Noto Sans CJK SC";
const PAGE = { width: 13.333, height: 7.5 };

const defaultTheme = {
  colors: {
    background: "FFFFFF",
    text: "1F2937",
    muted: "64748B",
    border: "D6DEE8",
    primary: "1D4ED8",
    accent: "0F766E",
    soft: "EFF6FF",
    softAccent: "ECFDF5"
  },
  fontSize: {
    title: 24,
    body: 15,
    small: 9
  },
  margin: {
    left: 0.65,
    right: 0.65,
    top: 0.5,
    bottom: 0.45
  }
};

function usage() {
  console.error("Usage: node scripts/build-pptx.mjs <input.json> <output.pptx>");
}

function asText(value, fallback = "") {
  if (value === null || value === undefined) return fallback;
  const text = String(value).trim();
  return text || fallback;
}

function asArray(value) {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item) => item !== null && item !== undefined)
    .map((item) => String(item).trim())
    .filter(Boolean);
}

function normalizeSlide(raw, index) {
  const slide = raw && typeof raw === "object" ? raw : {};
  return {
    ...slide,
    layout: asText(slide.layout, "content").toLowerCase(),
    title: asText(slide.title, "未命名页面"),
    subtitle: asText(slide.subtitle),
    bullets: asArray(slide.bullets),
    left_bullets: asArray(slide.left_bullets),
    right_bullets: asArray(slide.right_bullets),
    steps: asArray(slide.steps),
    speaker_notes: asText(slide.speaker_notes),
    _index: index
  };
}

function fitFont(items, base = 15, min = 10) {
  const totalChars = items.reduce((sum, item) => sum + item.length, 0);
  const pressure = Math.max(0, items.length - 4) * 1.2 + Math.max(0, totalChars - 160) / 55;
  return Math.max(min, Math.round((base - pressure) * 10) / 10);
}

function bulletText(items) {
  if (!items.length) return "暂无内容";
  return items.map((item) => `• ${item}`).join("\n");
}

function uniqueTitles(slides) {
  const seen = new Map();
  return slides.map((slide) => {
    const count = seen.get(slide.title) || 0;
    seen.set(slide.title, count + 1);
    if (count === 0) return slide;
    return { ...slide, title: `${slide.title} ${count + 1}` };
  });
}

async function loadTheme() {
  try {
    const raw = await fs.readFile(THEME_PATH, "utf8");
    return { ...defaultTheme, ...JSON.parse(raw) };
  } catch {
    return defaultTheme;
  }
}

async function loadOutline(inputPath) {
  const raw = await fs.readFile(inputPath, "utf8");
  const outline = JSON.parse(raw);
  const meta = outline.meta && typeof outline.meta === "object" ? outline.meta : {};
  if (!Array.isArray(outline.slides)) {
    throw new Error("Invalid slides_outline.json: slides must be an array.");
  }
  return {
    meta,
    slides: uniqueTitles(outline.slides.map(normalizeSlide))
  };
}

function addNotes(slide, notes) {
  if (!notes || typeof slide.addNotes !== "function") return;
  try {
    slide.addNotes(notes);
  } catch {
    slide.addNotes([notes]);
  }
}

function addFooter(pptx, slide, pageNumber, total, meta, theme) {
  const colors = theme.colors;
  slide.addShape(pptx.ShapeType.line, {
    x: 0.65,
    y: 7.02,
    w: 12.03,
    h: 0,
    line: { color: colors.border, width: 0.75 }
  });
  slide.addText(asText(meta.title), {
    x: 0.65,
    y: 7.08,
    w: 8.8,
    h: 0.18,
    fontFace: FONT_FACE,
    fontSize: theme.fontSize.small,
    color: colors.muted,
    fit: "shrink"
  });
  slide.addText(`${pageNumber}/${total}`, {
    x: 11.65,
    y: 7.06,
    w: 1,
    h: 0.22,
    fontFace: FONT_FACE,
    fontSize: theme.fontSize.small,
    color: colors.muted,
    align: "right"
  });
}

function addSlideTitle(pptx, slide, title, theme) {
  const colors = theme.colors;
  slide.background = { color: colors.background };
  slide.addText(title, {
    x: 0.65,
    y: 0.42,
    w: 11.8,
    h: 0.5,
    fontFace: FONT_FACE,
    fontSize: theme.fontSize.title,
    bold: true,
    color: colors.text,
    fit: "shrink",
    margin: 0
  });
  slide.addShape(pptx.ShapeType.line, {
    x: 0.65,
    y: 1.03,
    w: 1.2,
    h: 0,
    line: { color: colors.primary, width: 2 }
  });
}

function addBulletList(slide, bullets, box, theme, options = {}) {
  slide.addText(bulletText(bullets), {
    x: box.x,
    y: box.y,
    w: box.w,
    h: box.h,
    fontFace: FONT_FACE,
    fontSize: fitFont(bullets, options.baseSize || theme.fontSize.body, options.minSize || 10),
    color: theme.colors.text,
    breakLine: false,
    fit: "shrink",
    valign: "top",
    margin: 0.04,
    paraSpaceAfterPt: 7
  });
}

function addTitleSlide(pptx, slide, data, meta, theme) {
  const colors = theme.colors;
  const title = asText(data.title, asText(meta.title, "未命名页面"));
  const subtitle = asText(data.subtitle, asText(meta.subtitle));
  slide.background = { color: colors.background };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: 0,
    w: PAGE.width,
    h: 0.18,
    fill: { color: colors.primary },
    line: { color: colors.primary }
  });
  slide.addText(title, {
    x: 0.8,
    y: 2.1,
    w: 11.6,
    h: 0.8,
    fontFace: FONT_FACE,
    fontSize: 32,
    bold: true,
    color: colors.text,
    fit: "shrink",
    margin: 0
  });
  slide.addText(subtitle, {
    x: 0.82,
    y: 3.05,
    w: 10.8,
    h: 0.45,
    fontFace: FONT_FACE,
    fontSize: 17,
    color: colors.muted,
    fit: "shrink",
    margin: 0
  });
  slide.addText([asText(meta.author), asText(meta.date)].filter(Boolean).join("  |  "), {
    x: 0.82,
    y: 5.85,
    w: 8,
    h: 0.28,
    fontFace: FONT_FACE,
    fontSize: 11,
    color: colors.muted
  });
}

function addAgendaSlide(pptx, slide, data, theme) {
  addSlideTitle(pptx, slide, data.title, theme);
  const items = data.bullets.length ? data.bullets : ["背景与目标", "当前进展", "问题复盘", "后续计划"];
  const colors = theme.colors;
  items.slice(0, 8).forEach((item, index) => {
    const y = 1.45 + index * 0.55;
    slide.addText(String(index + 1).padStart(2, "0"), {
      x: 0.9,
      y,
      w: 0.55,
      h: 0.28,
      fontFace: FONT_FACE,
      fontSize: 11,
      bold: true,
      color: colors.primary,
      align: "center",
      margin: 0
    });
    slide.addText(item, {
      x: 1.65,
      y: y - 0.03,
      w: 10.2,
      h: 0.35,
      fontFace: FONT_FACE,
      fontSize: 15,
      color: colors.text,
      fit: "shrink",
      margin: 0
    });
  });
}

function addSectionSlide(slide, data, theme) {
  const colors = theme.colors;
  slide.background = { color: colors.soft };
  slide.addText(data.title, {
    x: 1.15,
    y: 2.45,
    w: 10.9,
    h: 0.75,
    fontFace: FONT_FACE,
    fontSize: 30,
    bold: true,
    color: colors.primary,
    align: "center",
    fit: "shrink",
    margin: 0
  });
  if (data.subtitle) {
    slide.addText(data.subtitle, {
      x: 1.6,
      y: 3.35,
      w: 10,
      h: 0.35,
      fontFace: FONT_FACE,
      fontSize: 15,
      color: colors.muted,
      align: "center",
      fit: "shrink",
      margin: 0
    });
  }
}

function addContentSlide(pptx, slide, data, theme) {
  addSlideTitle(pptx, slide, data.title, theme);
  addBulletList(slide, data.bullets, { x: 0.9, y: 1.45, w: 11.4, h: 4.65 }, theme);
  if (data.visual_suggestion) {
    slide.addText(`视觉建议：${data.visual_suggestion}`, {
      x: 0.9,
      y: 6.25,
      w: 11.3,
      h: 0.35,
      fontFace: FONT_FACE,
      fontSize: 10,
      color: theme.colors.muted,
      italic: true,
      fit: "shrink"
    });
  }
}

function addTwoColumnSlide(pptx, slide, data, theme) {
  addSlideTitle(pptx, slide, data.title, theme);
  const colors = theme.colors;
  const columns = [
    { x: 0.75, title: asText(data.left_title, "左侧"), bullets: data.left_bullets, fill: colors.soft },
    { x: 6.85, title: asText(data.right_title, "右侧"), bullets: data.right_bullets, fill: colors.softAccent }
  ];
  columns.forEach((column) => {
    slide.addShape(pptx.ShapeType.rect, {
      x: column.x,
      y: 1.35,
      w: 5.75,
      h: 4.95,
      fill: { color: column.fill },
      line: { color: colors.border, width: 0.8 }
    });
    slide.addText(column.title, {
      x: column.x + 0.25,
      y: 1.62,
      w: 5.2,
      h: 0.35,
      fontFace: FONT_FACE,
      fontSize: 15,
      bold: true,
      color: colors.text,
      fit: "shrink"
    });
    addBulletList(slide, column.bullets, { x: column.x + 0.35, y: 2.15, w: 5.05, h: 3.65 }, theme, {
      baseSize: 13,
      minSize: 9
    });
  });
}

function addTableSlide(pptx, slide, data, theme) {
  addSlideTitle(pptx, slide, data.title, theme);
  const table = data.table && typeof data.table === "object" ? data.table : {};
  const headers = asArray(table.headers);
  const rows = Array.isArray(table.rows) ? table.rows : [];
  const normalizedRows = rows.map((row) => (Array.isArray(row) ? row.map((cell) => asText(cell)) : []));
  const allRows = [
    headers.map((text) => ({
      text,
      options: { bold: true, color: "FFFFFF", fill: { color: theme.colors.primary } }
    })),
    ...normalizedRows.map((row) =>
      row.map((text) => ({
        text,
        options: { color: theme.colors.text, fill: { color: "FFFFFF" } }
      }))
    )
  ].filter((row) => row.length);
  if (!allRows.length) {
    addBulletList(slide, ["暂无表格数据"], { x: 0.9, y: 1.45, w: 11.2, h: 3.5 }, theme);
    return;
  }
  slide.addTable(allRows, {
    x: 0.75,
    y: 1.4,
    w: 11.85,
    h: Math.min(4.85, 0.45 + allRows.length * 0.55),
    fontFace: FONT_FACE,
    fontSize: allRows.length > 7 ? 9.5 : 11,
    color: theme.colors.text,
    valign: "mid",
    margin: 0.08,
    border: { type: "solid", color: theme.colors.border, pt: 1 },
    fit: "shrink"
  });
}

function addProcessSlide(pptx, slide, data, theme) {
  addSlideTitle(pptx, slide, data.title, theme);
  const colors = theme.colors;
  const steps = data.steps.length ? data.steps : data.bullets;
  const limited = steps.slice(0, 6);
  const gap = 0.18;
  const cardW = Math.min(1.78, (11.5 - gap * (limited.length - 1)) / Math.max(1, limited.length));
  const startX = (PAGE.width - (cardW * limited.length + gap * (limited.length - 1))) / 2;
  limited.forEach((step, index) => {
    const x = startX + index * (cardW + gap);
    slide.addShape(pptx.ShapeType.rect, {
      x,
      y: 2.55,
      w: cardW,
      h: 1.25,
      fill: { color: index === limited.length - 1 ? colors.softAccent : colors.soft },
      line: { color: index === limited.length - 1 ? colors.accent : colors.primary, width: 1 }
    });
    slide.addText(String(index + 1), {
      x: x + 0.12,
      y: 2.72,
      w: 0.3,
      h: 0.25,
      fontFace: FONT_FACE,
      fontSize: 10,
      bold: true,
      color: colors.primary,
      margin: 0
    });
    slide.addText(step, {
      x: x + 0.18,
      y: 3.05,
      w: cardW - 0.36,
      h: 0.45,
      fontFace: FONT_FACE,
      fontSize: 12,
      bold: true,
      align: "center",
      color: colors.text,
      fit: "shrink",
      margin: 0
    });
    if (index < limited.length - 1) {
      slide.addText("→", {
        x: x + cardW - 0.03,
        y: 2.98,
        w: gap + 0.06,
        h: 0.35,
        fontFace: FALLBACK_FONT,
        fontSize: 15,
        color: colors.muted,
        align: "center",
        margin: 0
      });
    }
  });
}

function addSummarySlide(pptx, slide, data, theme) {
  addSlideTitle(pptx, slide, data.title, theme);
  const colors = theme.colors;
  slide.addShape(pptx.ShapeType.rect, {
    x: 0.78,
    y: 1.45,
    w: 11.75,
    h: 4.55,
    fill: { color: colors.softAccent },
    line: { color: colors.accent, width: 1 }
  });
  addBulletList(slide, data.bullets, { x: 1.1, y: 1.85, w: 11.05, h: 3.65 }, theme, {
    baseSize: 17,
    minSize: 11
  });
}

function renderSlide(pptx, data, meta, theme, pageNumber, total) {
  const slide = pptx.addSlide();
  switch (data.layout) {
    case "title":
      addTitleSlide(pptx, slide, data, meta, theme);
      break;
    case "agenda":
      addAgendaSlide(pptx, slide, data, theme);
      break;
    case "section":
      addSectionSlide(slide, data, theme);
      break;
    case "two_column":
      addTwoColumnSlide(pptx, slide, data, theme);
      break;
    case "table":
      addTableSlide(pptx, slide, data, theme);
      break;
    case "process":
      addProcessSlide(pptx, slide, data, theme);
      break;
    case "summary":
      addSummarySlide(pptx, slide, data, theme);
      break;
    case "content":
    default:
      addContentSlide(pptx, slide, data, theme);
      break;
  }
  addFooter(pptx, slide, pageNumber, total, meta, theme);
  addNotes(slide, data.speaker_notes);
}

async function main() {
  const [inputPath, outputPath] = process.argv.slice(2);
  if (!inputPath || !outputPath) {
    usage();
    process.exit(1);
  }

  const resolvedInput = path.resolve(inputPath);
  const resolvedOutput = path.resolve(outputPath);
  const theme = await loadTheme();
  const outline = await loadOutline(resolvedInput);

  const pptx = new pptxgen();
  pptx.layout = "LAYOUT_WIDE";
  pptx.author = asText(outline.meta.author, "Codex");
  pptx.company = "Codex";
  pptx.subject = asText(outline.meta.subtitle);
  pptx.title = asText(outline.meta.title, path.basename(resolvedOutput, ".pptx"));
  pptx.lang = "zh-CN";
  pptx.theme = {
    headFontFace: FONT_FACE,
    bodyFontFace: FONT_FACE,
    lang: "zh-CN"
  };

  outline.slides.forEach((slide, index) => {
    renderSlide(pptx, slide, outline.meta, theme, index + 1, outline.slides.length);
  });

  await fs.mkdir(path.dirname(resolvedOutput), { recursive: true });
  await pptx.writeFile({ fileName: resolvedOutput });

  console.log(`input: ${resolvedInput}`);
  console.log(`output: ${resolvedOutput}`);
  console.log(`slides: ${outline.slides.length}`);
  console.log("success: true");
}

main().catch((error) => {
  console.error(`success: false`);
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
