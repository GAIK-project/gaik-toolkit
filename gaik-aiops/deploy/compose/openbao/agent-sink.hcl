# OpenBao Agent next to the collection sink: logs in with AppRole, keeps a token file fresh and renders
# the sink's database DSN to a file. The sink itself never holds AppRole credentials.
vault {
  address = "http://openbao:8200"
}

auto_auth {
  method "approle" {
    config = {
      role_id_file_path                   = "/approle/sink/role_id"
      secret_id_file_path                 = "/approle/sink/secret_id"
      remove_secret_id_file_after_reading = false
    }
  }
  sink "file" {
    config = {
      path = "/run/bao/token"
      mode = 0400
    }
  }
}

template_config {
  exit_on_retry_failure = true
}

template {
  destination = "/run/bao/collection_dsn"
  perms       = "0400"
  contents    = "{{ with secret \"gaik/data/collection/sink\" }}{{ .Data.data.dsn }}{{ end }}"
}
