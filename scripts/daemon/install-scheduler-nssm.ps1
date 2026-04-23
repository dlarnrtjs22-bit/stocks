# NSSM 기반 Windows 서비스 설치 스크립트
# Design Ref: Design §1.1 System Topology - scheduler.py 상주 데몬
# Plan §5 자동 반복 루프
#
# 사전 요구사항:
#   1. NSSM 설치: https://nssm.cc/download
#      또는: choco install nssm
#   2. 관리자 권한 PowerShell로 실행
#
# 사용법:
#   관리자 PowerShell 에서:
#     .\scripts\daemon\install-scheduler-nssm.ps1 install
#     .\scripts\daemon\install-scheduler-nssm.ps1 start
#     .\scripts\daemon\install-scheduler-nssm.ps1 stop
#     .\scripts\daemon\install-scheduler-nssm.ps1 status
#     .\scripts\daemon\install-scheduler-nssm.ps1 uninstall

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('install', 'start', 'stop', 'restart', 'status', 'uninstall', 'logs')]
    [string]$Action
)

$ErrorActionPreference = "Stop"

$ServiceName = "StocksScheduler"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = (Get-ChildItem 'C:\Users\*\AppData\Local\Programs\Python\Python314\python.exe' -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName)
if (-not $Python) {
    $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $Python) { throw "python.exe 를 찾을 수 없습니다." }

$LogDir = Join-Path $ProjectRoot "runtime\logs"
$StdoutLog = Join-Path $LogDir "scheduler.stdout.log"
$StderrLog = Join-Path $LogDir "scheduler.stderr.log"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Test-NssmInstalled {
    $nssm = Get-Command nssm -ErrorAction SilentlyContinue
    if (-not $nssm) {
        Write-Host "NSSM 이 설치되어 있지 않습니다." -ForegroundColor Red
        Write-Host "설치: https://nssm.cc/download 또는 'choco install nssm'"
        exit 1
    }
    return $nssm.Source
}

switch ($Action) {
    'install' {
        $nssm = Test-NssmInstalled
        Write-Host "Installing $ServiceName..."
        & $nssm install $ServiceName $Python "-X" "utf8" "-m" "batch.runtime_source.scheduler"
        & $nssm set $ServiceName AppDirectory $ProjectRoot
        & $nssm set $ServiceName AppEnvironmentExtra "PYTHONPATH=$ProjectRoot\.pydeps;$ProjectRoot" "PYTHONIOENCODING=utf-8" "PYTHONUNBUFFERED=1"
        & $nssm set $ServiceName AppStdout $StdoutLog
        & $nssm set $ServiceName AppStderr $StderrLog
        & $nssm set $ServiceName AppStdoutCreationDisposition 4  # Append
        & $nssm set $ServiceName AppStderrCreationDisposition 4
        & $nssm set $ServiceName AppRotateFiles 1
        & $nssm set $ServiceName AppRotateBytes 10485760  # 10MB
        & $nssm set $ServiceName Start SERVICE_AUTO_START
        & $nssm set $ServiceName AppExit Default Restart
        & $nssm set $ServiceName AppRestartDelay 15000  # 15초 후 재시작
        & $nssm set $ServiceName DisplayName "Stocks Auto-Trade Scheduler"
        & $nssm set $ServiceName Description "NXT 종가배팅 자동매매 루프 (Restart=always, logs in runtime/logs/scheduler.*.log)"
        Write-Host "Installed. Use '.\install-scheduler-nssm.ps1 start' to begin."
        Write-Host ""
        Write-Host "주의: 서비스가 자동매매 주문을 발사하려면 다음도 필요합니다:" -ForegroundColor Yellow
        Write-Host "  1. .bkit/state/auto_trade_enabled = 1"
        Write-Host "  2. .bkit/state/trading_mode = mock  (또는 real)"
        Write-Host "  3. 키움 appkey/secretkey 파일 존재"
    }
    'start' {
        $nssm = Test-NssmInstalled
        & $nssm start $ServiceName
    }
    'stop' {
        $nssm = Test-NssmInstalled
        & $nssm stop $ServiceName
    }
    'restart' {
        $nssm = Test-NssmInstalled
        & $nssm restart $ServiceName
    }
    'status' {
        $nssm = Test-NssmInstalled
        & $nssm status $ServiceName
        Get-Service $ServiceName -ErrorAction SilentlyContinue | Format-Table Name, Status, StartType -AutoSize
        Write-Host ""
        Write-Host "최근 stdout (10줄):"
        if (Test-Path $StdoutLog) {
            Get-Content $StdoutLog -Tail 10
        } else {
            Write-Host "  (없음)"
        }
        Write-Host ""
        Write-Host "최근 stderr (10줄):"
        if (Test-Path $StderrLog) {
            Get-Content $StderrLog -Tail 10
        } else {
            Write-Host "  (없음)"
        }
    }
    'logs' {
        Write-Host "stdout: $StdoutLog"
        Write-Host "stderr: $StderrLog"
        Write-Host "---- stdout (tail -f) ----"
        Get-Content $StdoutLog -Wait -Tail 50
    }
    'uninstall' {
        $nssm = Test-NssmInstalled
        & $nssm stop $ServiceName confirm
        & $nssm remove $ServiceName confirm
        Write-Host "Uninstalled."
    }
}
