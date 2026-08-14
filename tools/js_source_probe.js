// js_source_probe —— 「從原始碼抽函式來跑」與「變異測試」這兩件事的共用零件。
//
// ⚠ 核心層規則：本檔不得出現任何專案名稱／專案路徑字面值（UNIVERSAL_HARNESS_PLAN §2）。
//    它只吃「你給的字串」與「你給的檔案路徑」。
//
// 為什麼要有這支（兩個實際被咬過的坑，都不是打錯字，是**失敗長得像成功**）：
//
//  ① 抽函式時用「第一個 `{`」當本體起點
//     `function f({ force = false } = {})` 的第一個 `{` 是**解構參數**，
//     從它起算括號配對會在參數列結束就歸零 → 抽到被截斷的原始碼。
//     這種截斷有時語法還是合法的（只是少了一半），於是測試照跑照綠。
//
//  ② 變異的替換樣式沒套上，`String.replace` **回傳原字串、不報錯**
//     最常見成因是行尾：CRLF 檔裡 `}` 後面是 CR 不是 LF，寫成 `/\n {4}\}\n/` 永遠匹配不到。
//     但成因不重要——重要的是**沒套上的變異會讓測試全綠**，而全綠會被讀成「產品沒問題」，
//     實際上是「這一輪根本沒測到」。核心層 Python 側早有同型教訓，
//     見 tests/test_mutation_anchors.py 的 docstring（錨點漂掉→3 個變異失效→沒人看到）。
//
// 對策：**兩個函式都在失敗時 throw，不回傳「看起來還行」的東西。**
//   ①抽不到／抽出來不合法 → throw
//   ②替換沒命中／命中後內容沒變 → throw
//
// 用法：
//   const { extractFunctionSource, mutateSource } = require("<harness>/tools/js_source_probe.js");
//   const src  = fs.readFileSync(target, "utf8");
//   const fnSrc = extractFunctionSource(src, "myFunc");
//   const broken = mutateSource(fnSrc, /if \(!ok\) return false;/, "", { label: "拿掉守門" });

"use strict";

// ── 內部：判斷 `/` 是除號還是正則開頭 ────────────────────────────────
// 靠「前一個有意義的字元」判斷。這是掃描器的通用作法，對測試用途夠準；
// 真要 100% 正確得接完整 parser，那不值得——抽不準時下面的合法性檢查會擋下來。
const _REGEX_PREV = new Set("([{,;:=!&|?+-*%~^<>".split(""));

function _isRegexStart(src, i) {
  for (let j = i - 1; j >= 0; j--) {
    const ch = src[j];
    if (ch === " " || ch === "\t" || ch === "\r" || ch === "\n") continue;
    if (_REGEX_PREV.has(ch)) return true;
    // `return /re/`、`typeof /re/` 這種關鍵字結尾
    const tail = src.slice(Math.max(0, j - 11), j + 1);
    return /\b(return|typeof|instanceof|in|of|case|do|else|yield|await|void|delete|new)$/.test(tail);
  }
  return true;
}

// ── 內部：從 `from` 起做括號配對，跳過字串／樣板／註解／正則 ──────────
// open/close 用同一組（`(`/`)` 或 `{`/`}`）。回傳閉合括號的 index，找不到回 -1。
function _matchBracket(src, from, open, close) {
  let depth = 0;
  for (let i = from; i < src.length; i++) {
    const ch = src[i];

    // 註解
    if (ch === "/" && src[i + 1] === "/") { i = src.indexOf("\n", i); if (i < 0) return -1; continue; }
    if (ch === "/" && src[i + 1] === "*") { const e = src.indexOf("*/", i + 2); if (e < 0) return -1; i = e + 1; continue; }

    // 字串
    if (ch === '"' || ch === "'") {
      for (i++; i < src.length; i++) {
        if (src[i] === "\\") { i++; continue; }
        if (src[i] === ch) break;
      }
      continue;
    }

    // 樣板字串（含 ${} 巢狀）
    if (ch === "`") {
      for (i++; i < src.length; i++) {
        if (src[i] === "\\") { i++; continue; }
        if (src[i] === "$" && src[i + 1] === "{") {
          const end = _matchBracket(src, i + 1, "{", "}");
          if (end < 0) return -1;
          i = end;
          continue;
        }
        if (src[i] === "`") break;
      }
      continue;
    }

    // 正則字面值（含字元類別內的 `/`）
    if (ch === "/" && _isRegexStart(src, i)) {
      let inClass = false;
      for (i++; i < src.length; i++) {
        if (src[i] === "\\") { i++; continue; }
        if (src[i] === "[") inClass = true;
        else if (src[i] === "]") inClass = false;
        else if (src[i] === "/" && !inClass) break;
        else if (src[i] === "\n") break;   // 未閉合＝其實是除號，放棄
      }
      continue;
    }

    if (ch === open) depth++;
    else if (ch === close) { depth--; if (depth === 0) return i; }
  }
  return -1;
}

/**
 * 從原始碼裡抽出具名函式的完整原始碼（含 `function` 關鍵字到對應的 `}`）。
 * 抽不到、或抽出來的東西不是合法函式，一律 throw——不回傳半截程式碼。
 *
 * @param {string} src   整份原始碼
 * @param {string} name  函式名
 * @param {{validate?: boolean}} [opts]  validate 預設 true：用 new Function 驗一次合法性
 * @returns {string}
 */
function extractFunctionSource(src, name, opts) {
  const { validate = true } = opts || {};
  if (typeof src !== "string" || !src) throw new Error("extractFunctionSource: src 必須是非空字串");
  if (!name) throw new Error("extractFunctionSource: 未指定函式名");

  // 找 `function NAME(`，且 NAME 前面不能接著識別字（避免命中 `myfunction foo(`）
  const re = new RegExp("(^|[^\\w$])function\\s+" + name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*\\(");
  const m = re.exec(src);
  if (!m) {
    throw new Error(
      "extractFunctionSource: 找不到 function " + name + " —— 產品碼可能已改名、改成箭頭函式或被移除。" +
      "（這是有意義的紅燈：測試指向的東西不見了，不該當成 0 個案例默默跳過）"
    );
  }
  const start = m.index + (m[1] ? m[1].length : 0);

  // ⚠ 關鍵：先用括號配對走完**參數列**，再找本體的 `{`。
  //    直接 indexOf("{") 會命中解構參數 `({ a = 1 })` 的那個 `{`。
  const parenAt = src.indexOf("(", start);
  const parenEnd = _matchBracket(src, parenAt, "(", ")");
  if (parenEnd < 0) throw new Error("extractFunctionSource: " + name + " 的參數列括號不配對");

  const braceAt = src.indexOf("{", parenEnd);
  if (braceAt < 0) throw new Error("extractFunctionSource: " + name + " 找不到函式本體");
  const braceEnd = _matchBracket(src, braceAt, "{", "}");
  if (braceEnd < 0) throw new Error("extractFunctionSource: " + name + " 的本體大括號不配對");

  const out = src.slice(start, braceEnd + 1);

  if (validate) {
    // 合法性檢查：這一步就是「截斷會不會被發現」的分水嶺。
    try {
      new Function(out + "\nreturn typeof " + name + ";");
    } catch (e) {
      throw new Error("extractFunctionSource: 抽出來的 " + name + " 不是合法函式（可能被截斷）：" + e.message);
    }
  }
  return out;
}

// ── 行尾處理 ─────────────────────────────────────────────────────────
function _detectEol(s) {
  return /\r\n/.test(s) ? "\r\n" : "\n";
}

/**
 * 變異：把 pattern 換成 replacement，**沒套上就 throw**。
 *
 * 行尾由本函式負責：內部一律先正規化成 LF 再替換、最後還原成原本的行尾，
 * 所以呼叫端的樣式**直接寫 `\n` 就好**，不必記得 `\r?\n`（那正是被咬過的坑）。
 *
 * @param {string} src
 * @param {RegExp|string} pattern
 * @param {string} replacement
 * @param {{label?: string, expect?: number}} [opts]
 *        label  失敗訊息裡顯示的變異名稱
 *        expect 預期命中次數；給了就必須剛好等於（防「以為改一處、其實改了五處」）
 * @returns {string} 變異後的原始碼
 */
function mutateSource(src, pattern, replacement, opts) {
  const { label = "(未命名變異)", expect } = opts || {};
  if (typeof src !== "string") throw new Error("mutateSource: src 必須是字串");
  if (typeof replacement !== "string") throw new Error("mutateSource: replacement 必須是字串");

  const eol = _detectEol(src);
  const norm = src.replace(/\r\n/g, "\n");

  let count = 0;
  let out;
  if (pattern instanceof RegExp) {
    const flags = pattern.flags.includes("g") ? pattern.flags : pattern.flags + "g";
    out = norm.replace(new RegExp(pattern.source, flags), () => { count++; return replacement; });
    // 呼叫端若沒帶 g，語意是「只換第一個」——還原成只換一次
    if (!pattern.flags.includes("g") && count > 1) {
      count = 1;
      out = norm.replace(new RegExp(pattern.source, pattern.flags), replacement);
    }
  } else {
    let idx = norm.indexOf(pattern);
    if (idx >= 0) { count = 1; out = norm.slice(0, idx) + replacement + norm.slice(idx + pattern.length); }
    else out = norm;
  }

  if (count === 0) {
    throw new Error(
      "mutateSource: 變異「" + label + "」的樣式沒有命中任何內容 ⇒ **這一輪等於沒有變異**。\n" +
      "  樣式：" + String(pattern) + "\n" +
      "  常見成因：產品碼改了（錨點漂掉）／縮排或標點不同／樣式寫太死。\n" +
      "  ⚠ 沒有這道檢查的話，String.replace 會安靜地回傳原字串，測試會全綠而且看起來像「產品沒問題」。"
    );
  }
  if (expect !== undefined && count !== expect) {
    throw new Error("mutateSource: 變異「" + label + "」預期命中 " + expect + " 次，實際 " + count + " 次");
  }
  if (out === norm) {
    throw new Error("mutateSource: 變異「" + label + "」命中了但內容沒有改變（replacement 與原文相同？）");
  }

  return eol === "\r\n" ? out.replace(/\n/g, "\r\n") : out;
}

/** 只數不改，給「這個錨點還在不在」這種唯讀檢查用。 */
function countMatches(src, pattern) {
  const norm = String(src).replace(/\r\n/g, "\n");
  if (pattern instanceof RegExp) {
    const m = norm.match(new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : pattern.flags + "g"));
    return m ? m.length : 0;
  }
  let n = 0, i = 0;
  while ((i = norm.indexOf(pattern, i)) >= 0) { n++; i += pattern.length; }
  return n;
}

module.exports = { extractFunctionSource, mutateSource, countMatches };
