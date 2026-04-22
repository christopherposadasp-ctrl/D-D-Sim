param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("check-fast", "audit-quick", "audit-full", "audit-health", "fighter-audit-quick", "fighter-audit-full", "nightly-audit")]
    [string]$Task,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$TaskArgs
)

$repoRoot = Split-Path -Parent $PSScriptRoot

function Resolve-PythonCommand {
    $python313Path = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"
    $python312Path = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    $launcherPath = Join-Path $env:LOCALAPPDATA "Programs\Python\Launcher\py.exe"

    $candidates = @(
        @{ Command = $python313Path; ExtraArgs = @() },
        @{ Command = $python312Path; ExtraArgs = @() },
        @{ Command = "py"; ExtraArgs = @("-3.13") },
        @{ Command = $launcherPath; ExtraArgs = @("-3.13") },
        @{ Command = "python"; ExtraArgs = @() },
        @{ Command = "python3"; ExtraArgs = @() }
    )

    foreach ($candidate in $candidates) {
        $command = $candidate.Command
        if ([string]::IsNullOrWhiteSpace($command)) {
            continue
        }

        try {
            $resolved = Get-Command $command -ErrorAction Stop
            return @{
                Command = $resolved.Source
                ExtraArgs = @($candidate.ExtraArgs)
            }
        }
        catch {
            if (Test-Path -LiteralPath $command) {
                return @{
                    Command = $command
                    ExtraArgs = @($candidate.ExtraArgs)
                }
            }
        }
    }

    throw "Unable to locate a usable Python command."
}

function Build-PythonCommandParts {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$PythonCommand,

        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    $commandParts = @()
    $commandParts += $PythonCommand.Command
    $commandParts += @($PythonCommand.ExtraArgs)
    $commandParts += $Args
    return ,$commandParts
}

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$CommandParts
    )

    $commandName = $CommandParts[0]
    $arguments = @()
    if ($CommandParts.Count -gt 1) {
        $arguments = $CommandParts[1..($CommandParts.Count - 1)]
    }

    Write-Host ">" ($CommandParts -join " ")
    & $commandName @arguments
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Push-Location $repoRoot
try {
    $pythonCommand = Resolve-PythonCommand

    switch ($Task) {
        "check-fast" {
            Invoke-Step -CommandParts (Build-PythonCommandParts $pythonCommand @("-m", "ruff", "check", "backend", "tests", "scripts"))
            Invoke-Step -CommandParts (Build-PythonCommandParts $pythonCommand @("-m", "pytest", "-q", "tests\\golden", "tests\\rules", "tests\\integration"))
        }
        "audit-quick" {
            Invoke-Step -CommandParts (Build-PythonCommandParts $pythonCommand (@(".\scripts\run_scenario_audit.py") + $TaskArgs))
        }
        "audit-full" {
            Invoke-Step -CommandParts (Build-PythonCommandParts $pythonCommand (@(".\scripts\run_scenario_audit.py", "--full") + $TaskArgs))
        }
        "audit-health" {
            Invoke-Step -CommandParts (Build-PythonCommandParts $pythonCommand (@(".\scripts\run_code_health_audit.py", "--write-report") + $TaskArgs))
        }
        "fighter-audit-quick" {
            Invoke-Step -CommandParts (Build-PythonCommandParts $pythonCommand (@(".\scripts\run_fighter_audit.py") + $TaskArgs))
        }
        "fighter-audit-full" {
            Invoke-Step -CommandParts (Build-PythonCommandParts $pythonCommand (@(".\scripts\run_fighter_audit.py", "--full") + $TaskArgs))
        }
        "nightly-audit" {
            Invoke-Step -CommandParts (Build-PythonCommandParts $pythonCommand (@(".\scripts\run_nightly_audit.py") + $TaskArgs))
        }
    }
}
finally {
    Pop-Location
}
