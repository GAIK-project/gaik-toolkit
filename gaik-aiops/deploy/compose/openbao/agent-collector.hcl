# OpenBao Agent next to the collector: logs in with AppRole and renders the pseudonymisation key to a
# file the collector reads at start. The collector itself never holds AppRole credentials.
vault {
  address = "http://openbao:8200"
}

auto_auth {
  method "approle" {
    config = {
      role_id_file_path                   = "/approle/collector/role_id"
      secret_id_file_path                 = "/approle/collector/secret_id"
      remove_secret_id_file_after_reading = false
    }
  }
}

template_config {
  exit_on_retry_failure = true
}

template {
  destination = "/run/bao/pseudonym_key"
  perms       = "0400"
  contents    = "{{ with secret \"gaik/data/collection/pseudonym\" }}{{ .Data.data.key }}{{ end }}"
}
