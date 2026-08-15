# Local preview server for the Risk & Incident Map — no Python/Node needed.
# Serves the project folder over HTTP and opens your browser.
# Stop it with Ctrl+C (or just close this window).
$Root = Split-Path -Parent $PSScriptRoot   # project root (parent of \scripts)
$Port = 8000
$mimes = @{ ".html"="text/html; charset=utf-8"; ".css"="text/css; charset=utf-8";
  ".js"="application/javascript; charset=utf-8"; ".json"="application/json; charset=utf-8";
  ".svg"="image/svg+xml"; ".png"="image/png"; ".ico"="image/x-icon" }

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Port/")
try { $listener.Start() } catch {
  Write-Host "Could not start on port $Port. Is it already in use?" -ForegroundColor Red; exit 1
}
Write-Host "Serving $Root" -ForegroundColor Green
Write-Host "Open  http://localhost:$Port/   (Ctrl+C to stop)" -ForegroundColor Cyan
Start-Process "http://localhost:$Port/"

while ($listener.IsListening) {
  try {
    $ctx = $listener.GetContext()
    $rel = [System.Uri]::UnescapeDataString($ctx.Request.Url.AbsolutePath.TrimStart('/'))
    if ([string]::IsNullOrEmpty($rel)) { $rel = "index.html" }
    $path = Join-Path $Root $rel
    if (Test-Path $path -PathType Leaf) {
      $bytes = [System.IO.File]::ReadAllBytes($path)
      $ext = [System.IO.Path]::GetExtension($path).ToLower()
      if ($mimes.ContainsKey($ext)) { $ctx.Response.ContentType = $mimes[$ext] }
      $ctx.Response.Headers.Add("Cache-Control","no-store")
      $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    } else {
      $ctx.Response.StatusCode = 404
    }
    $ctx.Response.OutputStream.Close()
  } catch { }
}
