# Opens the optional local-to-GPU Whisper tunnel for this Windows session.
# The SSH key stays in the user's .ssh folder; no credentials are stored here.
$ssh = Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
$key = Join-Path $env:USERPROFILE '.ssh\safealley_stt'
$knownHosts = Join-Path $env:USERPROFILE '.ssh\known_hosts'
if (-not (Test-Path -LiteralPath $ssh) -or
    -not (Test-Path -LiteralPath $key) -or
    -not (Test-Path -LiteralPath $knownHosts)) {
    exit 1
}

$listener = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 11436 -State Listen -ErrorAction SilentlyContinue
if (-not $listener) {
    $arguments = @(
        '-N', '-T', '-p', '19922', '-i', $key,
        '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
        '-o', 'StrictHostKeyChecking=yes', '-o', "UserKnownHostsFile=$knownHosts",
        '-o', 'ExitOnForwardFailure=yes', '-o', 'ConnectTimeout=10',
        '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3',
        '-L', '127.0.0.1:11436:127.0.0.1:18081', 'ltmetric@211.58.157.60'
    )
    $process = Start-Process -FilePath $ssh -ArgumentList $arguments -WindowStyle Hidden -PassThru
}
for ($attempt = 0; $attempt -lt 15; $attempt++) {
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:11436/health' -TimeoutSec 2 -ErrorAction Stop
        if ($health.ready -and $health.device -eq 'cuda') { return }
    } catch { }
    Start-Sleep -Seconds 1
}
throw 'GPU 음성 연결을 확인하지 못했습니다.'
