param(
    [string[]]$Models = @("qwen2.5:14b", "llama3.1:8b", "nomic-embed-text")
)

foreach ($model in $Models) {
    Write-Host "Pulling Ollama model: $model"
    ollama pull $model
}
