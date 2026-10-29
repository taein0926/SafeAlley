param([switch]$TunnelOnly)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$taskPrivate = Join-Path $taskRoot 'deployment/.private/pc-ai'
$taskConfigPath = Join-Path $taskPrivate 'connection.json'
if (-not (Test-Path -LiteralPath $taskConfigPath)) { throw 'PC AI 비공개 연결 설정이 없습니다.' }
$taskConfig = Get-Content -LiteralPath $taskConfigPath -Raw | ConvertFrom-Json
$taskMutex = New-Object Threading.Mutex($false, 'Local\SafeAlleyPcAiTunnel')
if (-not $taskMutex.WaitOne(0)) { Write-Host 'PC AI 연결 관리자가 이미 실행 중입니다.'; exit 0 }
function Test-TaskDockerReady {
    $ErrorActionPreference = 'SilentlyContinue'
    docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}
try {
    Set-Location -LiteralPath $taskRoot
    if (-not $TunnelOnly) {
        if (-not (Test-TaskDockerReady)) {
            $taskDocker = @("$env:ProgramFiles\Docker\Docker\Docker Desktop.exe", "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe", "$env:LOCALAPPDATA\Programs\DockerDesktop\frontend\Docker Desktop.exe") | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
            if (-not $taskDocker) { throw 'Docker Desktop 설치 경로를 찾지 못했습니다.' }
            Start-Process -FilePath $taskDocker -WindowStyle Hidden
            for ($attempt = 0; $attempt -lt 60; $attempt++) {
                Start-Sleep -Seconds 5
                if (Test-TaskDockerReady) { break }
            }
            if (-not (Test-TaskDockerReady)) { throw 'Docker Desktop 준비 시간이 초과되었습니다.' }
        }
        try { Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3 | Out-Null }
        catch {
            Start-Process -FilePath (Get-Command ollama.exe).Source -ArgumentList 'serve' -WindowStyle Hidden
            Start-Sleep -Seconds 5
        }
        docker compose -f docker-compose.yml -f deployment/compose.pc-ai.yml up -d --wait --wait-timeout 180 database backend frontend pc-whisper pc-laya
        if ($LASTEXITCODE -ne 0) { throw '로컬 서비스 기동 실패' }
        docker compose -f docker-compose.yml -f deployment/compose.pc-ai.yml exec -T backend python -c "from app.services.local_llm_service import parse_route_intent; parse_route_intent('가로등이 많은 길로 안내해줘'); print('모델 준비 완료')"
        if ($LASTEXITCODE -ne 0) { throw 'Gemma 사전 로딩 실패' }
        $taskWarmBody = @{query='밤 10시에 최단거리로 가로등 CCTV 안전시설 많은 길, 계단과 건널목 피하고 육교 우선으로 안내해줘';version=0} | ConvertTo-Json
        Invoke-RestMethod -Uri 'http://127.0.0.1:18761/analyze' -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($taskWarmBody)) -TimeoutSec 120 | Out-Null
    }
    $taskLog = Join-Path $taskPrivate 'tunnel-manager.log'
    $taskArgs = @('-N','-T','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes',
        '-o','ExitOnForwardFailure=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=20','-o','ServerAliveCountMax=3',
        '-i',$taskConfig.key,'-p',[string]$taskConfig.port,
        '-R','127.0.0.1:21434:127.0.0.1:11434','-R','127.0.0.1:28081:127.0.0.1:18081',
        '-R','127.0.0.1:28761:127.0.0.1:18761',($taskConfig.user+'@'+$taskConfig.host))
    while ($true) {
        if ((Test-Path -LiteralPath $taskLog) -and (Get-Item -LiteralPath $taskLog).Length -gt 1MB) {
            Move-Item -LiteralPath $taskLog -Destination ($taskLog+'.previous') -Force
        }
        Add-Content -LiteralPath $taskLog -Encoding UTF8 -Value ((Get-Date -Format o)+' PC AI SSH 연결 시작')
        # Windows PowerShell은 native stderr를 terminating error로 승격할 수 있다.
        # 접속 실패도 재시도할 수 있도록 이 호출에 한해 계속 진행한다.
        $ErrorActionPreference = 'Continue'
        & ssh.exe @taskArgs 2>&1 | ForEach-Object { Add-Content -LiteralPath $taskLog -Encoding UTF8 -Value ([string]$_) }
        $ErrorActionPreference = 'Stop'
        Add-Content -LiteralPath $taskLog -Encoding UTF8 -Value ((Get-Date -Format o)+' 연결 종료. 5초 후 재연결합니다.')
        Start-Sleep -Seconds 5
    }
} finally { $taskMutex.ReleaseMutex(); $taskMutex.Dispose() }
