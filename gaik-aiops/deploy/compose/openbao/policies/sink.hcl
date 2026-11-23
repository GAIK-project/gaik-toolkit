# Collection sink: read its own database connection. Nothing else (the collector pseudonymises).
path "gaik/data/collection/sink" {
  capabilities = ["read"]
}
