<#
.SYNOPSIS
  Clean finished GitHub Actions runs older than 48 hours across musikfed repos.
.DESCRIPTION
  Deletes only finished runs (including their run logs/artifacts) and optionally
  caches unused for 14 days. Never deletes source code, workflow YAML, Git
  branches, commits or GitHub Releases.
  The default -Scope Self works with the workflow GITHUB_TOKEN. -Scope All
  needs a fine-grained token with Actions:write on all selected repositories.
.EXAMPLE
  ./Manage-GitHub-Actions.ps1 -Scope Self -Repository musikfed/muzikfed -DryRun
.EXAMPLE
  ./Manage-GitHub-Actions.ps1 -Scope All -CleanUnusedCaches
#>
[CmdletBinding()]
param(
  [ValidateSet('Self','All')][string]$Scope = 'Self',
  [ValidateRange(1,720)][int]$OlderThanHours = 48,
  [ValidateRange(1,365)][int]$UnusedCacheDays = 14,
  [ValidateRange(1,10000)][int]$MaxDeletes = 800,
  [ValidatePattern('^[A-Za-z0-9-]+$')][string]$Owner = 'musikfed',
  [string]$Repository = $env:GITHUB_REPOSITORY,
  [switch]$CleanUnusedCaches,
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  throw 'GitHub CLI (gh) is required: https://cli.github.com/'
}
function Get-ApiLines {
  param([string]$Endpoint, [string]$Query)
  $lines = @(& gh api --paginate $Endpoint --jq $Query 2>$null)
  if ($LASTEXITCODE -ne 0) {
    throw "GitHub API read failed: $Endpoint (exit $LASTEXITCODE)"
  }
  return $lines
}
function Remove-ApiItem {
  param([string]$Endpoint)
  $null = & gh api -X DELETE $Endpoint --silent 2>$null
  if ($LASTEXITCODE -ne 0) {
    throw "GitHub API deletion failed: $Endpoint (exit $LASTEXITCODE)"
  }
  Start-Sleep -Milliseconds 350
}
if ($Scope -eq 'Self') {
  if (-not $Repository -or $Repository -notmatch ('^' + [regex]::Escape($Owner) + '/[A-Za-z0-9_.-]+$')) {
    throw 'Self mode needs -Repository musikfed/NAME or GITHUB_REPOSITORY.'
  }
  $repos = @($Repository)
} else {
  $repos = @(Get-ApiLines -Endpoint 'user/repos?affiliation=owner&per_page=100' -Query '.[] | select(.archived == false) | .full_name' | Where-Object { $_ -like "$Owner/*" } | Sort-Object -Unique)
  if ($repos.Count -eq 0) {
    throw 'No repositories found. Check token permissions (Actions: write) and scope.'
  }
}
$cutoff = (Get-Date).ToUniversalTime().AddHours(-$OlderThanHours)
$cacheCutoff = (Get-Date).ToUniversalTime().AddDays(-$UnusedCacheDays)
$createdFilter = [Uri]::EscapeDataString('<' + $cutoff.ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Host "Housekeeping scope: $Scope; repositories: $($repos.Count); dry-run: $([bool]$DryRun)"
Write-Host "Finished runs last updated before UTC $($cutoff.ToString('u')) will be deleted."
if ($CleanUnusedCaches) { Write-Host "Caches last accessed before UTC $($cacheCutoff.ToString('u')) will be deleted." }
$foundRuns = 0
$deletedRuns = 0
$foundCaches = 0
$deletedCaches = 0
$errors = 0
$deletions = 0
foreach ($repo in $repos) {
  if (-not $DryRun -and $deletions -ge $MaxDeletes) {
    Write-Warning "Limit of $MaxDeletes deletions reached; remaining repositories are handled on a later run."
    break
  }
  Write-Host "---- $repo ----"
  try {
    # GitHub caps filtered run searches at 1,000 results. Subsequent jobs
    # continue removing the backlog after each sweep.
    $runsEndpoint = "repos/$repo/actions/runs?status=completed&created=$createdFilter&per_page=100"
    $rows = @(Get-ApiLines -Endpoint $runsEndpoint -Query '.workflow_runs[] | [.id, .updated_at] | @tsv')
    $oldRuns = @()
    foreach ($row in $rows) {
      $parts = $row -split '\t'
      if ($parts.Count -lt 2 -or $parts[0] -notmatch '^\d+$') { continue }
      try { $lastUpdated = [DateTimeOffset]::Parse($parts[1]).UtcDateTime }
      catch { continue }
      # A long job that finished recently must survive even if created days ago.
      if ($lastUpdated -lt $cutoff) { $oldRuns += $parts[0] }
    }
    $foundRuns += $oldRuns.Count
    Write-Host "Completed runs older than cutoff: $($oldRuns.Count)"
    foreach ($runId in $oldRuns) {
      if ($DryRun) { continue }
      if ($deletions -ge $MaxDeletes) { break }
      try {
        Remove-ApiItem -Endpoint "repos/$repo/actions/runs/$runId"
        $deletedRuns++
        $deletions++
      } catch {
        $errors++
        Write-Warning $_.Exception.Message
      }
    }
    if ($CleanUnusedCaches -and ($DryRun -or $deletions -lt $MaxDeletes)) {
      $cacheRows = @(Get-ApiLines -Endpoint "repos/$repo/actions/caches?per_page=100&sort=last_accessed_at&direction=asc" -Query '.actions_caches[] | [.id, .last_accessed_at] | @tsv')
      $oldCaches = @()
      foreach ($row in $cacheRows) {
        $parts = $row -split '\t'
        if ($parts.Count -lt 2 -or $parts[0] -notmatch '^\d+$') { continue }
        try { $lastAccessed = [DateTimeOffset]::Parse($parts[1]).UtcDateTime }
        catch { continue }
        if ($lastAccessed -lt $cacheCutoff) { $oldCaches += $parts[0] }
      }
      $foundCaches += $oldCaches.Count
      Write-Host "Unused caches older than cutoff: $($oldCaches.Count)"
      foreach ($cacheId in $oldCaches) {
        if ($DryRun) { continue }
        if ($deletions -ge $MaxDeletes) { break }
        try {
          Remove-ApiItem -Endpoint "repos/$repo/actions/caches/$cacheId"
          $deletedCaches++
          $deletions++
        } catch {
          $errors++
          Write-Warning $_.Exception.Message
        }
      }
    }
  } catch {
    $errors++
    Write-Warning "Skipping $repo : $($_.Exception.Message)"
  }
}
Write-Host "SUMMARY: runs found=$foundRuns, runs deleted=$deletedRuns; caches found=$foundCaches, caches deleted=$deletedCaches; errors=$errors"
if ($DryRun) { Write-Host 'PREVIEW ONLY. No items deleted.' }
if ($errors -gt 0) { exit 1 }
