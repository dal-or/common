import Database from 'better-sqlite3';
import path from 'path';
import fs from 'fs';

const DB_DIR = path.join(process.cwd(), 'data');
const DB_PATH = path.join(DB_DIR, 'servicios.db');

let db: Database.Database | null = null;

export function getDb(): Database.Database {
  if (db) return db;

  fs.mkdirSync(DB_DIR, { recursive: true });

  db = new Database(DB_PATH);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');

  db.exec(`
    CREATE TABLE IF NOT EXISTS servicios (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      nombre TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS documentos (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      servicio_id INTEGER NOT NULL REFERENCES servicios(id),
      anio INTEGER NOT NULL,
      mes INTEGER NOT NULL,
      tipo TEXT NOT NULL CHECK(tipo IN ('factura', 'comprobante')),
      nombre_archivo TEXT NOT NULL,
      ruta_archivo TEXT NOT NULL,
      monto REAL,
      fecha_subida TEXT NOT NULL DEFAULT (datetime('now')),
      UNIQUE(servicio_id, anio, mes, tipo)
    );

    INSERT OR IGNORE INTO servicios (nombre) VALUES
      ('Electricidad'),
      ('Gas'),
      ('Agua'),
      ('Internet'),
      ('Administracion');
  `);

  return db;
}
