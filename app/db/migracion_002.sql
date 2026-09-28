-- v2: ajustes del perfil (objetivo, nivel, FC reposo/máx, factor de actividad…)
ALTER TABLE perfil ADD COLUMN ajustes_json TEXT NOT NULL DEFAULT '{}';
