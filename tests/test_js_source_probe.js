// js_source_probe 自己的測試。
//
// 判準（feedback-execution-test-before-deploy「驗證 harness 自己會假綠燈」）：
//   **每一條都要先證明「天真寫法會錯」，再證明「helper 是對的」。**
//   只驗 helper 回傳正確值不夠——那無法區分「helper 有價值」與「這個坑根本不存在」。
//
// 跑法：node test_js_source_probe.js

"use strict";
const path = require("path");
const { extractFunctionSource, mutateSource, countMatches } =
  require(path.join(__dirname, "..", "tools", "js_source_probe.js"));

let pass = 0, fail = 0;
function chk(label, cond, detail) {
  console.log("  [" + (cond ? "PASS" : "FAIL") + "] " + label + (detail ? "  → " + detail : ""));
  cond ? pass++ : fail++;
}
function throws(fn) { try { fn(); return null; } catch (e) { return e; } }

// 天真版：坑① —— 直接拿第一個 `{` 當本體起點
function naiveExtract(src, name) {
  const start = src.indexOf("function " + name + "(");
  if (start < 0) return null;
  let i = src.indexOf("{", start), depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}") { depth--; if (depth === 0) return src.slice(start, j + 1); }
  }
  return null;
}

console.log("== 坑①：解構參數的 `{` 會讓天真版抽到半截 ==");
{
  const src = [
    "function target({ force = false } = {}) {",
    "  const a = 1;",
    "  return force ? a : 0;",
    "}",
    "function after() { return 9; }",
  ].join("\n");

  const naive = naiveExtract(src, "target");
  chk("天真版真的抽錯（沒有涵蓋到函式結尾）", naive !== null && !naive.trimEnd().endsWith("return force ? a : 0;\n}"),
    JSON.stringify(naive));
  chk("天真版抽出來的東西甚至不含 return", naive !== null && !/return force/.test(naive));

  const good = extractFunctionSource(src, "target");
  chk("helper 抽到完整函式", /return force \? a : 0;/.test(good) && good.trimEnd().endsWith("}"));
  chk("helper 沒有多吃到下一個函式", !/function after/.test(good));
  chk("helper 抽出來的可以真的被執行", (() => {
    const fn = new Function(good + "\nreturn target;")();
    return fn({ force: true }) === 1 && fn() === 0;
  })());
}

console.log("== 大括號出現在字串／樣板／正則／註解裡 ==");
{
  const src = [
    "function tricky(a) {",
    '  const s = "} not a brace";',
    "  const t = `x ${ a ? '}' : '{' } y`;",
    "  const re = /[}]{1,2}/g;",
    "  // } 註解裡的括號",
    "  /* } 區塊註解 */",
    "  return s.length + t.length + re.source.length;",
    "}",
    "function sentinel() { return 'SENTINEL'; }",
  ].join("\n");
  const good = extractFunctionSource(src, "tricky");
  chk("helper 不被字串/樣板/正則/註解裡的括號騙", !/sentinel/.test(good) && good.trimEnd().endsWith("}"));
  chk("抽出來可執行", typeof new Function(good + "\nreturn tricky;")() === "function");
}

console.log("== 函式名是另一個函式名的前綴 ==");
{
  const src = "function doThingElse() { return 2; }\nfunction doThing() { return 1; }";
  const good = extractFunctionSource(src, "doThing");
  chk("抽到的是 doThing 不是 doThingElse", new Function(good + "\nreturn doThing;")()() === 1);
}

console.log("== 抽不到 / 抽壞一定要 throw（不可以回半截或 null）==");
{
  const e1 = throws(() => extractFunctionSource("function a(){}", "notThere"));
  chk("找不到函式 → throw", !!e1 && /找不到 function notThere/.test(e1.message));
  chk("而且訊息說明這是有意義的紅燈", !!e1 && /不該當成 0 個案例/.test(e1.message));
  const e2 = throws(() => extractFunctionSource("function bad(a) { if (a) {", "bad"));
  chk("括號不配對 → throw", !!e2 && /不配對/.test(e2.message));
}

console.log("== 坑②：CRLF 檔的變異，樣式寫 `\\n` 也要能套上 ==");
{
  const crlf = ["function f() {", "    if (!ok) return false;", "    return true;", "}"].join("\r\n");
  chk("素材真的是 CRLF", crlf.includes("\r\n"));

  // 天真版：直接 replace，樣式用 \n
  const naivePat = /\n {4}if \(!ok\) return false;\n/;
  const naiveOut = crlf.replace(naivePat, "\n");
  chk("天真版沒套上（replace 安靜地回傳原字串）", naiveOut === crlf);

  const good = mutateSource(crlf, naivePat, "\n", { label: "拿掉守門" });
  chk("helper 套上了", good !== crlf && !/if \(!ok\)/.test(good));
  chk("helper 還原了原本的行尾（仍是 CRLF）", good.includes("\r\n") && !/[^\r]\n/.test(good));
}

console.log("== 變異沒命中一定要 throw（這是本工具存在的主要理由）==");
{
  const src = "function f() {\n  return 1;\n}\n";
  const e = throws(() => mutateSource(src, /return 2;/, "return 3;", { label: "改回傳值" }));
  chk("沒命中 → throw", !!e && /沒有命中任何內容/.test(e.message));
  chk("訊息點明後果是「這一輪等於沒有變異」", !!e && /等於沒有變異/.test(e.message));
  chk("訊息提醒全綠會被誤讀", !!e && /全綠/.test(e.message));
}

console.log("== expect 次數與「命中但沒改變」 ==");
{
  const src = "a;\na;\na;\n";
  chk("命中次數不符 → throw",
    !!throws(() => mutateSource(src, /a;/g, "b;", { label: "換 a", expect: 1 })));
  chk("次數相符 → 通過", mutateSource(src, /a;/g, "b;", { label: "換 a", expect: 3 }) === "b;\nb;\nb;\n");
  chk("不帶 g 時只換第一個", mutateSource(src, /a;/, "b;", { label: "換第一個 a" }) === "b;\na;\na;\n");
  chk("命中但內容沒變 → throw",
    !!throws(() => mutateSource(src, /a;/, "a;", { label: "換成一樣的" })));
}

console.log("== countMatches（唯讀錨點檢查）==");
{
  const crlf = "x\r\ny\r\nx\r\n";
  chk("CRLF 下用 \\n 樣式也數得到", countMatches(crlf, /x\n/g) === 2);
  chk("字串樣式", countMatches("aXbXc", "X") === 2);
  chk("沒命中回 0", countMatches("abc", /zzz/) === 0);
}

console.log("\n結果：PASS " + pass + " / FAIL " + fail);
process.exit(fail ? 1 : 0);
