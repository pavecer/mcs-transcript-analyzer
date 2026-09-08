[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$InputPath,

    [Parameter(Mandatory = $true, Position = 1)]
    [string]$OutputPath,

    [string]$ConfigPath = (Join-Path $PSScriptRoot 'pii-masker.config.json'),

    [string]$AuditReportPath,

    [switch]$FailOnResidual,

    [switch]$Force
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Get-AbsolutePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [switch]$MustExist
    )

    if ($MustExist) {
        return (Resolve-Path -LiteralPath $Path).Path
    }

    $parent = Split-Path -Parent $Path
    if ([string]::IsNullOrWhiteSpace($parent)) {
        $parent = (Get-Location).Path
    }
    $resolvedParent = (Resolve-Path -LiteralPath $parent).Path
    return [IO.Path]::Combine($resolvedParent, (Split-Path -Leaf $Path))
}

function Get-NormalizedFieldName {
    param([string]$Name)

    return ($Name -replace '[^A-Za-z0-9]', '').ToLowerInvariant()
}

function Get-RuleForField {
    param(
        [string]$Name,
        [string]$Path
    )

    $normalized = Get-NormalizedFieldName -Name $Name
    $logicalName = $normalized
    if ($normalized.StartsWith('pvci')) {
        $logicalName = $normalized.Substring(4)
    }

    foreach ($rule in @($script:State.Config.sensitiveFields)) {
        foreach ($field in @($rule.fields)) {
            if ($normalized -eq $field -or ($rule.category -ne 'WORKDAY_DATA' -and $logicalName -eq $field)) {
                return [pscustomobject]@{ Mode = 'Sensitive'; Category = [string]$rule.category }
            }
        }
    }

    return [pscustomobject]@{ Mode = 'Normal'; Category = $null }
}

function Join-JsonPath {
    param(
        [string]$Parent,
        [string]$Child
    )

    if ($Parent -eq '$') {
        return '$.' + $Child
    }
    return $Parent + '.' + $Child
}

function Try-ParseEmbeddedJson {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $null
    }

    $trimmed = $Text.Trim()
    if (-not ($trimmed.StartsWith('{') -or $trimmed.StartsWith('['))) {
        return $null
    }

    try {
        $parsed = $trimmed | ConvertFrom-Json
        if ($trimmed.StartsWith('[')) {
            $parsed = @($parsed)
        }
        return [pscustomobject]@{ Value = $parsed }
    }
    catch [System.ArgumentException] {
        return $null
    }
    catch [System.Management.Automation.RuntimeException] {
        return $null
    }
}

# Country/language codes such as "CAN" or "IND" live inside Workday and HR subtrees; harvesting
# them would mask every occurrence of "canonical", "candidate", or "Bind" elsewhere in the transcript.
function Test-Harvestable {
    param(
        [string]$Value,
        [string]$Category
    )

    $trimmed = $Value.Trim()
    if ($trimmed.Length -ge $script:State.MinHarvestLength) {
        return $true
    }
    if ($trimmed.Length -lt 3) {
        return $false
    }
    if ($trimmed -match '\d') {
        return $true
    }
    return -not $script:State.CodeBearingCategories.Contains($Category)
}

function Add-HarvestedValue {
    param(
        [object]$Value,
        [string]$Category
    )

    if ($null -eq $Value -or $Value -isnot [string]) {
        return
    }

    $candidate = $Value.Trim()
    if (-not (Test-Harvestable -Value $candidate -Category $Category)) {
        return
    }

    $key = $candidate.ToLowerInvariant()
    $script:State.Harvested[$key] = [pscustomobject]@{
        Value = $candidate
        Category = $Category
    }
}

function Collect-SensitiveValues {
    param(
        [object]$Node,
        [string]$Path,
        [string]$ForcedCategory
    )

    if ($null -eq $Node) {
        return
    }

    if ($Node -is [string]) {
        $embeddedResult = Try-ParseEmbeddedJson -Text $Node
        if ($null -ne $embeddedResult) {
            Collect-SensitiveValues -Node $embeddedResult.Value -Path ($Path + '::<json>') -ForcedCategory $ForcedCategory
            return
        }

        if ($ForcedCategory) {
            Add-HarvestedValue -Value $Node -Category $ForcedCategory
        }
        return
    }

    if ($Node -is [System.Collections.IDictionary]) {
        foreach ($key in $Node.Keys) {
            $name = [string]$key
            $childPath = Join-JsonPath -Parent $Path -Child $name
            $fieldRule = Get-RuleForField -Name $name -Path $childPath
            $childCategory = $ForcedCategory
            if (-not $childCategory -and $fieldRule.Mode -eq 'Sensitive') {
                $childCategory = $fieldRule.Category
            }
            Collect-SensitiveValues -Node $Node[$key] -Path $childPath -ForcedCategory $childCategory
        }
        return
    }

    if ($Node -is [pscustomobject]) {
        foreach ($property in $Node.PSObject.Properties) {
            $childPath = Join-JsonPath -Parent $Path -Child $property.Name
            $fieldRule = Get-RuleForField -Name $property.Name -Path $childPath
            $childCategory = $ForcedCategory
            if (-not $childCategory -and $fieldRule.Mode -eq 'Sensitive') {
                $childCategory = $fieldRule.Category
            }
            Collect-SensitiveValues -Node $property.Value -Path $childPath -ForcedCategory $childCategory
        }
        return
    }

    if ($Node -is [System.Collections.IEnumerable]) {
        $index = 0
        foreach ($item in $Node) {
            Collect-SensitiveValues -Node $item -Path ($Path + '[' + $index + ']') -ForcedCategory $ForcedCategory
            $index++
        }
        return
    }

    if ($ForcedCategory) {
        Add-HarvestedValue -Value ([string]$Node) -Category $ForcedCategory
    }
}

function Get-MaskToken {
    param(
        [string]$Value,
        [string]$Category
    )

    return '[MASKED:' + $Category + ']'
}

function Add-ReplacementCount {
    param(
        [string]$Category,
        [int]$Count = 1
    )

    $script:State.Stats.ReplacementCount += $Count
    if (-not $script:State.Stats.CategoryCounts.ContainsKey($Category)) {
        $script:State.Stats.CategoryCounts[$Category] = 0
    }
    $script:State.Stats.CategoryCounts[$Category] += $Count
}

function Get-HarvestedValuePattern {
    param([string]$Value)

    $escaped = [Text.RegularExpressions.Regex]::Escape($Value)
    # Word-bounded so a harvested value never replaces a fragment inside an unrelated word or ID.
    return "(?<![A-Za-z0-9])$escaped(?![A-Za-z0-9])"
}

function Replace-HarvestedValues {
    param([string]$Text)

    $result = $Text
    foreach ($entry in $script:State.HarvestedEntries) {
        $pattern = Get-HarvestedValuePattern -Value $entry.Value

        $matches = [Text.RegularExpressions.Regex]::Matches(
            $result,
            $pattern,
            [Text.RegularExpressions.RegexOptions]::IgnoreCase
        )
        if ($matches.Count -gt 0) {
            $token = Get-MaskToken -Value $entry.Value -Category $entry.Category
            $result = [Text.RegularExpressions.Regex]::Replace(
                $result,
                $pattern,
                $token,
                [Text.RegularExpressions.RegexOptions]::IgnoreCase
            )
            Add-ReplacementCount -Category $entry.Category -Count $matches.Count
        }
    }
    return $result
}

function Replace-PatternRule {
    param(
        [string]$Text,
        [object]$Rule
    )

    $category = [string]$Rule.category
    $evaluator = [Text.RegularExpressions.MatchEvaluator]{
        param($match)
        Add-ReplacementCount -Category $category
        return Get-MaskToken -Value $match.Value -Category $category
    }

    return [Text.RegularExpressions.Regex]::Replace(
        $Text,
        [string]$Rule.pattern,
        $evaluator,
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
}

function Mask-String {
    param(
        [string]$Value,
        [string]$Path
    )

    $embeddedResult = Try-ParseEmbeddedJson -Text $Value
    if ($null -ne $embeddedResult) {
        $script:State.Stats.EmbeddedJsonCount++
        $maskedEmbedded = Mask-Node -Node $embeddedResult.Value -Path ($Path + '::<json>') -ForcedCategory $null
        return ConvertTo-Json -InputObject $maskedEmbedded -Depth 100 -Compress
    }

    $result = Replace-HarvestedValues -Text $Value
    foreach ($rule in @($script:State.Config.textPatterns)) {
        $result = Replace-PatternRule -Text $result -Rule $rule
    }
    return $result
}

function Test-StructuralField {
    param([string]$Name)

    return $script:State.StructuralFields.Contains((Get-NormalizedFieldName -Name $Name))
}

function Mask-Node {
    param(
        [object]$Node,
        [string]$Path,
        [string]$ForcedCategory,
        [switch]$Structural
    )

    if ($null -eq $Node) {
        return $null
    }

    if ($Node -is [string]) {
        $embeddedResult = Try-ParseEmbeddedJson -Text $Node
        if ($null -ne $embeddedResult) {
            $script:State.Stats.EmbeddedJsonCount++
            $maskedEmbedded = Mask-Node -Node $embeddedResult.Value -Path ($Path + '::<json>') -ForcedCategory $ForcedCategory
            return ConvertTo-Json -InputObject $maskedEmbedded -Depth 100 -Compress
        }

        if ($ForcedCategory) {
            Add-ReplacementCount -Category $ForcedCategory
            return Get-MaskToken -Value $Node -Category $ForcedCategory
        }
        # Structural identifiers, enum states and topic/tool names never carry transcript content.
        if ($Structural) {
            return $Node
        }
        return Mask-String -Value $Node -Path $Path
    }

    if ($Node -is [System.Collections.IDictionary]) {
        $maskedDictionary = [ordered]@{}
        foreach ($key in $Node.Keys) {
            $name = [string]$key
            $childPath = Join-JsonPath -Parent $Path -Child $name
            $fieldRule = Get-RuleForField -Name $name -Path $childPath
            $childCategory = $ForcedCategory
            if (-not $childCategory -and $fieldRule.Mode -eq 'Sensitive') {
                $childCategory = $fieldRule.Category
            }
            $maskedDictionary[$name] = Mask-Node -Node $Node[$key] -Path $childPath -ForcedCategory $childCategory -Structural:(Test-StructuralField -Name $name)
        }
        return [pscustomobject]$maskedDictionary
    }

    if ($Node -is [pscustomobject]) {
        $maskedObject = [ordered]@{}
        foreach ($property in $Node.PSObject.Properties) {
            $childPath = Join-JsonPath -Parent $Path -Child $property.Name
            $fieldRule = Get-RuleForField -Name $property.Name -Path $childPath
            $childCategory = $ForcedCategory
            if (-not $childCategory -and $fieldRule.Mode -eq 'Sensitive') {
                $childCategory = $fieldRule.Category
            }
            $maskedObject[$property.Name] = Mask-Node -Node $property.Value -Path $childPath -ForcedCategory $childCategory -Structural:(Test-StructuralField -Name $property.Name)
        }
        return [pscustomobject]$maskedObject
    }

    if ($Node -is [System.Collections.IEnumerable]) {
        $maskedItems = New-Object System.Collections.ArrayList
        $index = 0
        foreach ($item in $Node) {
            $maskedItem = Mask-Node -Node $item -Path ($Path + '[' + $index + ']') -ForcedCategory $ForcedCategory -Structural:$Structural
            [void]$maskedItems.Add($maskedItem)
            $index++
        }
        return ,($maskedItems.ToArray())
    }

    if ($ForcedCategory) {
        Add-ReplacementCount -Category $ForcedCategory
        return Get-MaskToken -Value ([string]$Node) -Category $ForcedCategory
    }

    return $Node
}

function Get-ResidualCount {
    param([string]$Json)

    $count = 0
    foreach ($rule in @($script:State.Config.textPatterns)) {
        $count += [Text.RegularExpressions.Regex]::Matches(
            $Json,
            [string]$rule.pattern,
            [Text.RegularExpressions.RegexOptions]::IgnoreCase
        ).Count
    }

    foreach ($entry in $script:State.HarvestedEntries) {
        $count += [Text.RegularExpressions.Regex]::Matches(
            $Json,
            (Get-HarvestedValuePattern -Value $entry.Value),
            [Text.RegularExpressions.RegexOptions]::IgnoreCase
        ).Count
    }

    return $count
}

$resolvedInput = Get-AbsolutePath -Path $InputPath -MustExist
$resolvedConfig = Get-AbsolutePath -Path $ConfigPath -MustExist
$resolvedOutput = Get-AbsolutePath -Path $OutputPath

if ($resolvedInput -eq $resolvedOutput) {
    throw 'InputPath and OutputPath must be different. The source transcript is never modified.'
}
if ((Test-Path -LiteralPath $resolvedOutput) -and -not $Force) {
    throw "Output already exists: $resolvedOutput. Use -Force to replace it."
}

$resolvedReport = $null
if (-not [string]::IsNullOrWhiteSpace($AuditReportPath)) {
    $resolvedReport = Get-AbsolutePath -Path $AuditReportPath
    if ($resolvedReport -eq $resolvedInput -or $resolvedReport -eq $resolvedOutput) {
        throw 'AuditReportPath must be different from InputPath and OutputPath.'
    }
    if ((Test-Path -LiteralPath $resolvedReport) -and -not $Force) {
        throw "Audit report already exists: $resolvedReport. Use -Force to replace it."
    }
}

$config = Get-Content -LiteralPath $resolvedConfig -Raw | ConvertFrom-Json
if ($config.schemaVersion -ne 2) {
    throw "Unsupported config schemaVersion '$($config.schemaVersion)'. Expected 2."
}

$script:State = @{
    Config = $config
    Harvested = @{}
    HarvestedEntries = @()
    MinHarvestLength = [int]$config.minHarvestLength
    CodeBearingCategories = [System.Collections.Generic.HashSet[string]]::new([string[]]@($config.codeBearingCategories))
    StructuralFields = [System.Collections.Generic.HashSet[string]]::new(
        [string[]](@($config.structuralFields) | ForEach-Object { Get-NormalizedFieldName -Name $_ })
    )
    Stats = @{
        ReplacementCount = 0
        EmbeddedJsonCount = 0
        CategoryCounts = @{}
    }
}

$sourceJson = [IO.File]::ReadAllText($resolvedInput)
try {
    $document = $sourceJson | ConvertFrom-Json
    if ($sourceJson.TrimStart().StartsWith('[')) {
        $document = @($document)
    }
}
catch {
    throw "Input is not valid JSON: $resolvedInput. $($_.Exception.Message)"
}

Collect-SensitiveValues -Node $document -Path '$' -ForcedCategory $null
$script:State.HarvestedEntries = @(
    $script:State.Harvested.Values |
        Sort-Object { $_.Value.Length } -Descending
)

$maskedDocument = Mask-Node -Node $document -Path '$' -ForcedCategory $null
$maskedJson = ConvertTo-Json -InputObject $maskedDocument -Depth 100
$residualCount = Get-ResidualCount -Json $maskedJson

if ($FailOnResidual -and $residualCount -gt 0) {
    throw "Residual audit found $residualCount potential sensitive value(s). No output was written."
}

$utf8NoBom = New-Object Text.UTF8Encoding($false)
$outputDirectory = Split-Path -Parent $resolvedOutput
$temporaryOutput = Join-Path $outputDirectory ([IO.Path]::GetRandomFileName())
try {
    [IO.File]::WriteAllText($temporaryOutput, $maskedJson + [Environment]::NewLine, $utf8NoBom)
    Move-Item -LiteralPath $temporaryOutput -Destination $resolvedOutput -Force:$Force
}
finally {
    if (Test-Path -LiteralPath $temporaryOutput) {
        Remove-Item -LiteralPath $temporaryOutput -Force
    }
}

$categorySummary = [ordered]@{}
foreach ($category in ($script:State.Stats.CategoryCounts.Keys | Sort-Object)) {
    $categorySummary[$category] = $script:State.Stats.CategoryCounts[$category]
}

$report = [ordered]@{
    schemaVersion = 1
    maskingPolicy = [string]$script:State.Config.policyVersion
    completedUtc = [DateTime]::UtcNow.ToString('o')
    inputFile = [IO.Path]::GetFileName($resolvedInput)
    outputFile = [IO.Path]::GetFileName($resolvedOutput)
    harvestedSensitiveValues = $script:State.Harvested.Count
    replacements = $script:State.Stats.ReplacementCount
    replacementsByCategory = $categorySummary
    embeddedJsonValuesProcessed = $script:State.Stats.EmbeddedJsonCount
    residualHighConfidenceMatches = $residualCount
    limitations = @(
        'Rule-based detection cannot guarantee removal of every name or context-specific identifier.',
        'Review the masked output before it leaves the customer security boundary.'
    )
}

if ($null -ne $resolvedReport) {
    [IO.File]::WriteAllText(
        $resolvedReport,
        (($report | ConvertTo-Json -Depth 10) + [Environment]::NewLine),
        $utf8NoBom
    )
}

$report | ConvertTo-Json -Depth 10
