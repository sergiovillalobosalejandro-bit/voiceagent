# Despliegue del backend SoundBot en Render (API)
# Uso (PowerShell, NO pegues la clave en el chat):
#   $env:RENDER_API_KEY = "rnd_..."
#   $env:GROQ_API_KEY = "gsk_..."
#   .\scripts\deploy-render.ps1

$ErrorActionPreference = "Stop"
$base = "https://api.render.com/v1"

if (-not $env:RENDER_API_KEY) {
    Write-Error "Define RENDER_API_KEY en tu terminal (Account Settings > API Keys en Render)."
}
if (-not $env:GROQ_API_KEY) {
    Write-Error "Define GROQ_API_KEY en tu terminal."
}

$headers = @{
    Authorization = "Bearer $($env:RENDER_API_KEY)"
    Accept        = "application/json"
    "Content-Type" = "application/json"
}

Write-Host "Obteniendo workspace (ownerId)..."
$owners = Invoke-RestMethod -Uri "$base/owners" -Headers $headers -Method Get
if (-not $owners -or $owners.Count -eq 0) {
    Write-Error "No se encontraron owners en tu cuenta Render."
}
$ownerId = $owners[0].owner.id
Write-Host "ownerId: $ownerId"

$repo = "https://github.com/sergiovillalobosalejandro-bit/voiceagent"
$serviceName = "soundbot-backend"

Write-Host "Comprobando si el servicio ya existe..."
$existing = Invoke-RestMethod -Uri "$base/services?limit=100" -Headers $headers -Method Get
$found = $existing | Where-Object { $_.service.name -eq $serviceName }
if ($found) {
    $serviceId = $found[0].service.id
    Write-Host "Servicio existente: $serviceId — disparando deploy..."
    $deploy = Invoke-RestMethod -Uri "$base/services/$serviceId/deploys" -Headers $headers -Method Post -Body "{}"
    Write-Host "Deploy encolado. Revisa el dashboard de Render."
    exit 0
}

$cors = $env:CORS_ORIGINS
if (-not $cors) {
    $cors = "http://localhost:5173,http://localhost:3000,https://frontend-ruddy-nine-54.vercel.app"
}

$body = @{
    type      = "web_service"
    name      = $serviceName
    ownerId   = $ownerId
    repo      = $repo
    branch    = "main"
    autoDeploy = "yes"
    envVars   = @(
        @{ key = "GROQ_API_KEY"; value = $env:GROQ_API_KEY }
        @{ key = "GROQ_TEXT_MODEL"; value = "llama-3.3-70b-versatile" }
        @{ key = "GROQ_VISION_MODEL"; value = "meta-llama/llama-4-scout-17b-16e-instruct" }
        @{ key = "MAX_MODEL_TOKENS"; value = "512" }
        @{ key = "CORS_ORIGINS"; value = $cors }
    )
    serviceDetails = @{
        runtime           = "docker"
        dockerfilePath    = "./Dockerfile"
        dockerContext     = "."
        plan              = "starter"
        healthCheckPath   = "/health"
        envSpecificDetails = @{
            dockerCommand = $null
        }
    }
} | ConvertTo-Json -Depth 6

Write-Host "Creando web service Docker en Render..."
$created = Invoke-RestMethod -Uri "$base/services" -Headers $headers -Method Post -Body $body
$serviceId = $created.service.id
$url = $created.service.serviceDetails.url
Write-Host "Servicio creado: $serviceId"
if ($url) { Write-Host "URL (cuando termine el build): $url" }
Write-Host "Configura en Vercel: VITE_API_URL = la URL de Render"
Write-Host "Prueba salud: <url>/health"
