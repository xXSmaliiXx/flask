from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)

DB_PATH = "workers.db"

# ---------------- DB ----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            rank TEXT NOT NULL DEFAULT 'Стандартен',
            special_rate REAL DEFAULT 50
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time   TEXT NOT NULL,
            standard_hours REAL NOT NULL DEFAULT 0,
            overtime       REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(worker_id) REFERENCES workers(id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ------------- helpers -------------
def compute_hours(start_time: str, end_time: str, rank="Стандартен"):
    fmt = "%H:%M"
    sh = datetime.strptime(start_time, fmt)
    eh = datetime.strptime(end_time, fmt)

    start = sh
    end = eh
    if end <= start:
        end = end + timedelta(days=1)

    worked = (end - start).total_seconds() / 3600.0

    # break hours
    break_hours = 0.0
    if rank == "Стандартен":
        if worked >= 6:
            break_hours = 1.0
    else:  # Специален
        if worked >= 6:
            break_hours = 1.0

    paid = max(worked - break_hours, 0.0)

    if rank == "Стандартен":
        standard_cap = 8.0
        standard = min(paid, standard_cap)
        overtime = max(paid - standard, 0.0)
    else:  # Специален
        standard = paid
        overtime = 0.0

    standard = round(round(standard * 60) / 60, 2)
    overtime = round(round(overtime * 60) / 60, 2)
    return standard, overtime

def compute_salary(worker, standard_hours, overtime_hours):
    if worker['rank'] == 'Стандартен':
        return round(standard_hours * 10, 2), round(overtime_hours * 10.5, 2)
    else:
        # Специален: ставка за 8 часа
        rate = worker.get('special_rate', 50)
        salary = standard_hours / 8 * rate
        return round(salary, 2), 0.0

# ------------- routes -------------
@app.route("/")
def index():
    month_filter = request.args.get("month")  # Формат YYYY-MM
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, rank, special_rate FROM workers")
    rows = c.fetchall()

    workers = []
    for wid, name, rank, special_rate in rows:
        worker_info = {'id': wid, 'name': name, 'rank': rank, 'special_rate': special_rate}
        if month_filter:
            c.execute("""
                SELECT COALESCE(SUM(standard_hours),0), COALESCE(SUM(overtime),0), COUNT(DISTINCT date)
                FROM shifts
                WHERE worker_id=? AND strftime('%Y-%m', date)=?
            """, (wid, month_filter))
        else:
            c.execute("""
                SELECT COALESCE(SUM(standard_hours),0), COALESCE(SUM(overtime),0), COUNT(DISTINCT date)
                FROM shifts
                WHERE worker_id=?
            """, (wid,))
        std, ot, work_days = c.fetchone()
        salary_std, salary_ot = compute_salary(worker_info, std or 0, ot or 0)
        workers.append({
            **worker_info,
            "salary_data": {
                "standard_hours": round(std or 0, 2),
                "overtime_hours": round(ot or 0, 2),
                "work_days": work_days,
                "salary_standard": salary_std,
                "salary_overtime": salary_ot,
                "salary_total": round(salary_std + salary_ot, 2)
            }
        })
    conn.close()

    current_month = month_filter or datetime.now().strftime("%Y-%m")
    return render_template("index.html", workers=workers, current_month=current_month)

# ------------- worker CRUD -------------
@app.route("/add_worker", methods=["GET", "POST"])
def add_worker():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            return redirect(url_for("index"))
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO workers(name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
        return redirect(url_for("index"))
    return render_template("add_worker.html")

@app.route("/edit_worker/<int:worker_id>", methods=["GET", "POST"])
def edit_worker(worker_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM workers WHERE id=?", (worker_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return redirect(url_for("index"))
    worker = dict(row)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        rank = request.form.get("rank", "Стандартен")
        special_rate = request.form.get("special_rate", 50)
        special_rate = float(special_rate) if special_rate else 50
        c.execute("UPDATE workers SET name=?, rank=?, special_rate=? WHERE id=?", (name, rank, special_rate, worker_id))
        conn.commit()
        conn.close()
        return redirect(url_for("index"))
    conn.close()
    return render_template("edit_worker.html", worker=worker)

@app.route("/delete_worker", methods=["POST"])
def delete_worker():
    data = request.get_json(force=True)
    worker_id = int(data["worker_id"])
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM shifts WHERE worker_id=?", (worker_id,))
    c.execute("DELETE FROM workers WHERE id=?", (worker_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# ------------- shifts / calendar -------------
@app.route("/calendar/<int:worker_id>")
def calendar(worker_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, rank FROM workers WHERE id=?", (worker_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return redirect(url_for("index"))
    worker_name, rank = row
    return render_template("calendar.html", worker_id=worker_id, worker_name=worker_name, rank=rank)

@app.route("/get_shifts/<int:worker_id>")
def get_shifts(worker_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, date, start_time, end_time, standard_hours, overtime
        FROM shifts
        WHERE worker_id=?
    """, (worker_id,))
    rows = c.fetchall()
    conn.close()

    events = []
    for sid, date, st, et, std, ot in rows:
        events.append({
            "id": sid,
            "title": round(std or 0, 2),
            "start": f"{date}T{st}",
            "end":   f"{date}T{et}",
            "allDay": False,
            "extendedProps": {
                "overtime": round(ot or 0, 2),
                "start_time": st,
                "end_time": et
            }
        })
    return jsonify(events)

@app.route("/add_shift", methods=["POST"])
def add_shift():
    data = request.get_json(force=True)
    worker_id = int(data["worker_id"])
    date = data["date"]
    start_time = data["start_time"]
    end_time = data["end_time"]

    # Вземаме ранга на работника
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT rank FROM workers WHERE id=?", (worker_id,))
    row = c.fetchone()
    rank = row["rank"] if row else "Стандартен"
    conn.close()

    standard, overtime = compute_hours(start_time, end_time, rank=rank)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO shifts (worker_id, date, start_time, end_time, standard_hours, overtime)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (worker_id, date, start_time, end_time, standard, overtime))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/edit_shift", methods=["POST"])
def edit_shift():
    data = request.get_json(force=True)
    sid = int(data["shift_id"])
    date = data["date"]
    start_time = data["start_time"]
    end_time = data["end_time"]

    # Вземаме ранга на работника
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT w.rank FROM workers w JOIN shifts s ON w.id=s.worker_id WHERE s.id=?", (sid,))
    row = c.fetchone()
    rank = row["rank"] if row else "Стандартен"
    conn.close()

    standard, overtime = compute_hours(start_time, end_time, rank=rank)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE shifts
        SET date=?, start_time=?, end_time=?, standard_hours=?, overtime=?
        WHERE id=?
    """, (date, start_time, end_time, standard, overtime, sid))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/delete_shift", methods=["POST"])
def delete_shift():
    data = request.get_json(force=True)
    sid = int(data["shift_id"])
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM shifts WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(debug=True)
