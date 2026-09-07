[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw "Assertion failed: $Message"
    }
}

$toolRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$masker = Join-Path $toolRoot 'Mask-ConversationTranscript.ps1'
$config = Join-Path $toolRoot 'pii-masker.config.json'
$testDirectory = Join-Path ([IO.Path]::GetTempPath()) ('transcript-pii-masker-' + [Guid]::NewGuid().ToString('N'))

New-Item -ItemType Directory -Path $testDirectory | Out-Null
try {
    $inputPath = Join-Path $testDirectory 'input.json'
    $outputPath = Join-Path $testDirectory 'output.json'
    $reportPath = Join-Path $testDirectory 'report.json'
    $arrayInputPath = Join-Path $testDirectory 'array-input.json'
    $arrayOutputPath = Join-Path $testDirectory 'array-output.json'

    $fixture = @'
{
  "conversationId": "conversation-control-001",
  "diagnostics": [],
  "singleItemArray": [
    {
      "status": "Ready"
    }
  ],
  "activities": [
    {
      "type": "event",
      "name": "DynamicPlanStepTriggered",
      "timestamp": "2026-09-02T10:00:00Z",
      "value": {
        "stepId": "step-workday-worker",
        "taskDialogId": "Workday.GetWorker",
        "employeeId": "WD-12345",
        "pvci_userdisplayname": "Alex Example",
        "fullName": "Alex Example",
        "emailAddress": "alex.example@example.test",
        "nationalIdentifier": "AB123456C",
        "dateOfBirth": "1990-01-02"
      }
    },
    {
      "type": "message",
      "text": "Alex Example (alex.example@example.test) can be reached on +44 7700 900123.",
      "value": {
        "responseBody": "{\"workerId\":\"WD-12345\",\"preferredName\":\"Alex Example\",\"status\":\"Active\"}",
        "responseArray": "[{\"employeeId\":\"WD-12345\"}]",
        "workdayResponse": "{\"department\":\"Sensitive Department\",\"status\":\"Success\",\"records\":[{\"code\":\"ABC\"}]}",
        "finalized_emergency_contact_data": {
          "Company_Code": "PRIVATE-CO",
          "Headcount": 42,
          "Active": true
        }
      }
    }
  ]
}
'@

    [IO.File]::WriteAllText($inputPath, $fixture, (New-Object Text.UTF8Encoding($false)))

    & $masker `
        -InputPath $inputPath `
        -OutputPath $outputPath `
        -ConfigPath $config `
        -AuditReportPath $reportPath `
        -FailOnResidual

    $source = Get-Content -LiteralPath $inputPath -Raw
    $maskedText = Get-Content -LiteralPath $outputPath -Raw
    $masked = $maskedText | ConvertFrom-Json
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json

    Assert-True ($source -match 'Alex Example') 'the source fixture must remain unchanged'
    Assert-True ($maskedText -notmatch 'Alex Example') 'person name must be removed'
    Assert-True ($maskedText -notmatch 'alex\.example@example\.test') 'email must be removed'
    Assert-True ($maskedText -notmatch 'AB123456C') 'national identifier must be removed'
    Assert-True ($maskedText -notmatch 'WD-12345') 'employee identifier must be removed everywhere'
    Assert-True ($maskedText -notmatch '\+44 7700 900123') 'phone number must be removed'
    Assert-True ($maskedText -notmatch 'Sensitive Department') 'unknown values under a Workday response must be removed'
    Assert-True ($maskedText -notmatch 'PRIVATE-CO') 'normalized Workday subtree names must be recognized'
    Assert-True ($masked.conversationId -eq 'conversation-control-001') 'conversation correlation ID must be preserved'
    Assert-True ($masked.diagnostics.Count -eq 0) 'empty arrays must remain arrays'
    Assert-True ($masked.singleItemArray.Count -eq 1) 'single-item arrays must remain arrays'
    Assert-True ($masked.activities.Count -eq 2) 'activity array shape must be preserved'
    Assert-True ($masked.activities[0].name -eq 'DynamicPlanStepTriggered') 'event name must be preserved'
    Assert-True ($masked.activities[0].value.taskDialogId -eq 'Workday.GetWorker') 'tool ID must be preserved'
    Assert-True ($maskedText -match '"timestamp"\s*:\s*"2026-09-02T10:00:00Z"') 'timestamp text must be preserved'

    $structuredToken = $masked.activities[0].value.fullName
    Assert-True ($structuredToken -eq '[MASKED:PERSON]') 'structured person token must match the code app policy'
    Assert-True ($masked.activities[0].value.pvci_userdisplayname -eq '[MASKED:PERSON]') 'pvci-prefixed fields must use the logical field category'
    Assert-True ($masked.activities[1].text -match [Text.RegularExpressions.Regex]::Escape($structuredToken)) 'the same person token must be reused in free text'

    $embedded = $masked.activities[1].value.responseBody | ConvertFrom-Json
    Assert-True ($embedded.status -eq 'Active') 'preserved fields inside embedded JSON must remain readable'
    Assert-True ($embedded.workerId -eq '[MASKED:IDENTIFIER]') 'embedded JSON identifiers must be masked'

    $workday = $masked.activities[1].value.workdayResponse | ConvertFrom-Json
    Assert-True ($workday.status -eq '[MASKED:WORKDAY_DATA]') 'Workday status values must be masked'
    Assert-True ($workday.department -eq '[MASKED:WORKDAY_DATA]') 'unknown Workday values must be masked'
    Assert-True ($workday.records.Count -eq 1) 'arrays inside Workday JSON must retain their shape'
    Assert-True ($workday.records[0].code -eq '[MASKED:WORKDAY_DATA]') 'nested Workday values must be masked'
    Assert-True ($masked.activities[1].value.finalized_emergency_contact_data.Headcount -eq '[MASKED:WORKDAY_DATA]') 'numeric Workday values must be masked'
    Assert-True ($masked.activities[1].value.finalized_emergency_contact_data.Active -eq '[MASKED:WORKDAY_DATA]') 'boolean Workday values must be masked'
    Assert-True ($masked.activities[1].value.responseArray.TrimStart().StartsWith('[')) 'embedded JSON array syntax must be preserved'
    $embeddedArray = @($masked.activities[1].value.responseArray | ConvertFrom-Json)
    Assert-True ($embeddedArray.Count -eq 1) 'single-item arrays inside JSON strings must remain arrays'
    Assert-True ($embeddedArray[0].employeeId -eq '[MASKED:IDENTIFIER]') 'fields inside embedded arrays must be masked'
    Assert-True ($report.residualHighConfidenceMatches -eq 0) 'residual audit must pass'
    Assert-True ($report.replacements -ge 8) 'audit report must record replacements'
    Assert-True ($report.maskingPolicy -eq 'workday-hr-v1') 'audit report must identify the code app masking policy'

    [IO.File]::WriteAllText($arrayInputPath, '[{"employeeId":"WD-ARRAY"}]', (New-Object Text.UTF8Encoding($false)))
    & $masker -InputPath $arrayInputPath -OutputPath $arrayOutputPath -ConfigPath $config -FailOnResidual | Out-Null
    $maskedArrayText = Get-Content -LiteralPath $arrayOutputPath -Raw
    Assert-True ($maskedArrayText.TrimStart().StartsWith('[')) 'root JSON array syntax must be preserved'
    $maskedArray = @($maskedArrayText | ConvertFrom-Json)
    Assert-True ($maskedArray.Count -eq 1) 'single-item root arrays must remain arrays'
    Assert-True ($maskedArray[0].employeeId -eq '[MASKED:IDENTIFIER]') 'root-array fields must be masked'

    Write-Host 'PASS: transcript PII masker preserved orchestration and removed synthetic sensitive data.'
}
finally {
    if (Test-Path -LiteralPath $testDirectory) {
        Remove-Item -LiteralPath $testDirectory -Recurse -Force
    }
}
