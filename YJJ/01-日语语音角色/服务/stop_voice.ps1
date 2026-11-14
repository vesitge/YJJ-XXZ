# stop_voice.ps1 - 关掉语音助手，只动它自己的进程
#
# 判据只有两条：
#   1. 可执行文件在 GPT-SoVITS-v5\runtime 下（整合包那个 python：9890 服务、9888 TTS、托盘）
#   2. 占着 9890 / 9888 且确实是 python
# 系统 python、别的项目、别的端口，一概不碰。
#
# 关闭助手.bat 只负责把这里叫起来（那个文件保持纯 ASCII，cmd 才不会把中文读乱）。

$ErrorActionPreference = 'SilentlyContinue'

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$here = $PSScriptRoot
if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }
$root = Split-Path -Parent (Split-Path -Parent $here)   # tools\voicechat -> 工作区根
$runtime = Join-Path $root 'GPT-SoVITS-v5\runtime'
$serviceDir = Join-Path $root 'tools\voicechat'
$marker = Join-Path $serviceDir 'autostart.off'

Write-Host ''
Write-Host '==== 关闭助手 ===='
Write-Host '只停语音助手自己的进程（整合包 runtime 的 python + 9890/9888），别的一概不碰'

# 真关了：先留记号，DSH 插件看到它就不再自动拉起
try {
  if (-not (Test-Path $marker)) { New-Item -ItemType File -Path $marker -Force | Out-Null }
  Write-Host '已留记号 autostart.off：插件不会再把服务偷偷拉起来'
} catch {
  Write-Host ('记号没写成功：' + $_.Exception.Message)
}

$targets = @{}

# 判据 1：整合包 runtime 下的 python
foreach ($p in @(Get-Process -Name python, pythonw)) {
  $exe = ''
  try { $exe = [string]$p.Path } catch { $exe = '' }
  if ($exe -and $exe.StartsWith($runtime, [System.StringComparison]::OrdinalIgnoreCase)) {
    $targets[$p.Id] = '整合包 python'
  }
}

# 判据 2：占着 9890 / 9888 的 python（netstat 解析，NetTCPIP 模块在受限环境里未必查得到）
$portOwner = @{}
foreach ($line in @(& netstat -ano)) {
  if ($line -notmatch 'LISTENING') { continue }
  foreach ($port in 9890, 9888) {
    if ($line -notmatch (':' + $port + '\s')) { continue }
    $cols = ($line -replace '\s+', ' ').Trim().Split(' ')
    $last = $cols[$cols.Length - 1]
    if ($last -match '^\d+$') { $portOwner[[int]$last] = $port }
  }
}

foreach ($ownerId in $portOwner.Keys) {
  $owner = Get-Process -Id $ownerId
  if ($owner -and ($owner.ProcessName -eq 'python' -or $owner.ProcessName -eq 'pythonw')) {
    if (-not $targets.ContainsKey($ownerId)) { $targets[$ownerId] = ('占着 ' + $portOwner[$ownerId] + ' 的 python') }
  } elseif ($owner) {
    Write-Host ('  端口 ' + $portOwner[$ownerId] + ' 被 ' + $owner.ProcessName + '（pid ' + $ownerId + '）占着，不是 python，不动')
  }
}

if ($targets.Count -eq 0) {
  Write-Host '语音助手没在跑，没有可关的进程。'
} else {
  foreach ($targetId in ($targets.Keys | Sort-Object)) {
    $proc = Get-Process -Id $targetId
    $procName = if ($proc) { $proc.ProcessName } else { '?' }
    Write-Host ('  结束 pid ' + $targetId + '（' + $procName + '，' + $targets[$targetId] + '）')
    Stop-Process -Id $targetId -Force
  }
  Start-Sleep -Milliseconds 500
}

$left = @()
foreach ($targetId in $targets.Keys) {
  if (Get-Process -Id $targetId) { $left += $targetId }
}

Write-Host ''
Write-Host '---- 端口 ----'
foreach ($port in 9890, 9888) {
  $busy = @(& netstat -ano | Select-String -Pattern (':' + $port + '\s') | Select-String -Pattern 'LISTENING')
  if ($busy.Count -eq 0) {
    Write-Host ('  ' + $port + ' 已关')
  } else {
    Write-Host ('  ' + $port + ' 还占着')
  }
}

Write-Host ''
if ($left.Count -gt 0) {
  Write-Host ('还有没结束的：' + ($left -join ', '))
  exit 1
}
Write-Host ('搞定，结束了 ' + $targets.Count + ' 个进程。要再开就双击「开始对话.bat」。')
exit 0
