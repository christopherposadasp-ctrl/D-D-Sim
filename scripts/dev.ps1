param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("check-fast", "audit-quick", "audit-full", "audit-health", "fighter-audit-quick", "fighter-audit-full", "nightly-audit")]
    [string]$Task,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$TaskArgs
)

$repoRoot = Split-Path -Parent $PSScriptRoot

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
    switch ($Task) {
        "check-fast" {
            Invoke-Step @("py", "-3.13", "-m", "ruff", "check", "backend", "tests", "scripts")
            Invoke-Step @("py", "-3.13", "-m", "pytest", "-q", "tests\\golden", "tests\\rules", "tests\\integration")
        }
        "audit-quick" {
            Invoke-Step (@("py", "-3.13", ".\scripts\run_scenario_audit.py") + $TaskArgs)
        }
        "audit-full" {
            Invoke-Step (@("py", "-3.13", ".\scripts\run_scenario_audit.py", "--full") + $TaskArgs)
        }
        "audit-health" {
            Invoke-Step (@("py", "-3.13", ".\scripts\run_code_health_audit.py", "--write-report") + $TaskArgs)
        }
        "fighter-audit-quick" {
            Invoke-Step (@("py", "-3.13", ".\scripts\run_fighter_audit.py") + $TaskArgs)
        }
        "fighter-audit-full" {
            Invoke-Step (@("py", "-3.13", ".\scripts\run_fighter_audit.py", "--full") + $TaskArgs)
        }
        "nightly-audit" {
            Invoke-Step (@("py", "-3.13", ".\scripts\run_nightly_audit.py") + $TaskArgs)
        }
    }
}
finally {
    Pop-Location
}
