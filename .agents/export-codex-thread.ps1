[CmdletBinding(DefaultParameterSetName = 'ByThreadId')]
param(
    [Parameter(Mandatory, ParameterSetName = 'ByThreadId')]
    [ValidatePattern('^[0-9a-z-]+$')]
    [string] $ThreadId,

    [Parameter(Mandatory, ParameterSetName = 'BySessionFile')]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string] $SessionFile,

    [ValidateRange(0, 100000)]
    [int] $Last = 0,

    [switch] $IncludeInjectedContext
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($PSCmdlet.ParameterSetName -eq 'ByThreadId') {
    $codexUserProfile = $env:USERPROFILE
    if (-not $codexUserProfile) {
        $codexUserProfile = [Environment]::GetFolderPath('UserProfile')
    }
    $sessionsRoot = Join-Path $codexUserProfile '.codex\sessions'
    if (-not (Test-Path -LiteralPath $sessionsRoot -PathType Container)) {
        throw "Codex sessions directory was not found: $sessionsRoot"
    }

    $matches = @(
        Get-ChildItem -LiteralPath $sessionsRoot -Recurse -File `
            -Filter "*$ThreadId*.jsonl"
    )
    if ($matches.Count -ne 1) {
        throw "Expected one rollout log for thread $ThreadId; found $($matches.Count)."
    }
    $SessionFile = $matches[0].FullName
}

$resolvedSessionFile = (Resolve-Path -LiteralPath $SessionFile).Path

function Get-MessageText {
    param([Parameter(Mandatory)] $Payload)

    $parts = foreach ($part in @($Payload.content)) {
        if ($null -ne $part.PSObject.Properties['text']) {
            [string] $part.text
        }
    }
    return ($parts -join "`n")
}

function Test-InjectedContext {
    param([Parameter(Mandatory)][string] $Text)

    $trimmed = $Text.TrimStart()
    return (
        $trimmed.StartsWith('<environment_context>') -or
        $trimmed.StartsWith('<recommended_plugins>') -or
        $trimmed.StartsWith('<codex_internal_context') -or
        $trimmed.StartsWith('# AGENTS.md instructions for ')
    )
}

$messages = @()
$lineNumber = 0
foreach ($line in (Get-Content -LiteralPath $resolvedSessionFile -Encoding utf8)) {
    $lineNumber++
    try {
        $row = $line | ConvertFrom-Json
    }
    catch {
        throw "Invalid JSONL at line $lineNumber in $resolvedSessionFile"
    }

    if ($row.type -ne 'response_item' -or $row.payload.type -ne 'message') {
        continue
    }
    if ($row.payload.role -notin @('user', 'assistant')) {
        continue
    }

    $messageText = Get-MessageText -Payload $row.payload
    if (-not $messageText) {
        continue
    }
    if (
        -not $IncludeInjectedContext -and
        $row.payload.role -eq 'user' -and
        (Test-InjectedContext -Text $messageText)
    ) {
        continue
    }

    $messages += [pscustomobject]@{
        Timestamp = [string] $row.timestamp
        Ordinal = [int] $row.ordinal
        Role = [string] $row.payload.role
        Text = $messageText
    }
}

if ($Last -gt 0 -and $messages.Count -gt $Last) {
    $messages = @($messages | Select-Object -Last $Last)
}

Write-Output '# Recovered Codex conversation'
Write-Output ''
Write-Output "Source: local rollout log $(Split-Path -Leaf $resolvedSessionFile)"
Write-Output ''
foreach ($message in $messages) {
    Write-Output "## $($message.Timestamp) -- $($message.Role)"
    Write-Output ''
    Write-Output $message.Text
    Write-Output ''
}
