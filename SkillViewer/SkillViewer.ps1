#requires -Version 5.1
<#
  SkillViewer — Claude Code Skill 瀏覽器（PowerShell WinForms 原生視窗）
  用途：工作時查看/翻閱目前有哪些 Claude Code skills（專案本地 + 平台通用），
  每張卡可一鍵複製 /指令，或直接貼到你指定的另一個視窗（例如正在跑 Claude Code 的終端機）。

  資料來源：
    - 專案本地：即時掃描 <ProjectPath>\.claude\skills\*\SKILL.md 的 frontmatter（name/description）。
    - 平台通用：讀同目錄 platform_skills.json 裡 origin=platform 的項目。
      ⚠ 2026-08-22 起這個 JSON **由 tools\skill_inventory.py 產生，請勿手動編輯**
      （下次產生會整批覆蓋）。要改內容請改產生器或它的來源；變動偵測的基準
      （baselines 區塊）由 tools\skill_watch_run.py 每日維護。

  用法：雙擊 Launch-SkillViewer.bat（雙擊 .ps1 只會用記事本開啟）。
  可選參數：-ProjectPath 指到別的專案（預設 D:\Patrick-AI\IT-department）。
#>
param(
  [string]$ProjectPath = "D:\Patrick-AI\IT-department"
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

# ── 隱藏本行程附著的主控台黑窗（沿用 ITAHC-Portable 已驗證手法）：
#    透過 Launch-SkillViewer.bat 啟動時，powershell.exe 仍會沿用 .bat 那個 cmd 主控台視窗；
#    GUI 開起來後這個黑窗沒有用途，藏起來即可（不影響 GUI 本身，之後要看輸出可拿掉這段自行除錯）。
try {
  Add-Type -Namespace SkillViewerNative -Name ConsoleUtil -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
[DllImport("user32.dll")]  public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
'@
  $consoleHwnd = [SkillViewerNative.ConsoleUtil]::GetConsoleWindow()
  if ($consoleHwnd -ne [IntPtr]::Zero) { [void][SkillViewerNative.ConsoleUtil]::ShowWindow($consoleHwnd, 0) }
} catch { }

# ── DPI 縮放：125%/150% 螢幕不裂版 ──
$g0 = [System.Drawing.Graphics]::FromHwnd([IntPtr]::Zero)
$script:UIScale = [double]($g0.DpiX / 96.0)
$g0.Dispose()
function S([double]$n) { return [int][math]::Round($n * $script:UIScale) }

# ── Win32：列舉可見視窗＋切前景（供「傳送到指定視窗」用）──
Add-Type -Namespace SkillViewerNative -Name Win32 -MemberDefinition @'
public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
[DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
'@

function Get-VisibleWindows {
  $list = New-Object System.Collections.Generic.List[object]
  $cb = {
    param($hWnd, $lParam)
    if ([SkillViewerNative.Win32]::IsWindowVisible($hWnd)) {
      $len = [SkillViewerNative.Win32]::GetWindowTextLength($hWnd)
      if ($len -gt 0) {
        $sb = New-Object System.Text.StringBuilder ($len + 1)
        [void][SkillViewerNative.Win32]::GetWindowText($hWnd, $sb, $sb.Capacity)
        $title = $sb.ToString().Trim()
        if ($title) { $list.Add([pscustomobject]@{ Title = $title; Handle = $hWnd }) }
      }
    }
    return $true
  }
  [void][SkillViewerNative.Win32]::EnumWindows($cb, [IntPtr]::Zero)
  return , $list
}

# ── 分類配色（卡片右上角小標籤）──
$script:CategoryColors = @{
  "收工/部署"  = @{ bg = [System.Drawing.Color]::FromArgb(219, 234, 254); fg = [System.Drawing.Color]::FromArgb(29, 78, 216) }
  "診斷/除錯"  = @{ bg = [System.Drawing.Color]::FromArgb(254, 226, 226); fg = [System.Drawing.Color]::FromArgb(185, 28, 28) }
  "工作追蹤"   = @{ bg = [System.Drawing.Color]::FromArgb(220, 252, 231); fg = [System.Drawing.Color]::FromArgb(6, 95, 70) }
  "研究/內容"  = @{ bg = [System.Drawing.Color]::FromArgb(237, 233, 254); fg = [System.Drawing.Color]::FromArgb(91, 33, 182) }
  "開發輔助"   = @{ bg = [System.Drawing.Color]::FromArgb(254, 243, 199); fg = [System.Drawing.Color]::FromArgb(146, 64, 14) }
  "環境設定"   = @{ bg = [System.Drawing.Color]::FromArgb(226, 232, 240); fg = [System.Drawing.Color]::FromArgb(71, 85, 105) }
  "其他"       = @{ bg = [System.Drawing.Color]::FromArgb(241, 245, 249); fg = [System.Drawing.Color]::FromArgb(100, 116, 139) }
}
# 專案本地 skill → 分類（新 skill 沒對到這裡會落「其他」；要調分類直接改這個表即可）
$script:LocalSkillCategoryMap = @{
  "shougong"          = "收工/部署"
  "deploy-prod"       = "收工/部署"
  "diagnose-bug"      = "診斷/除錯"
  "dry-run-migrate"   = "診斷/除錯"
  "codebase-health"   = "診斷/除錯"
  "suggestion-inbox"  = "工作追蹤"
}

# ===== GUI-SECTION =====（此線以上為純函式／資料，測試 harness 依此標記切分 dot-source）

function Get-LocalSkills([string]$projectPath) {
  $dir = Join-Path $projectPath ".claude\skills"
  if (-not (Test-Path -LiteralPath $dir)) { return @() }
  $result = New-Object System.Collections.Generic.List[object]
  Get-ChildItem -LiteralPath $dir -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    $skillFile = Join-Path $_.FullName "SKILL.md"
    if (-not (Test-Path -LiteralPath $skillFile)) { return }
    $content = Get-Content -LiteralPath $skillFile -Raw -Encoding UTF8
    $fm = [regex]::Match($content, '(?s)^---\s*\r?\n(.*?)\r?\n---')
    if (-not $fm.Success) { return }
    $front = $fm.Groups[1].Value
    $name = $_.Name
    $nm = [regex]::Match($front, '(?m)^name:\s*(.+?)\s*$')
    if ($nm.Success) { $name = $nm.Groups[1].Value.Trim() }
    $desc = ""
    $dm = [regex]::Match($front, '(?m)^description:\s*(.+?)\s*$')
    if ($dm.Success) { $desc = $dm.Groups[1].Value.Trim() }
    $cat = $script:LocalSkillCategoryMap[$name]
    if (-not $cat) { $cat = "其他" }
    $result.Add([pscustomobject]@{ Name = $name; Description = $desc; Category = $cat })
  }
  return , ($result.ToArray() | Sort-Object Category, Name)
}

function Get-PlatformSkills([string]$jsonPath) {
  if (-not (Test-Path -LiteralPath $jsonPath)) { return @() }
  try {
    $data = Get-Content -LiteralPath $jsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
    # 這個 JSON 自 2026-08-22 起由 tools\skill_inventory.py 產生，skills[] 裝三種
    # origin（platform / global / project）。這個面板叫「平台通用」，只該顯示 platform——
    # 不過濾的話專案 skill 會同時出現在兩個面板（實測 16 支重複），
    # 而狀態列會把 49 報成「平台通用」筆數（實際只有 24）。
    # 沒有 origin 欄的是升級前的舊格式，一律顯示以維持相容。
    $items = @($data.skills | Where-Object {
      (-not $_.PSObject.Properties['origin']) -or ($_.origin -eq 'platform')
    })
    $out = @($items | ForEach-Object { [pscustomobject]@{ Name = $_.name; Description = $_.description; Category = $_.category } })
    return , ($out | Sort-Object Category, Name)
  } catch { return @() }
}

function Get-SkillCategory($skillObj) {
  if ($skillObj -and $skillObj.Category) { return $skillObj.Category }
  return "其他"
}

# ===== GUI-SECTION-END =====

# ── GDI+ helpers（沿用 ITAHC-Portable 已驗證過的分槽/圓角元件手法）──
function New-RoundRectPath([single]$x, [single]$y, [single]$w, [single]$h, [single]$r) {
  $p = New-Object System.Drawing.Drawing2D.GraphicsPath
  $d = $r * 2
  $p.AddArc($x, $y, $d, $d, 180, 90)
  $p.AddArc($x + $w - $d, $y, $d, $d, 270, 90)
  $p.AddArc($x + $w - $d, $y + $h - $d, $d, $d, 0, 90)
  $p.AddArc($x, $y + $h - $d, $d, $d, 90, 90)
  $p.CloseFigure()
  return $p
}
function Enable-DoubleBuffer($ctrl) {
  $prop = [System.Windows.Forms.Control].GetProperty('DoubleBuffered', ([System.Reflection.BindingFlags]::Instance -bor [System.Reflection.BindingFlags]::NonPublic))
  $prop.SetValue($ctrl, $true, $null)
}

# ── Fluent/Copilot 風配色：中性淺灰頁面 + 白色浮起卡片(陰影非邊框) + 藍紫漸層強調色 ──
$colText     = [System.Drawing.Color]::FromArgb(32, 31, 30)
$colSoft     = [System.Drawing.Color]::FromArgb(96, 94, 92)
$colMuted    = [System.Drawing.Color]::FromArgb(150, 148, 146)
$colBrand    = [System.Drawing.Color]::FromArgb(43, 45, 130)     # 卡片標題／群組標題（沿用識別藍）
$colAccent1  = [System.Drawing.Color]::FromArgb(37, 99, 235)     # 漸層：藍
$colAccent2  = [System.Drawing.Color]::FromArgb(147, 51, 234)    # 漸層：紫（Copilot 識別語彙）
$colAccent1H = [System.Drawing.Color]::FromArgb(59, 130, 246)
$colAccent2H = [System.Drawing.Color]::FromArgb(168, 85, 247)
$colAccent1P = [System.Drawing.Color]::FromArgb(29, 78, 216)
$colAccent2P = [System.Drawing.Color]::FromArgb(126, 34, 206)
$colRed      = [System.Drawing.Color]::FromArgb(220, 38, 38)  # 保留：Set-Status 錯誤訊息用
$colCardBd   = [System.Drawing.Color]::FromArgb(232, 232, 232)
$colGhostHov = [System.Drawing.Color]::FromArgb(243, 243, 243)
$colGhostPrs = [System.Drawing.Color]::FromArgb(230, 230, 230)
$colPageBg   = [System.Drawing.Color]::FromArgb(243, 243, 243)  # Win11 Mica 中性灰
$colSurface  = [System.Drawing.Color]::White

$fontUI          = New-Object System.Drawing.Font('Microsoft JhengHei UI', 9.5)
$fontSmall       = New-Object System.Drawing.Font('Microsoft JhengHei UI', 8.5)
$fontCardTitle   = New-Object System.Drawing.Font('Consolas', 10.5, [System.Drawing.FontStyle]::Bold)
$fontDesc        = New-Object System.Drawing.Font('Microsoft JhengHei UI', 8.7)
$fontTag         = New-Object System.Drawing.Font('Microsoft JhengHei UI', 7.8, [System.Drawing.FontStyle]::Bold)
$fontGroupHeader = New-Object System.Drawing.Font('Microsoft JhengHei UI', 10.8, [System.Drawing.FontStyle]::Bold)
$fontStatus      = New-Object System.Drawing.Font('Microsoft JhengHei UI', 8.3)

# 主按鈕＝藍→紫漸層填色（Copilot 識別語彙）；次按鈕＝白底細框，維持樸素好讀
function New-FluentButton([string]$text, [int]$x, [int]$y, [int]$w, [int]$h, [string]$kind) {
  $b = New-Object System.Windows.Forms.Panel
  $b.Location = New-Object System.Drawing.Point($x, $y)
  $b.Size = New-Object System.Drawing.Size($w, $h)
  $b.Font = $fontSmall
  $b.Cursor = [System.Windows.Forms.Cursors]::Hand
  $b.Tag = @{ kind = $kind; text = $text; hover = $false; pressed = $false; enabled = $true; onClick = $null }
  $b.AccessibleRole = 'PushButton'  # Panel 預設 AccessibleRole 不會把 AccessibleName 曝露給 UIA/螢幕報讀器，補上才對得到
  $b.AccessibleName = $text
  Enable-DoubleBuffer $b
  $b.Add_Paint({
    param($sender, $e)
    $st = $sender.Tag
    $gr = $e.Graphics
    $gr.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $path = New-RoundRectPath 0.5 0.5 ($sender.Width - 1) ($sender.Height - 1) ([single](S 6))
    if ($st.kind -eq 'primary') {
      $c1 = $script:colAccent1; $c2 = $script:colAccent2
      if ($st.pressed) { $c1 = $script:colAccent1P; $c2 = $script:colAccent2P }
      elseif ($st.hover) { $c1 = $script:colAccent1H; $c2 = $script:colAccent2H }
      $fg = [System.Drawing.Color]::White
      $rectF = New-Object System.Drawing.RectangleF(0, 0, $sender.Width, $sender.Height)
      $gbrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush($rectF, $c1, $c2, 30.0)
      $gr.FillPath($gbrush, $path); $gbrush.Dispose()
    } else {
      $fill = [System.Drawing.Color]::White
      if ($st.pressed) { $fill = $script:colGhostPrs } elseif ($st.hover) { $fill = $script:colGhostHov }
      $fg = $script:colText
      $br = New-Object System.Drawing.SolidBrush($fill); $gr.FillPath($br, $path); $br.Dispose()
      $bd = if ($st.hover) { $script:colAccent1 } else { $script:colCardBd }
      $pen = New-Object System.Drawing.Pen($bd, 1); $gr.DrawPath($pen, $path); $pen.Dispose()
    }
    $path.Dispose()
    $rect = New-Object System.Drawing.Rectangle(0, 0, $sender.Width, $sender.Height)
    $flags = ([System.Windows.Forms.TextFormatFlags]::HorizontalCenter -bor [System.Windows.Forms.TextFormatFlags]::VerticalCenter)
    [System.Windows.Forms.TextRenderer]::DrawText($gr, $st.text, $sender.Font, $rect, $fg, $flags)
  })
  $b.Add_MouseEnter({ $this.Tag.hover = $true; $this.Invalidate() })
  $b.Add_MouseLeave({ $this.Tag.hover = $false; $this.Tag.pressed = $false; $this.Invalidate() })
  $b.Add_MouseDown({ $this.Tag.pressed = $true; $this.Invalidate() })
  $b.Add_MouseUp({ $this.Tag.pressed = $false; $this.Invalidate() })
  $b.Add_Click({ if ($this.Tag.onClick) { & $this.Tag.onClick } })
  return $b
}

# 分類標籤＝真正的圓角膠囊（Panel 自繪，非 Label+BackColor 那種方形色塊）
function New-RoundedTag([string]$text, $bgColor, $fgColor) {
  $p = New-Object System.Windows.Forms.Panel
  $p.Font = $fontTag
  Enable-DoubleBuffer $p
  $sz = [System.Windows.Forms.TextRenderer]::MeasureText($text, $fontTag)
  $p.Size = New-Object System.Drawing.Size(($sz.Width + (S 16)), ($sz.Height + (S 7)))
  $p.Tag = @{ bg = $bgColor; fg = $fgColor; text = $text }
  $p.Add_Paint({
    param($sender, $e)
    $st = $sender.Tag
    $gr = $e.Graphics
    $gr.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $rad = [single]($sender.Height / 2.0)
    $path = New-RoundRectPath 0.5 0.5 ($sender.Width - 1) ($sender.Height - 1) $rad
    $br = New-Object System.Drawing.SolidBrush($st.bg)
    $gr.FillPath($br, $path); $br.Dispose(); $path.Dispose()
    $rect = New-Object System.Drawing.Rectangle(0, 0, $sender.Width, $sender.Height)
    $flags = ([System.Windows.Forms.TextFormatFlags]::HorizontalCenter -bor [System.Windows.Forms.TextFormatFlags]::VerticalCenter)
    [System.Windows.Forms.TextRenderer]::DrawText($gr, $st.text, $sender.Font, $rect, $st.fg, $flags)
  })
  return $p
}

# 無邊框圓角輸入框（借鏡 ITAHC-Portable 分槽輸入的 FluentEntry 手法）：白底圓角、聚焦轉強調色
function New-FluentTextBox([int]$x, [int]$y, [int]$w, [int]$h, [string]$initialText) {
  $wrap = New-Object System.Windows.Forms.Panel
  $wrap.Location = New-Object System.Drawing.Point($x, $y)
  $wrap.Size = New-Object System.Drawing.Size($w, $h)
  $wrap.BackColor = [System.Drawing.Color]::White
  Enable-DoubleBuffer $wrap
  $wrap.Tag = @{ focus = $false }
  $tb = New-Object System.Windows.Forms.TextBox
  $tb.BorderStyle = 'None'
  $tb.Font = $fontUI
  $tb.BackColor = [System.Drawing.Color]::White
  $tb.ForeColor = $colText
  if ($initialText) { $tb.Text = $initialText }
  $wrap.Controls.Add($tb)
  $tb.Left = S 10
  $tb.Width = $w - (S 20)
  $tb.Top = [int](($h - $tb.PreferredHeight) / 2)
  $wrap.Add_Paint({
    param($sender, $e)
    $gr = $e.Graphics
    $gr.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $path = New-RoundRectPath 0.5 0.5 ($sender.Width - 1) ($sender.Height - 1) ([single](S 6))
    $br = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
    $gr.FillPath($br, $path); $br.Dispose()
    $bd = if ($sender.Tag.focus) { $script:colAccent1 } else { $script:colCardBd }
    $bw = if ($sender.Tag.focus) { 1.6 } else { 1.0 }
    $pen = New-Object System.Drawing.Pen($bd, $bw)
    $gr.DrawPath($pen, $path); $pen.Dispose(); $path.Dispose()
  })
  $tb.Add_GotFocus({ $this.Parent.Tag.focus = $true; $this.Parent.Invalidate() })
  $tb.Add_LostFocus({ $this.Parent.Tag.focus = $false; $this.Parent.Invalidate() })
  return @{ wrap = $wrap; box = $tb }
}

# ── 主視窗 ──
$form = New-Object System.Windows.Forms.Form
$form.Text = "Claude Code Skill 瀏覽器"
$form.ClientSize = New-Object System.Drawing.Size((S 960), (S 700))
$form.FormBorderStyle = 'FixedSingle'
$form.MaximizeBox = $false
$form.StartPosition = 'CenterScreen'
$form.Font = $fontUI
$form.BackColor = $colPageBg

$script:AllLocalSkills = @()
$script:AllPlatformSkills = @()
$script:CurrentWindows = @()
$script:SelectedWindowHandle = [IntPtr]::Zero
$script:SelectedWindowTitle = ""

function Set-Status([string]$msg, [bool]$isWarn = $false) {
  $statusLbl.Text = $msg
  $statusLbl.ForeColor = if ($isWarn) { $colRed } else { $colSoft }
}

function Send-ToTargetWindow([string]$text) {
  if ($script:SelectedWindowHandle -eq [IntPtr]::Zero) {
    [void][System.Windows.Forms.MessageBox]::Show($form, "請先在上方「目標視窗」選一個視窗。", "SkillViewer", 'OK', 'Warning')
    return
  }
  $fresh = Get-VisibleWindows
  $stillValid = $fresh | Where-Object { $_.Handle -eq $script:SelectedWindowHandle }
  if (-not $stillValid) {
    Set-Status "目標視窗已關閉或找不到了，請重新選擇。" $true
    return
  }
  [void][SkillViewerNative.Win32]::SetForegroundWindow($script:SelectedWindowHandle)
  Start-Sleep -Milliseconds 150
  [System.Windows.Forms.Clipboard]::SetText($text)
  [System.Windows.Forms.SendKeys]::SendWait("^v")
  Set-Status ("已貼上 {0} → {1}（尚未送出，請自行確認後按 Enter）" -f $text, $script:SelectedWindowTitle)
}

# ── 頂部工具列 ──
$toolbar = New-Object System.Windows.Forms.Panel
$toolbar.Location = New-Object System.Drawing.Point(0, 0)
$toolbar.Size = New-Object System.Drawing.Size((S 960), (S 92))
$toolbar.BackColor = [System.Drawing.Color]::White
$form.Controls.Add($toolbar)

$toolbar.Controls.Add((New-Object System.Windows.Forms.Label -Property @{ Text = "專案路徑"; Location = (New-Object System.Drawing.Point((S 14), (S 12))); Size = (New-Object System.Drawing.Size((S 60), (S 22))); ForeColor = $colSoft }))
$projectPathEntry = New-FluentTextBox (S 76) (S 8) (S 360) (S 28) $ProjectPath
$toolbar.Controls.Add($projectPathEntry.wrap)
$projectPathBox = $projectPathEntry.box

$refreshBtn = New-FluentButton "🔄 重新整理" (S 446) (S 8) (S 110) (S 28) "ghost"
$toolbar.Controls.Add($refreshBtn)

$toolbar.Controls.Add((New-Object System.Windows.Forms.Label -Property @{ Text = "🔍"; Location = (New-Object System.Drawing.Point((S 572), (S 12))); Size = (New-Object System.Drawing.Size((S 20), (S 22))) }))
$searchEntry = New-FluentTextBox (S 594) (S 8) (S 200) (S 28) ""
$toolbar.Controls.Add($searchEntry.wrap)
$searchBox = $searchEntry.box

$toolbar.Controls.Add((New-Object System.Windows.Forms.Label -Property @{ Text = "目標視窗"; Location = (New-Object System.Drawing.Point((S 14), (S 52))); Size = (New-Object System.Drawing.Size((S 60), (S 22))); ForeColor = $colSoft }))
$targetCombo = New-Object System.Windows.Forms.ComboBox
$targetCombo.Location = New-Object System.Drawing.Point((S 76), (S 48))
$targetCombo.Size = New-Object System.Drawing.Size((S 700), (S 24))
$targetCombo.DropDownStyle = 'DropDownList'
$targetCombo.FlatStyle = 'Flat'
$targetCombo.AccessibleName = "target-window-combo"
$toolbar.Controls.Add($targetCombo)
$toolbar.Controls.Add((New-Object System.Windows.Forms.Label -Property @{ Text = "傳送＝切到該視窗貼上文字，不會自動按 Enter，需你自行確認送出"; Location = (New-Object System.Drawing.Point((S 76), (S 72))); Size = (New-Object System.Drawing.Size((S 700), (S 18))); Font = $fontStatus; ForeColor = $colMuted }))

function Refresh-WindowList {
  $script:CurrentWindows = @(Get-VisibleWindows | Where-Object { $_.Title -ne $form.Text } | Sort-Object Title)
  $prevTitle = $targetCombo.Text
  $targetCombo.Items.Clear()
  foreach ($w in $script:CurrentWindows) { [void]$targetCombo.Items.Add($w.Title) }
  $restoreIdx = $targetCombo.Items.IndexOf($prevTitle)
  if ($restoreIdx -ge 0) { $targetCombo.SelectedIndex = $restoreIdx }
}
$targetCombo.Add_DropDown({ Refresh-WindowList })
$targetCombo.Add_SelectedIndexChanged({
  $idx = $targetCombo.SelectedIndex
  if ($idx -ge 0 -and $idx -lt $script:CurrentWindows.Count) {
    $script:SelectedWindowHandle = $script:CurrentWindows[$idx].Handle
    $script:SelectedWindowTitle = $script:CurrentWindows[$idx].Title
  }
})

# ── 分頁 ──
$tabs = New-Object System.Windows.Forms.TabControl
$tabs.Location = New-Object System.Drawing.Point(0, (S 92))
$tabs.Size = New-Object System.Drawing.Size((S 960), (S 578))
$form.Controls.Add($tabs)

$tabLocal = New-Object System.Windows.Forms.TabPage
$tabLocal.Text = "專案本地"
$tabs.Controls.Add($tabLocal)
$tabPlatform = New-Object System.Windows.Forms.TabPage
$tabPlatform.Text = "平台通用"
$tabs.Controls.Add($tabPlatform)

function New-SkillFlowPanel([System.Windows.Forms.TabPage]$parent) {
  $p = New-Object System.Windows.Forms.FlowLayoutPanel
  $p.Dock = 'Fill'
  $p.AutoScroll = $true
  $p.BackColor = $colPageBg
  $p.Padding = New-Object System.Windows.Forms.Padding((S 10))
  $parent.Controls.Add($p)
  return $p
}
$localPanel = New-SkillFlowPanel $tabLocal
$platformPanel = New-SkillFlowPanel $tabPlatform

$script:CardShadowPad = S 7   # 卡片控件比視覺卡面多留的邊，供陰影延伸不被裁掉
$script:CardFaceW = S 280
$script:CardFaceH = S 192

function New-SkillCard($skillObj) {
  $cmdName = $skillObj.Name
  $description = $skillObj.Description
  $category = Get-SkillCategory $skillObj
  $faceW = $script:CardFaceW
  $faceH = $script:CardFaceH
  $pad = $script:CardShadowPad

  $card = New-Object System.Windows.Forms.Panel
  $card.Size = New-Object System.Drawing.Size(($faceW + $pad), ($faceH + $pad))
  $card.Margin = New-Object System.Windows.Forms.Padding((S 8))
  $card.BackColor = $script:colPageBg
  $card.Tag = @{ hover = $false }
  Enable-DoubleBuffer $card
  $card.Add_Paint({
    param($sender, $e)
    $st = $sender.Tag
    $gr = $e.Graphics
    $gr.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $rad = [single](S 10)
    $fw = $script:CardFaceW; $fh = $script:CardFaceH
    # 柔和陰影：多層小offset＋遞減透明度疊出模糊感（無邊框、靠陰影分離卡片與底色）
    for ($i = 4; $i -ge 1; $i--) {
      $alpha = 4 * (5 - $i)
      $sp = New-RoundRectPath $i $i ($fw - 1) ($fh - 1) $rad
      $sb = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb($alpha, 20, 20, 35))
      $gr.FillPath($sb, $sp); $sb.Dispose(); $sp.Dispose()
    }
    $path = New-RoundRectPath 0.5 0.5 ($fw - 1) ($fh - 1) $rad
    $br = New-Object System.Drawing.SolidBrush($script:colSurface)
    $gr.FillPath($br, $path); $br.Dispose()
    $bd = if ($st.hover) { $script:colAccent1 } else { $script:colCardBd }
    $bw = if ($st.hover) { 1.4 } else { 1.0 }
    $pen = New-Object System.Drawing.Pen($bd, $bw)
    $gr.DrawPath($pen, $path); $pen.Dispose()
    $path.Dispose()
  })
  $card.Add_MouseEnter({ $this.Tag.hover = $true; $this.Invalidate() })
  $card.Add_MouseLeave({ $this.Tag.hover = $false; $this.Invalidate() })

  $nameLbl = New-Object System.Windows.Forms.Label
  $nameLbl.Text = "/$cmdName"
  $nameLbl.Font = $fontCardTitle
  $nameLbl.ForeColor = $colBrand
  $nameLbl.AutoSize = $true
  $nameLbl.BackColor = [System.Drawing.Color]::Transparent
  $nameLbl.Location = New-Object System.Drawing.Point((S 14), (S 12))
  $card.Controls.Add($nameLbl)

  $tagColors = $script:CategoryColors[$category]
  if (-not $tagColors) { $tagColors = $script:CategoryColors["其他"] }
  $tag = New-RoundedTag $category $tagColors.bg $tagColors.fg
  $card.Controls.Add($tag)
  $tag.Location = New-Object System.Drawing.Point(($faceW - $tag.Width - (S 12)), (S 12))

  $descLbl = New-Object System.Windows.Forms.Label
  $descLbl.Text = $description
  $descLbl.Font = $fontDesc
  $descLbl.ForeColor = $colSoft
  $descLbl.AutoSize = $false
  $descLbl.BackColor = [System.Drawing.Color]::Transparent
  $descLbl.Location = New-Object System.Drawing.Point((S 14), (S 38))
  $descLbl.Size = New-Object System.Drawing.Size(($faceW - (S 28)), (S 104))
  $card.Controls.Add($descLbl)

  $copyBtn = New-FluentButton "複製" (S 14) ($faceH - (S 42)) (S 96) (S 30) "ghost"
  $copyBtn.AccessibleName = "copy-btn:$cmdName"
  $copyBtn.Tag.onClick = {
    [System.Windows.Forms.Clipboard]::SetText("/$cmdName")
    Set-Status "已複製 /$cmdName"
  }.GetNewClosure()
  $card.Controls.Add($copyBtn)

  $sendBtn = New-FluentButton "傳送到視窗" ($faceW - (S 122)) ($faceH - (S 42)) (S 110) (S 30) "primary"
  $sendBtn.AccessibleName = "send-btn:$cmdName"
  $sendBtn.Tag.onClick = { Send-ToTargetWindow "/$cmdName" }.GetNewClosure()
  $card.Controls.Add($sendBtn)

  return $card
}

function Render-SkillGroup([System.Windows.Forms.FlowLayoutPanel]$panel, [array]$skills) {
  $panel.SuspendLayout()
  $panel.Controls.Clear()
  $headerWidth = (S 920)
  $byCategory = @($skills) | Group-Object Category | Sort-Object Name
  foreach ($grp in $byCategory) {
    $header = New-Object System.Windows.Forms.Label
    $header.Text = "{0}（{1}）" -f $grp.Name, $grp.Count
    $header.Font = $fontGroupHeader
    $header.ForeColor = $colBrand
    $header.AutoSize = $false
    $header.Size = New-Object System.Drawing.Size($headerWidth, (S 28))
    $header.Margin = New-Object System.Windows.Forms.Padding((S 4), (S 12), (S 4), (S 4))
    [void]$panel.Controls.Add($header)
    foreach ($sk in ($grp.Group | Sort-Object Name)) {
      [void]$panel.Controls.Add((New-SkillCard $sk))
    }
  }
  if (-not $byCategory) {
    $empty = New-Object System.Windows.Forms.Label
    $empty.Text = "（沒有符合的 skill）"
    $empty.ForeColor = $colMuted
    $empty.AutoSize = $true
    $empty.Location = New-Object System.Drawing.Point((S 10), (S 10))
    [void]$panel.Controls.Add($empty)
  }
  $panel.ResumeLayout()
}

function Test-SkillMatch($sk, [string]$q) {
  if (-not $q) { return $true }
  return ($sk.Name.ToLower().Contains($q)) -or ($sk.Description.ToLower().Contains($q)) -or ($sk.Category.ToLower().Contains($q))
}

function Refresh-All {
  $script:AllLocalSkills = @(Get-LocalSkills $projectPathBox.Text)
  $script:AllPlatformSkills = @(Get-PlatformSkills (Join-Path $PSScriptRoot "platform_skills.json"))
  Apply-Filter
  Refresh-WindowList
  Set-Status ("已重新整理：專案本地 {0} 筆／平台通用 {1} 筆" -f $script:AllLocalSkills.Count, $script:AllPlatformSkills.Count)
}
function Apply-Filter {
  $q = $searchBox.Text.Trim().ToLower()
  Render-SkillGroup $localPanel (@($script:AllLocalSkills | Where-Object { Test-SkillMatch $_ $q }))
  Render-SkillGroup $platformPanel (@($script:AllPlatformSkills | Where-Object { Test-SkillMatch $_ $q }))
}

$refreshBtn.Tag.onClick = { Refresh-All }
$searchBox.Add_TextChanged({ Apply-Filter })
$projectPathBox.Add_KeyDown({ if ($_.KeyCode -eq [System.Windows.Forms.Keys]::Enter) { $_.SuppressKeyPress = $true; Refresh-All } })

# ── 底部狀態列 ──
$statusBar = New-Object System.Windows.Forms.Panel
$statusBar.Location = New-Object System.Drawing.Point(0, (S 670))
$statusBar.Size = New-Object System.Drawing.Size((S 960), (S 30))
$statusBar.BackColor = [System.Drawing.Color]::White
$form.Controls.Add($statusBar)
$statusLbl = New-Object System.Windows.Forms.Label
$statusLbl.Location = New-Object System.Drawing.Point((S 14), (S 6))
$statusLbl.Size = New-Object System.Drawing.Size((S 930), (S 20))
$statusLbl.Font = $fontStatus
$statusLbl.ForeColor = $colSoft
$statusBar.Controls.Add($statusLbl)

$form.Add_Shown({ Refresh-All })
[System.Windows.Forms.Application]::Run($form)
