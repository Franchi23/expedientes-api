from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
import os

app = Flask(__name__)
CORS(app)

# ── Conexión ──────────────────────────────────────────────────
def get_conn():
    return mysql.connector.connect(
        host     = os.environ.get('DB_HOST',     'bnljmz5gsmhe9fn1f9c5-mysql.services.clever-cloud.com'),
        port     = int(os.environ.get('DB_PORT', '3306')),
        user     = os.environ.get('DB_USER',     'uqfoqapoib9kqyke'),
        password = os.environ.get('DB_PASS',     'M1Yvwsc3ooLNEJxO7i5y'),
        database = os.environ.get('DB_NAME',     'bnljmz5gsmhe9fn1f9c5'),
        charset  = 'utf8mb4'
    )

# ── Init tablas ───────────────────────────────────────────────
def init_db():
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS companeras (
            id        INT AUTO_INCREMENT PRIMARY KEY,
            nombre    VARCHAR(150) NOT NULL,
            activa    TINYINT(1)   NOT NULL DEFAULT 1,
            creado_en TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS expedientes (
            id               INT AUTO_INCREMENT PRIMARY KEY,
            numero           VARCHAR(50)  NOT NULL,
            nombre           VARCHAR(255) NOT NULL,
            idcompanera      INT          NOT NULL,
            responsable      INT          NOT NULL,
            fecha_asignacion DATE         NOT NULL,
            fecha_devolucion DATE         NULL,
            borrado          TINYINT(1)   NOT NULL DEFAULT 0,
            creado_en        TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
            actualizado_en   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            CONSTRAINT fk_comp FOREIGN KEY (idcompanera) REFERENCES companeras(id),
            CONSTRAINT fk_resp FOREIGN KEY (responsable)  REFERENCES companeras(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    # Insertar registro propio si no existe
    cur.execute("SELECT id FROM companeras WHERE id = 1")
    if not cur.fetchone():
        cur.execute("INSERT INTO companeras (id, nombre, activa) VALUES (1, 'Yo', 1)")
    conn.commit()
    cur.close()
    conn.close()

# ── Helpers ───────────────────────────────────────────────────
def rows_as_dicts(cursor):
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]

def row_as_dict(cursor):
    cols = [d[0] for d in cursor.description]
    row  = cursor.fetchone()
    return dict(zip(cols, row)) if row else None

def serial(obj):
    """Convierte fechas a string para JSON."""
    import datetime
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

import json, datetime
class DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(obj, datetime.date):
            return obj.strftime('%Y-%m-%d')
        return super().default(obj)

app.json_encoder = DateEncoder

# ── Servir el HTML en la raíz ────────────────────────────────
@app.route('/')
def index():
    import os
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'expedientes.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        return f.read()

# ── Ejecutar init al arrancar (funciona con gunicorn también) ─
with app.app_context():
    try:
        init_db()
    except Exception as e:
        print(f"Warning: init_db falló al arrancar: {e}")

# Ruta de emergencia para crear tablas manualmente
@app.route('/init')
def ruta_init():
    try:
        init_db()
        return jsonify({'ok': True, 'mensaje': 'Tablas creadas correctamente'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ════════════════════════════════════════════════════════════
#  EXPEDIENTES
# ════════════════════════════════════════════════════════════

@app.route('/expedientes', methods=['GET'])
def listar_expedientes():
    buscar      = request.args.get('buscar', '')
    responsable = request.args.get('responsable', '')
    conn = get_conn(); cur = conn.cursor()
    sql    = """SELECT e.*, c.nombre AS nombre_companera, r.nombre AS nombre_responsable
                FROM expedientes e
                JOIN companeras c ON c.id = e.idcompanera
                JOIN companeras r ON r.id = e.responsable
                WHERE 1=1"""
    params = []
    if buscar:
        sql += " AND (e.numero LIKE %s OR e.nombre LIKE %s OR c.nombre LIKE %s)"
        b = f'%{buscar}%'
        params += [b, b, b]
    if responsable:
        sql += " AND e.responsable = %s"
        params.append(int(responsable))
    sql += " ORDER BY e.id DESC"
    cur.execute(sql, params)
    data = rows_as_dicts(cur)
    cur.close(); conn.close()
    return jsonify(data)

@app.route('/expedientes/<int:eid>', methods=['GET'])
def obtener_expediente(eid):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""SELECT e.*, c.nombre AS nombre_companera, r.nombre AS nombre_responsable
                   FROM expedientes e
                   JOIN companeras c ON c.id = e.idcompanera
                   JOIN companeras r ON r.id = e.responsable
                   WHERE e.id = %s""", (eid,))
    row = row_as_dict(cur)
    cur.close(); conn.close()
    if row: return jsonify(row)
    return jsonify({'error': 'No encontrado'}), 404

@app.route('/expedientes', methods=['POST'])
def crear_expediente():
    d = request.json
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""INSERT INTO expedientes
                   (numero, nombre, idcompanera, responsable, fecha_asignacion, fecha_devolucion)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (d['numero'], d['nombre'], d['idcompanera'], d['responsable'],
                 d['fecha_asignacion'], d.get('fecha_devolucion') or None))
    conn.commit()
    eid = cur.lastrowid
    cur.close(); conn.close()
    return jsonify({'id': eid, 'mensaje': 'Expediente creado'}), 201

@app.route('/expedientes/<int:eid>', methods=['PUT'])
def editar_expediente(eid):
    d = request.json
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""UPDATE expedientes
                   SET numero=%s, nombre=%s, idcompanera=%s, responsable=%s,
                       fecha_asignacion=%s, fecha_devolucion=%s, borrado=%s
                   WHERE id=%s""",
                (d['numero'], d['nombre'], d['idcompanera'], d['responsable'],
                 d['fecha_asignacion'], d.get('fecha_devolucion') or None,
                 int(d.get('borrado', 0)), eid))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({'mensaje': 'Expediente actualizado'})

@app.route('/expedientes/<int:eid>', methods=['DELETE'])
def eliminar_expediente(eid):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM expedientes WHERE id = %s", (eid,))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({'mensaje': 'Eliminado'})

# ════════════════════════════════════════════════════════════
#  COMPAÑERAS
# ════════════════════════════════════════════════════════════

@app.route('/companeras', methods=['GET'])
def listar_companeras():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""SELECT c.*,
                   (SELECT COUNT(*) FROM expedientes e WHERE e.idcompanera = c.id) AS total_expedientes
                   FROM companeras c ORDER BY c.id ASC""")
    data = rows_as_dicts(cur)
    cur.close(); conn.close()
    return jsonify(data)

@app.route('/companeras', methods=['POST'])
def crear_companera():
    d = request.json
    nombre = (d.get('nombre') or '').strip()
    if not nombre:
        return jsonify({'error': 'El nombre es obligatorio'}), 400
    conn = get_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO companeras (nombre, activa) VALUES (%s, 1)", (nombre,))
    conn.commit()
    cid = cur.lastrowid
    cur.close(); conn.close()
    return jsonify({'id': cid, 'mensaje': 'Compañera creada'}), 201

@app.route('/companeras/<int:cid>', methods=['PUT'])
def editar_companera(cid):
    if cid == 1:
        return jsonify({'error': 'No podés editar tu propio registro'}), 403
    d = request.json
    nombre = (d.get('nombre') or '').strip()
    if not nombre:
        return jsonify({'error': 'El nombre es obligatorio'}), 400
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE companeras SET nombre=%s, activa=%s WHERE id=%s",
                (nombre, int(d.get('activa', 1)), cid))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({'mensaje': 'Compañera actualizada'})

@app.route('/companeras/<int:cid>', methods=['DELETE'])
def eliminar_companera(cid):
    if cid == 1:
        return jsonify({'error': 'No podés eliminar tu propio registro'}), 403
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM expedientes WHERE idcompanera=%s OR responsable=%s", (cid, cid))
    total = cur.fetchone()[0]
    if total > 0:
        cur.close(); conn.close()
        return jsonify({'error': f'No se puede eliminar: tiene {total} expediente/s asociado/s'}), 409
    cur.execute("DELETE FROM companeras WHERE id=%s", (cid,))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({'mensaje': 'Compañera eliminada'})

# ════════════════════════════════════════════════════════════
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
