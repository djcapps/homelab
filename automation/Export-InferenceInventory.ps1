<# Read-only inventory for a Windows coordinator and its existing SSH worker.
   Never starts a model, probes the single-client RPC port, or changes routing. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$WorkerSsh,
    [Parameter(Mandatory)][System.Net.IPAddress]$WorkerAddress,
    [Parameter(Mandatory)][string]$ModelPath
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ($WorkerSsh -notmatch '^[A-Za-z0-9_][A-Za-z0-9_.-]*@[A-Za-z0-9][A-Za-z0-9_.-]*$') {
    throw 'Use an existing user@host SSH destination without options or shell syntax.'
}
function Get-SingleGpu([string[]]$Lines, [string]$Role) {
    if ($Lines.Count -ne 1) { throw "$Role must report exactly one NVIDIA GPU for this collector." }
    $gpu = $Lines | ConvertFrom-Csv -Header Name,FreeMiB
    $free = 0
    if (-not [int]::TryParse($gpu.FreeMiB.Trim(), [ref]$free) -or $free -lt 0) {
        throw "$Role did not report a numeric free-memory value."
    }
    return @{role=$Role; name=$gpu.Name.Trim(); free_mib=$free}
}
$localLines = @(& nvidia-smi --query-gpu=name,memory.free --format=csv,noheader,nounits)
if ($LASTEXITCODE -ne 0) { throw 'Local nvidia-smi failed.' }
$remoteLines = @(& ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 `
    $WorkerSsh 'nvidia-smi --query-gpu=name,memory.free --format=csv,noheader,nounits')
if ($LASTEXITCODE -ne 0) { throw 'Worker SSH or nvidia-smi failed; no partial inventory was produced.' }
$route = @(Find-NetRoute -RemoteIPAddress $WorkerAddress.IPAddressToString)
$source = @($route | Where-Object { $_.PSObject.Properties['IPAddress'] })
if ($source.Count -ne 1) { throw 'Could not select one route source address.' }
$model = Get-Item -LiteralPath $ModelPath
if ($model.PSIsContainer) { throw 'ModelPath must name a file.' }
@{
    collected_at = [DateTimeOffset]::UtcNow.ToString('o')
    coordinator_addresses = @(Get-NetIPAddress -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress)
    route = @{
        destination = $WorkerAddress.IPAddressToString
        source = $source[0].IPAddress
        interface = $source[0].InterfaceAlias
    }
    model_bytes = $model.Length
    devices = @((Get-SingleGpu $localLines 'coordinator'), (Get-SingleGpu $remoteLines 'worker'))
} | ConvertTo-Json -Depth 5
