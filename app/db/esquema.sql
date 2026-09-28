-- FitPlan · esquema v1. Todas las tablas de datos llevan perfil_id (aislamiento multiperfil).
CREATE TABLE perfil (
  id            INTEGER PRIMARY KEY,
  alias         TEXT NOT NULL UNIQUE,
  sexo          TEXT CHECK (sexo IN ('H','M')),
  fecha_nacimiento TEXT,
  altura_cm     REAL,
  zona_horaria  TEXT NOT NULL DEFAULT 'Europe/Madrid',
  creado        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE importacion (
  id         INTEGER PRIMARY KEY,
  perfil_id  INTEGER NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
  fuente     TEXT NOT NULL,            -- hevy_csv | garmin_fit | fitdays | perfil_medico
  fichero    TEXT,
  sha256     TEXT NOT NULL,
  nuevos     INTEGER NOT NULL,
  duplicados INTEGER NOT NULL,
  fecha      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX ix_importacion_sha ON importacion(perfil_id, sha256);

CREATE TABLE perfil_medico (
  id           INTEGER PRIMARY KEY,
  perfil_id    INTEGER NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
  yaml_cifrado BLOB NOT NULL,          -- solo el bloque YAML, cifrado (Fernet)
  sha256_md    TEXT NOT NULL,
  generado     TEXT,
  importado    TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (perfil_id, sha256_md)
);

CREATE TABLE actividad (
  id             INTEGER PRIMARY KEY,
  perfil_id      INTEGER NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
  clave          TEXT NOT NULL,
  garmin_id      TEXT,
  tipo           TEXT NOT NULL,
  sport          TEXT,
  sub_sport      TEXT,
  inicio_utc     TEXT NOT NULL,
  duracion_s     REAL NOT NULL,
  distancia_km   REAL,
  kcal           INTEGER,
  fc_media       INTEGER,
  fc_max         INTEGER,
  ascenso_m      INTEGER,
  cadencia_media INTEGER,
  te_aerobico    REAL,
  te_anaerobico  REAL,
  carga_garmin   REAL,
  fc_max_config  INTEGER,
  zonas_json     TEXT,
  fc_json        TEXT,                 -- [[segundos, ppm], ...]
  con_gps        INTEGER NOT NULL DEFAULT 0,
  avisos_json    TEXT,
  UNIQUE (perfil_id, clave)
);
CREATE INDEX ix_actividad_inicio ON actividad(perfil_id, inicio_utc);

CREATE TABLE actividad_serie (
  id               INTEGER PRIMARY KEY,
  actividad_id     INTEGER NOT NULL REFERENCES actividad(id) ON DELETE CASCADE,
  orden            INTEGER NOT NULL,
  inicio_utc       TEXT,
  duracion_s       REAL,
  reps             INTEGER,
  peso_kg          REAL,
  descanso_s       REAL,
  categoria_garmin INTEGER
);

CREATE TABLE hevy_entreno (
  id         INTEGER PRIMARY KEY,
  perfil_id  INTEGER NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
  inicio_utc TEXT NOT NULL,
  fin_utc    TEXT NOT NULL,
  titulo     TEXT,
  UNIQUE (perfil_id, inicio_utc)
);

CREATE TABLE hevy_serie (
  id              INTEGER PRIMARY KEY,
  perfil_id       INTEGER NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
  entreno_id      INTEGER NOT NULL REFERENCES hevy_entreno(id) ON DELETE CASCADE,
  clave           TEXT NOT NULL,
  ejercicio       TEXT NOT NULL,
  ejercicio_orden INTEGER NOT NULL,
  set_index       INTEGER NOT NULL,
  tipo            TEXT,
  peso_kg         REAL,
  reps            INTEGER,
  distancia_km    REAL,
  duracion_s      REAL,
  rpe             REAL,
  superset_id     INTEGER,
  notas           TEXT,
  UNIQUE (perfil_id, clave)
);
CREATE INDEX ix_hevy_serie_ej ON hevy_serie(perfil_id, ejercicio);

CREATE TABLE composicion (
  id          INTEGER PRIMARY KEY,
  perfil_id   INTEGER NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
  fecha_hora  TEXT NOT NULL,           -- hora local de la báscula
  peso_kg     REAL NOT NULL,
  grasa_pct   REAL,
  musculo_esqueletico_kg REAL,
  masa_magra_kg REAL,
  tmb_kcal    REAL,
  datos_json  TEXT NOT NULL,           -- medición completa (composicion_corporal/v1)
  UNIQUE (perfil_id, fecha_hora)
);
