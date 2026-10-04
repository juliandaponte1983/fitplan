-- v3: paquetes exportados y planes importados
CREATE TABLE paquete (
  id            TEXT PRIMARY KEY,          -- UUID
  perfil_id     INTEGER NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
  semana_inicio TEXT NOT NULL,
  json          TEXT NOT NULL,
  creado        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX ix_paquete_semana ON paquete(perfil_id, semana_inicio);

CREATE TABLE plan (
  id            INTEGER PRIMARY KEY,
  perfil_id     INTEGER NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
  paquete_id    TEXT NOT NULL REFERENCES paquete(id),
  semana_inicio TEXT NOT NULL,
  estado        TEXT NOT NULL CHECK (estado IN ('aceptado','rechazado','sustituido')),
  json          TEXT NOT NULL,
  validacion_json TEXT NOT NULL,
  importado     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX ix_plan_semana ON plan(perfil_id, semana_inicio, estado);
