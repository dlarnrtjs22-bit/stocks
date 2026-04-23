# Windows Task Scheduler 기반 scheduler 상주 (NSSM 없이 돌리는 대안)
# Design Ref: Design §1.1 - systemd 등가 Windows 솔루션
#
# 장점: NSSM 설치 불필요, 기본 내장
# 단점: 서비스가 아니라 task라서 관리가 조금 덜 깔끔
#
# 사용법 (관리자 PowerShell):
#   .\scripts\daemon\install-scheduler-taskscheduler.ps1 install
#   .\scripts\daemon\install-scheduler-taskscheduler.ps1 start
#   .\scripts\daemon\install-scheduler-taskscheduler.ps1 status
#   .\scripts\daemon\install-scheduler-taskscheduler.ps1 stop
#   .\scripts\daemon\install-scheduler-taskscheduler.ps1 uninstall

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('install', 'start', 'stop', 'status', 'uninstall')]
    [string]$Action
)

$ErrorActionPreference = "Stop"

$TaskName = "StocksScheduler"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = (Get-ChildItem 'C:\Users\*\AppData\Local\Programs\Python\Python314\python.exe' -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName)
if (-not $Python) { $Python = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $Python) { throw "python.exe 를 찾을 수 없습니다." }

$LogDir = Join-Path $ProjectRoot "runtime\logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

switch ($Action) {
    'install' {
        # Wrapper 배치 (환경변수 세팅 + Python 실행 + 로그 리다이렉트)
        $WrapperPath = Join-Path $PSScriptRoot "run-scheduler.cmd"
        $WrapperContent = @"
@echo off
cd /d "$ProjectRoot"
set PYTHONPATH=$ProjectRoot\.pydeps;$ProjectRoot
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
"$Python" -X utf8 -u -m batch.runtime_source.scheduler >> "$LogDir\scheduler.stdout.log" 2>> "$LogDir\scheduler.stderr.log"
"@
        Set-Content -Path $WrapperPath -Value $WrapperContent -Encoding ASCII
        Write-Host "Wrapper 생성: $WrapperPath"

        $action = New-ScheduledTaskAction -Execute $WrapperPath
        $trigger = New-ScheduledTaskTrigger -AtStartup
        # OnLogon 도 함께 등록 (PC 재시작/로그온 모두 대응)
        $trigger2 = New-ScheduledTaskTrigger -AtLogOn
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 0)
        $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Highest

        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($trigger, $trigger2) -Settings $settings -Principal $principal -Force | Out-Null
        Write-Host "Task installed: $TaskName" -ForegroundColor Green
        Write-Host ""
        Write-Host "주의:" -ForegroundColor Yellow
        Write-Host "  1. .bkit/state/auto_trade_enabled = 1 해야 주문 발사됨"
        Write-Host "  2. 처음엔 paper_mode=1 + trading_mode=mock 유지 권장"
    }
    'start' {
        Start-ScheduledTask -TaskName $TaskName
        Write-Host "Started."
    }
    'stop' {
        Stop-ScheduledTask -TaskName $TaskName
        Write-Host "Stopped."
    }
    'status' {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($task) {
            $info = Get-ScheduledTaskInfo -TaskName $TaskName
            Write-Host "TaskName: $($task.TaskName)"
            Write-Host "State: $($task.State)"
            Write-Host "LastRunTime: $($info.LastRunTime)"
            Write-Host "LastResult: $($info.LastTaskResult)"
            Write-Host "NextRunTime: $($info.NextRunTime)"
            Write-Host "NumberOfMissedRuns: $($info.NumberOfMissedRuns)"
        } else {
            Write-Host "Task not installed." -ForegroundColor Yellow
        }
        Write-Host ""
        $stdout = Join-Path $LogDir "scheduler.stdout.log"
        if (Test-Path $stdout) {
            Write-Host "---- stdout tail (10줄) ----"
            Get-Content $stdout -Tail 10
        }
    }
    'uninstall' {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Uninstalled."
    }
}
