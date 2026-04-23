# Scheduler 데몬 상주화 가이드

자동매매 루프(`scheduler.py`)를 **항상 살아있는 서비스**로 돌리는 방법.

## 공통 요구사항

### 사전 체크
```bash
# 1. 상태 파일 준비 (없으면 기본값 — 안전)
cat .bkit/state/auto_trade_enabled  # 0 (OFF, 기본 안전값)
cat .bkit/state/paper_mode          # 1 (ON, 기본 안전값)
cat .bkit/state/trading_mode        # mock (기본 안전값)

# 2. 키움 키 파일 존재 확인
ls 58416417_appkey.txt 58416417_secretkey.txt
# (선택) 모의투자 전용 키
ls 58416417_appkey_mock.txt 58416417_secretkey_mock.txt
```

### scheduler가 실제 주문 발사하는 조건
1. `auto_trade_enabled = 1` (Kill Switch ON)
2. 개별 job이 `.bkit/state/disabled_jobs`에 없을 것
3. `paper_mode = 0` 이어야 실주문 (1이면 감사 로그만)
4. `trading_mode = mock` → mockapi.kiwoom.com / `real` → api.kiwoom.com

---

## Windows — 옵션 A: NSSM (권장)

NSSM은 일반 EXE를 Windows Service로 감싸주는 도구. Service 관리자에서 확인 가능.

### 설치
```powershell
# 1. NSSM 설치 (한 번만)
choco install nssm
# 또는 https://nssm.cc/download 에서 수동 설치 후 PATH 등록

# 2. 관리자 PowerShell 열고
cd C:\codex\stocks_new
.\scripts\daemon\install-scheduler-nssm.ps1 install
.\scripts\daemon\install-scheduler-nssm.ps1 start
```

### 운영 명령
```powershell
.\scripts\daemon\install-scheduler-nssm.ps1 status    # 현재 상태 + 최근 로그
.\scripts\daemon\install-scheduler-nssm.ps1 restart   # 재시작
.\scripts\daemon\install-scheduler-nssm.ps1 logs      # tail -f
.\scripts\daemon\install-scheduler-nssm.ps1 stop
.\scripts\daemon\install-scheduler-nssm.ps1 uninstall
```

### 특징
- `services.msc` 에서 **StocksScheduler** 이름으로 보임
- 크래시 시 15초 후 자동 재시작 (`AppExit Default Restart`)
- 로그: `runtime/logs/scheduler.stdout.log` / `scheduler.stderr.log`
- 로그 10MB 넘으면 자동 로테이션

---

## Windows — 옵션 B: Task Scheduler (NSSM 설치 불원)

Windows 기본 내장 스케줄러 사용. NSSM 설치 없이 상주.

### 설치
```powershell
# 관리자 PowerShell
cd C:\codex\stocks_new
.\scripts\daemon\install-scheduler-taskscheduler.ps1 install
.\scripts\daemon\install-scheduler-taskscheduler.ps1 start
```

### 특징
- PC 부팅 시 + 로그온 시 자동 시작 (둘 다 trigger)
- 1분 간격 999회 재시작 시도 (사실상 무한 재시도)
- 로그: `runtime/logs/scheduler.stdout.log`

---

## Linux — systemd

### 설치
```bash
# 1. 프로젝트 위치: /opt/stocks_new (또는 본인 경로로 .service 수정)
sudo cp scripts/daemon/stocks-scheduler.service /etc/systemd/system/

# 2. User/WorkingDirectory 본인 환경에 맞게 수정
sudo nano /etc/systemd/system/stocks-scheduler.service

# 3. 활성화 + 시작
sudo systemctl daemon-reload
sudo systemctl enable stocks-scheduler
sudo systemctl start stocks-scheduler
```

### 운영 명령
```bash
sudo systemctl status stocks-scheduler
sudo systemctl restart stocks-scheduler
sudo systemctl stop stocks-scheduler

# 로그
sudo journalctl -u stocks-scheduler -f
tail -f /opt/stocks_new/runtime/logs/scheduler.stdout.log
```

---

## 배포 후 첫 실행 체크리스트

1. **서비스가 돌고 있나?**
2. **로그에 `scheduler started` 나오나?**
3. **UI `/control` 페이지에서 상태 확인** — trading_mode / paper_mode / kill_switch
4. **Kill Switch OFF → ON 전환하면서 첫 시점 관찰**
   - Paper=1 + Kill=1 → 감사 로그만 (안전)
   - Paper=0 + Kill=1 + mode=mock → 모의계좌 실주문 (안전, 진짜 돈 X)
   - Paper=0 + Kill=1 + mode=real → 실전계좌 실주문 ⚠️

---

## 비상 정지 (Emergency Stop)

```bash
# 1. Kill switch 파일 OFF (가장 빠름)
echo 0 > .bkit/state/auto_trade_enabled

# 2. 발주된 주문 취소는 Kiwoom 앱에서 수동

# 3. 서비스 중단 (필요 시)
.\scripts\daemon\install-scheduler-nssm.ps1 stop
# 또는 systemctl stop stocks-scheduler
```

---

## 트러블슈팅

| 증상 | 원인 | 조치 |
|------|------|------|
| 서비스 시작 즉시 멈춤 | python 경로 오류 | `nssm get StocksScheduler AppEnvironmentExtra` 확인 |
| fire 안 나감 | disabled_jobs 전부 | UI에서 job toggle ON |
| 15:30 됐는데 아무 일 없음 | kill_switch=0 | `echo 1 > .bkit/state/auto_trade_enabled` |
| "401 unauthorized" | mock 키 없는데 mock 모드 | trading_mode=real 또는 mock 키 발급 |
| 주문 다 PAPER | paper_mode=1 | `echo 0 > .bkit/state/paper_mode` |
