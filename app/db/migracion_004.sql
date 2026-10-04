-- v4: conectores (Hevy API, Garmin) y estado de sincronización
CREATE TABLE hevy_plantilla (
  perfil_id  INTEGER NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
  id         TEXT NOT NULL,
  titulo     TEXT NOT NULL,
  tipo       TEXT,
  musculo    TEXT,
  equipo     TEXT,
  PRIMARY KEY (perfil_id, id)
);
CREATE INDEX ix_hevy_plantilla_titulo ON hevy_plantilla(perfil_id, titulo);

CREATE TABLE hevy_rutina (
  perfil_id  INTEGER NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
  hueco      TEXT NOT NULL,              -- RT1, RT2… (se reutiliza semana a semana)
  routine_id TEXT NOT NULL,
  PRIMARY KEY (perfil_id, hueco)
);

CREATE TABLE sincronizacion (
  perfil_id  INTEGER NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
  fuente     TEXT NOT NULL,              -- hevy_api | garmin
  ultima     TEXT NOT NULL,              -- ISO UTC
  resultado  TEXT,
  PRIMARY KEY (perfil_id, fuente)
);
