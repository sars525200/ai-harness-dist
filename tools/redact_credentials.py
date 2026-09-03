# -*- coding: utf-8 -*-
"""把工作紀錄裡的明文憑證換成 <REDACTED>，對話內容一字不動。

為什麼要這支：部署腳本曾經用
`New-Object PSCredential(<帳號>, (ConvertTo-SecureString <明文密碼> -AsPlainText -Force))`
的寫法，所以每跑一次就在對話紀錄裡留一份明文。刪整個檔會連對話歷史一起失去，
遮蔽只拿掉那把鑰匙。

四條安全設計（每一條都是踩過才加的）：

  1. **只在比對到的憑證形狀裡面換，不做全檔字串取代。**
     一個 4 字元的密碼若全檔取代，會把無關的文字一起打爛。

  2. **變數名不是憑證。** `ConvertTo-SecureString $Pass -AsPlainText` 裡的 `$Pass`
     長得跟密碼一模一樣，第一版把它一起遮掉，結果是把指令範本弄壞。
     已知的變數名列在 BENIGN，比對 sha256 前 8 碼，不比對明文。

  3. **6 小時內被寫過的檔跳過。** 那可能是還開著的 session，改它會撞車。
     ⇒ 本檔案自己那一則對話的紀錄一定漏掉，**收工後再跑一次才會乾淨**。

  4. **全程不印憑證值**，只印 sha8 與次數。動手前整檔備份到 repo 外。

用法：
    py -3 -X utf8 tools/redact_credentials.py --dry-run   # 只看計畫
    py -3 -X utf8 tools/redact_credentials.py             # 真的改
    py -3 -X utf8 tools/redact_credentials.py --verify    # 只驗證現況
"""
import os, re, sys, json, time, shutil, hashlib

# ── 掃描範圍 ───────────────────────────────────────────────────────────
def roots():
    out = []
    for p in (os.environ.get('HARNESS_SESSION_ARCHIVE'),
              os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'session-archive'),
              os.path.join(os.path.expanduser('~'), '.claude', 'projects')):
        if p and os.path.isdir(p) and p not in out:
            out.append(p)
    return out


BACKUP = os.path.join(os.path.expanduser('~'),
                      '.claude-credential-redact-backup')
MASK = '<REDACTED>'
HOT_SECONDS = 6 * 3600

# 每條規則有且僅有一個捕捉群組＝要遮的那段
PATTERNS = [
    re.compile(r'(?<=ConvertTo-SecureString )(?:\\{0,2}[\'"])([^\'"\\\s]{4,64})'
               r'(?=(?:\\{0,2}[\'"])\s*(?:-AsPlainText|-Force))'),
    re.compile(r'(?<=ConvertTo-SecureString )([^\s\'"\\]{4,64})(?=\s+-AsPlainText)'),
    re.compile(r'(?<=-Pass )(?:\\{0,2}[\'"])([^\'"\\\s]{4,64})(?=(?:\\{0,2}[\'"]))'),
    re.compile(r'(?<=-Pass )([^\s\'"\\\-][^\s\'"\\]{3,63})(?=[\s\\])'),
    re.compile(r'(?<=remoteEnableAccountPassword)(?:\\{0,2}"\s*:\s*\\{0,2}")'
               r'([^"\\\s]{4,64})(?=\\{0,2}")'),
]

# 已查證是 PowerShell 變數名，不是憑證（sha256 前 8 碼 → 說明）
BENIGN = {
    '7dd3e1e8': '$Pass',
    '80db0891': '$pass',
}


def sha8(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:8]


def targets():
    """回傳 (要處理的實體路徑, 因為太新而跳過的)。junction 會讓同一個檔
    出現兩次，用 realpath 去重。"""
    now = time.time()
    out, hot, seen = [], [], set()
    for root in roots():
        for dp, dn, fn in os.walk(root):
            for f in fn:
                p = os.path.join(dp, f)
                try:
                    with open(p, encoding='utf-8', errors='ignore') as fh:
                        t = fh.read()
                except Exception:
                    continue
                if not any(pat.search(t) for pat in PATTERNS):
                    continue
                rp = os.path.realpath(p)
                if rp in seen:
                    continue
                seen.add(rp)
                if now - os.stat(p).st_mtime < HOT_SECONDS:
                    hot.append(rp)
                else:
                    out.append(rp)
    return out, hot


def redact(text):
    n = 0
    kept = 0
    for pat in PATTERNS:
        def repl(m):
            nonlocal n, kept
            lit = m.group(1)
            if lit == MASK:
                return m.group(0)
            if sha8(lit) in BENIGN:
                kept += 1
                return m.group(0)
            n += 1
            return m.group(0).replace(lit, MASK)
        text = pat.sub(repl, text)
    return text, n, kept


def census(text):
    """(真正的明文, 已遮蔽, 變數名)"""
    real = masked = benign = 0
    for pat in PATTERNS:
        for m in pat.finditer(text):
            g = m.group(1)
            if g == MASK:
                masked += 1
            elif sha8(g) in BENIGN:
                benign += 1
            else:
                real += 1
    return real, masked, benign


def badjson(path, text):
    if not path.endswith('.jsonl'):
        return 0
    bad = 0
    for ln in text.splitlines():
        if not ln.strip():
            continue
        try:
            json.loads(ln)
        except Exception:
            bad += 1
    return bad


def main(argv):
    dry = '--dry-run' in argv
    verify = '--verify' in argv
    global HOT_SECONDS
    if verify:
        HOT_SECONDS = 0

    files, hot = targets()
    print('=' * 74)
    print('掃描根目錄：')
    for r in roots():
        print('   ', r)
    print('待處理 %d 個檔；跳過（6 小時內被寫過，可能有 session 開著）%d 個'
          % (len(files), len(hot)))
    for p in hot:
        print('   SKIP  %s' % os.path.basename(p))

    if verify:
        real = masked = benign = bad = 0
        offenders = []
        for p in files:
            with open(p, encoding='utf-8', errors='ignore') as fh:
                t = fh.read()
            r, m, b = census(t)
            j = badjson(p, t)
            real += r
            masked += m
            benign += b
            bad += j
            if r or j:
                offenders.append((os.path.basename(p), r, j))
        print('-' * 74)
        print('已遮蔽          : %d' % masked)
        print('保留的變數名    : %d  (%s)' % (benign, '／'.join(BENIGN.values())))
        print('真正殘留的明文  : %d   （必須是 0）' % real)
        print('JSON 壞行       : %d   （必須是 0）' % bad)
        for name, r, j in offenders:
            print('   ⚠ %s 殘留%d 壞行%d' % (name, r, j))
        return 0 if (real == 0 and bad == 0) else 1

    if not dry:
        os.makedirs(BACKUP, exist_ok=True)

    grand = grandkept = 0
    bad = []
    print('-' * 74)
    for p in files:
        with open(p, encoding='utf-8', errors='ignore') as fh:
            t = fh.read()
        new, n, kept = redact(t)
        grand += n
        grandkept += kept
        if dry:
            print('  %5d 處  %s' % (n, os.path.basename(p)))
            continue
        if n == 0:
            continue
        shutil.copy2(p, os.path.join(BACKUP, os.path.basename(p)))
        tmp = p + '.redact-tmp'
        with open(tmp, 'w', encoding='utf-8', newline='') as fh:
            fh.write(new)
        os.replace(tmp, p)
        with open(p, encoding='utf-8', errors='ignore') as fh:
            chk = fh.read()
        r, m, b = census(chk)
        j = badjson(p, chk)
        flag = ''
        if r:
            flag += ' ⚠殘留%d' % r
        if j:
            flag += ' ⚠壞行%d' % j
        if flag:
            bad.append(p)
        print('  %5d 處  %s%s' % (n, os.path.basename(p), flag or '  ✓'))

    print('-' * 74)
    print('遮蔽 %d 處；保留變數名 %d 處' % (grand, grandkept))
    if not dry:
        print('備份 = %s' % BACKUP)
        print('⚠ 備份裡仍有明文，確認無誤後請自行刪除。')
        print('問題檔 = %s' % (bad if bad else '無'))
    else:
        print('--dry-run：一個檔都沒動。')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
