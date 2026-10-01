param(
    [Parameter(Mandatory = $true, Position = 0)][string]$AudioPath,
    [ValidateRange(0.0, 1.0)][double]$Volume = 0.75,
    [switch]$Mute,
    [switch]$Trace,
    # .NET sleeps in Windows PowerShell land on a ~15.6 ms tick: asking for 17 ms costs
    # two ticks (32 Hz), asking for 11 ms costs one (64 Hz measured). 90 nominal is the
    # one-tick rate, which beats the 60 Hz the macOS helper emitted.
    [ValidateRange(10.0, 250.0)][double]$Hz = 90.0
)
# Audio clock for the terminal MV, replacing the macOS AVAudioPlayer helper.
# Same line protocol: stdin takes "play|pause|seek <t>|volume <0..1>|quit",
# stdout emits {"time","duration","playing"} lines. Diagnostics go to stderr only,
# and stay ASCII so the parent can read them whatever the console codepage is.
$ErrorActionPreference = 'Stop'
$inv = [System.Globalization.CultureInfo]::InvariantCulture
$OPEN_TIMEOUT_S = 6.0

function Emit([string]$line) {
    [Console]::Out.WriteLine($line)
    [Console]::Out.Flush()
}
function Num([double]$value) {
    [string]::Format($inv, '{0:F6}', $value)
}
function Trace([string]$step) {
    if ($Trace) { [Console]::Error.WriteLine('trace: ' + $step) }
}
function Ascii([string]$text) {
    # Keep both channels ASCII: the parent decodes them as UTF-8 no matter what codepage
    # Windows PowerShell wrote them with.
    $folded = ('' + $text) -replace '[^\x20-\x7E]', '?'
    if ($folded.Length -gt 160) { return $folded.Substring(0, 160) }
    return $folded
}
function Fail([string]$reason, [string]$detail, [int]$code) {
    Emit ('{{"error":"{0}"}}' -f $reason)
    [Console]::Error.WriteLine('audioclock: ' + $reason + ' [' + (Ascii $detail) + ']')
    exit $code
}

if ($Mute) { $Volume = 0.0 }
if (-not (Test-Path -LiteralPath $AudioPath)) {
    Fail 'audio file not found' 'Test-Path returned false' 2
}
try {
    $playerType = [Windows.Media.Playback.MediaPlayer,Windows.Media.Playback,ContentType=WindowsRuntime]
    $sourceType = [Windows.Media.Core.MediaSource,Windows.Media.Core,ContentType=WindowsRuntime]
} catch {
    Fail 'WinRT projection unavailable' 'Windows.Media.Playback not resolvable' 3
}
try {
    $player = [Activator]::CreateInstance($playerType)
} catch {
    Fail 'WinRT projection unavailable' 'MediaPlayer could not be created' 3
}
$session = $player.PlaybackSession
$player.Volume = $Volume
$startedAt = Get-Date
Trace ('player created, state=' + $session.PlaybackState)

try {
    # Setting Source plus an immediate Pause preloads and reports duration without
    # letting a few milliseconds of audio escape before the player seeks to --start.
    $player.Source = $sourceType::CreateFromUri([System.Uri]$AudioPath)
    Trace 'source set'
    $player.Play()
    $player.Pause()
    Trace ('play/pause issued, state=' + $session.PlaybackState)
} catch {
    Fail 'open failed' $_.Exception.Message 4
}

$duration = 0.0
$polled = 0
while ($duration -le 0 -and ((Get-Date) - $startedAt).TotalSeconds -lt $OPEN_TIMEOUT_S) {
    $duration = $session.NaturalDuration.TotalSeconds
    $polled++
    if ($polled % 20 -eq 0) { Trace ('poll ' + $polled + ' state=' + $session.PlaybackState + ' d=' + $duration) }
    if ($duration -le 0) { Start-Sleep -Milliseconds 10 }
}
if ($duration -le 0) {
    Fail 'media did not report a duration' ('state=' + $session.PlaybackState) 5
}

function Apply-Line([string]$line) {
    $parts = $line -split '\s+'
    switch ($parts[0]) {
        'play' { $player.Play(); return 'play' }
        'pause' { $player.Pause(); return 'pause' }
        'volume' {
            if ($parts.Count -gt 1) {
                $v = 0.0
                if ([double]::TryParse($parts[1], [System.Globalization.NumberStyles]::Float, $inv, [ref]$v)) {
                    $player.Volume = [math]::Min(1.0, [math]::Max(0.0, $v))
                }
            }
            return 'volume'
        }
        'seek' {
            if ($parts.Count -gt 1) {
                $t = 0.0
                if ([double]::TryParse($parts[1], [System.Globalization.NumberStyles]::Float, $inv, [ref]$t)) {
                    $t = [math]::Min([math]::Max(0.0, $t), $duration - 0.01)
                    $session.Position = [TimeSpan]::FromSeconds($t)
                }
            }
            return 'seek'
        }
        'quit' { return 'quit' }
        default { return '' }
    }
}

# [Console]::In is a SyncTextReader: its ReadLineAsync runs the blocking read on the
# calling thread, which would park the clock before its first status line. A plain
# StreamReader over the raw handle gives a genuinely pending Task.
$reader = New-Object System.IO.StreamReader([Console]::OpenStandardInput())
$pending = $null

# Sleep() is quantised to the system timer tick (15.6 ms by default), which would cap
# this loop near 20 Hz and coarsen the parent's frame pacing too. Media players raise
# the resolution while they run and hand it back on the way out.
$fineClock = $false
try {
    if (-not ('Wem.Clock' -as [type])) {
        Add-Type -Namespace Wem -Name Clock -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("winmm.dll")]
public static extern uint timeBeginPeriod(uint milliseconds);
[System.Runtime.InteropServices.DllImport("winmm.dll")]
public static extern uint timeEndPeriod(uint milliseconds);
'@
    }
    [void][Wem.Clock]::timeBeginPeriod(1)
    $fineClock = $true
} catch {
    Trace ('timeBeginPeriod unavailable: ' + $_.Exception.Message)
}

$quit = $false
$interval = [int][math]::Max(4.0, [math]::Round(1000.0 / $Hz))
$template = '{{"time":{0},"duration":{1},"playing":{2},"backend":"winrt-mediafoundation","pid":{3}}}'
$wantPlaying = $false
$playSince = $null
Trace ('entering loop, interval=' + $interval + 'ms d=' + $duration)

try {
    $emitted = 0
    $loopStarted = Get-Date
    while (-not $quit) {
        # Take everything that landed since the last tick: a seek+play pair from the parent
        # should cost one frame, not two.
        while ($true) {
            if ($null -eq $pending) { $pending = $reader.ReadLineAsync() }
            if (-not $pending.IsCompleted) { break }
            $line = $pending.Result
            $pending = $null
            if ($null -eq $line) { $quit = $true; break }
            $verb = Apply-Line $line
            switch ($verb) {
                'quit' { $quit = $true }
                'play' { $wantPlaying = $true; $playSince = Get-Date }
                'pause' { $wantPlaying = $false; $playSince = $null }
                # A seek can send the engine through Buffering, so give the "did play ever
                # start" watchdog a fresh window rather than blaming the seek for it.
                'seek' { if ($wantPlaying) { $playSince = Get-Date } }
            }
            if ($quit) { break }
        }
        if ($quit) { break }
        $playing = ($session.PlaybackState.ToString() -eq 'Playing')
        $time = $session.Position.TotalSeconds
        if ([double]::IsNaN($time) -or [double]::IsInfinity($time)) {
            # A non-finite time would be invalid JSON; the parent would read it as a stall.
            Emit '{"error":"media engine reported a non-finite position"}'
            [Console]::Error.WriteLine('audioclock: non-finite position from the media engine')
            break
        }
        if ($wantPlaying -and (-not $playing) -and ($playSince -ne $null) `
            -and (((Get-Date) - $playSince).TotalSeconds -gt 1.5)) {
            # This is the channel the macOS helper had for a failed play(): without it a
            # dead output device looks like a frozen picture with playing:false.
            Emit '{"error":"playback did not start: no audio output available"}'
            [Console]::Error.WriteLine('audioclock: Play() never reached the Playing state')
            break
        }
        Emit ($template -f (Num $time), (Num $duration), $(if ($playing) { 'true' } else { 'false' }), $PID)
        $emitted++
        Start-Sleep -Milliseconds $interval
    }
    $elapsed = ((Get-Date) - $loopStarted).TotalSeconds
    if ($elapsed -gt 0) {
        Trace ('rate: ' + [string]::Format($inv, '{0:F1}', $emitted / $elapsed) + ' Hz, fineClock=' + $fineClock)
    }
} catch {
    # Anything the media engine throws mid-playback has to reach the parent as a message,
    # not as a silent process exit, which the parent can only report as "engine exited unexpectedly".
    Emit ('{{"error":"clock failed: {0}"}}' -f (Ascii (('' + $_.Exception.Message))))
    [Console]::Error.WriteLine('audioclock: ' + (Ascii (('' + $_.Exception.Message))))
    exit 6
} finally {
    # Each step guarded on its own: a throw in Pause() must not skip Dispose() or leak the
    # 1 ms timer-resolution request for the life of the process.
    try { $player.Pause() } catch { }
    try { $player.Dispose() } catch { }
    if ($fineClock) { try { [void][Wem.Clock]::timeEndPeriod(1) } catch { } }
}
exit 0
