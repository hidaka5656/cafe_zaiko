from datetime import date, datetime
from pathlib import Path
import sqlite3

from flask import Flask, flash, redirect, render_template, request, url_for

app = Flask(__name__)
app.config["SECRET_KEY"] = "cafe-zaiko-dev"

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "cafe_inventory.db"
EXPIRY_WARNING_DAYS = 3


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.template_filter("format_quantity")
def format_quantity(value):
    if value is None:
        return ""

    number = float(value)
    if number.is_integer():
        return str(int(number))
    return str(number)


def quantity_to_int(value):
    if value is None:
        return 0
    return int(float(value))


def table_exists(conn, table_name):
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def log_stock_change(conn, item_id, stock_lot_id, action_type, quantity, note):
    if not table_exists(conn, "stock_logs"):
        return

    conn.execute(
        """
        INSERT INTO stock_logs (
            item_id,
            stock_lot_id,
            action_type,
            quantity,
            action_at,
            updated_by,
            note
        )
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
        """,
        (item_id, stock_lot_id, action_type, quantity, "system", note),
    )


def fetch_items(conn):
    return conn.execute(
        """
        SELECT id, name, category, unit
        FROM items
        WHERE is_active = 1
        ORDER BY category, name
        """
    ).fetchall()


def fetch_stock_lots(conn):
    return conn.execute(
        """
        SELECT
            stock_lots.id,
            stock_lots.item_id,
            items.name AS item_name,
            items.category,
            items.unit,
            stock_lots.lot_code,
            stock_lots.quantity,
            stock_lots.remaining_quantity,
            stock_lots.received_date,
            stock_lots.expiry_date,
            stock_lots.supplier_name,
            stock_lots.note
        FROM stock_lots
        INNER JOIN items
            ON stock_lots.item_id = items.id
        ORDER BY
            items.id,
            stock_lots.expiry_date IS NULL,
            stock_lots.expiry_date,
            stock_lots.received_date,
            stock_lots.id
        """
    ).fetchall()


def fetch_stock_lot(conn, lot_id):
    return conn.execute(
        """
        SELECT *
        FROM stock_lots
        WHERE id = ?
        """,
        (lot_id,),
    ).fetchone()


def fetch_item_summary_rows(conn):
    return conn.execute(
        """
        SELECT
            items.id,
            items.name,
            items.category,
            items.unit,
            items.order_group,
            items.minimum_stock,
            COALESCE(
                SUM(
                    CASE
                        WHEN stock_lots.remaining_quantity > 0 THEN stock_lots.remaining_quantity
                        ELSE 0
                    END
                ),
                0
            ) AS total_remaining,
            MIN(
                CASE
                    WHEN stock_lots.remaining_quantity > 0
                     AND stock_lots.expiry_date IS NOT NULL
                    THEN stock_lots.expiry_date
                END
            ) AS nearest_expiry,
            MAX(
                CASE
                    WHEN stock_lots.remaining_quantity > 0
                    THEN stock_lots.received_date
                END
            ) AS latest_received_date,
            SUM(
                CASE
                    WHEN stock_lots.remaining_quantity > 0 THEN 1
                    ELSE 0
                END
            ) AS active_lot_count
        FROM items
        LEFT JOIN stock_lots
            ON stock_lots.item_id = items.id
        WHERE items.is_active = 1
        GROUP BY
            items.id,
            items.name,
            items.category,
            items.unit,
            items.order_group,
            items.minimum_stock
        ORDER BY items.category, items.name
        """
    ).fetchall()


def build_item_summary(row):
    total_remaining = quantity_to_int(row["total_remaining"])
    minimum_stock = quantity_to_int(row["minimum_stock"])
    nearest_expiry = row["nearest_expiry"]
    latest_received_date = row["latest_received_date"]
    active_lot_count = int(row["active_lot_count"] or 0)
    days_to_expiry = None

    if nearest_expiry:
        days_to_expiry = (date.fromisoformat(nearest_expiry) - date.today()).days

    alert_kind = None
    alert_label = ""
    badge_class = ""
    dot_class = "dot-green"
    status_text = "在庫は安定しています。"

    if days_to_expiry is not None and days_to_expiry < 0:
        alert_kind = "order"
        alert_label = "期限切れ"
        badge_class = "badge-expiry"
        dot_class = "dot-red"
        status_text = "消費期限を過ぎたロットがあります。"
    elif total_remaining <= minimum_stock:
        alert_kind = "order"
        alert_label = "発注"
        badge_class = "badge-expiry"
        dot_class = "dot-red"
        if total_remaining == 0:
            status_text = "在庫がありません。"
        else:
            status_text = f"最小在庫 {minimum_stock}{row['unit']} 以下です。"
    elif days_to_expiry is not None and days_to_expiry <= EXPIRY_WARNING_DAYS:
        alert_kind = "warning"
        alert_label = "期限"
        badge_class = "badge-low"
        dot_class = "dot-yellow"
        status_text = f"消費期限まで {days_to_expiry} 日です。"
    elif nearest_expiry:
        status_text = f"最短の消費期限は {nearest_expiry} です。"
    elif latest_received_date:
        status_text = f"最終入荷日は {latest_received_date} です。"

    return {
        "id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "unit": row["unit"],
        "order_group": row["order_group"],
        "minimum_stock": minimum_stock,
        "total_remaining": total_remaining,
        "nearest_expiry": nearest_expiry,
        "latest_received_date": latest_received_date,
        "active_lot_count": active_lot_count,
        "days_to_expiry": days_to_expiry,
        "alert_kind": alert_kind,
        "alert_label": alert_label,
        "badge_class": badge_class,
        "dot_class": dot_class,
        "status_text": status_text,
    }


def fetch_item_summaries(conn):
    return [build_item_summary(row) for row in fetch_item_summary_rows(conn)]


def fetch_item_summary_by_name(conn, item_name):
    for item in fetch_item_summaries(conn):
        if item["name"] == item_name:
            return item
    return None


def fetch_item_lots(conn, item_id):
    return conn.execute(
        """
        SELECT
            id,
            quantity,
            remaining_quantity,
            received_date,
            expiry_date,
            supplier_name,
            note
        FROM stock_lots
        WHERE item_id = ?
          AND remaining_quantity > 0
        ORDER BY
            expiry_date IS NULL,
            expiry_date,
            received_date,
            id
        """,
        (item_id,),
    ).fetchall()


def parse_iso_date(raw_value, field_label, required=True):
    value = (raw_value or "").strip()
    if not value:
        if required:
            return None, f"{field_label}を入力してください。"
        return None, None

    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None, f"{field_label}は YYYY-MM-DD 形式で入力してください。"

    return parsed.isoformat(), None


def parse_non_negative_integer(raw_value, field_label):
    value = (raw_value or "").strip()
    if not value:
        return None, f"{field_label}を入力してください。"

    try:
        parsed = int(value)
    except ValueError:
        return None, f"{field_label}は整数で入力してください。"

    if parsed < 0:
        return None, f"{field_label}は0以上で入力してください。"

    return parsed, None


def build_lot_form_defaults(row):
    return {
        "item_id": str(row["item_id"]),
        "lot_code": row["lot_code"] or "",
        "quantity": format_quantity(row["quantity"]),
        "remaining_quantity": format_quantity(row["remaining_quantity"]),
        "received_date": row["received_date"] or "",
        "expiry_date": row["expiry_date"] or "",
        "supplier_name": row["supplier_name"] or "",
        "note": row["note"] or "",
    }


def normalize_form_data(form):
    return {
        "item_id": form.get("item_id", "").strip(),
        "lot_code": form.get("lot_code", "").strip(),
        "quantity": form.get("quantity", "").strip(),
        "remaining_quantity": form.get("remaining_quantity", "").strip(),
        "received_date": form.get("received_date", "").strip(),
        "expiry_date": form.get("expiry_date", "").strip(),
        "supplier_name": form.get("supplier_name", "").strip(),
        "note": form.get("note", "").strip(),
    }


def validate_lot_form(conn, form):
    errors = []
    form_data = normalize_form_data(form)

    item_id = None
    if not form_data["item_id"]:
        errors.append("品目を選択してください。")
    else:
        try:
            item_id = int(form_data["item_id"])
        except ValueError:
            errors.append("品目の指定が不正です。")
        else:
            item_row = conn.execute(
                """
                SELECT id
                FROM items
                WHERE id = ? AND is_active = 1
                """,
                (item_id,),
            ).fetchone()
            if item_row is None:
                errors.append("選択した品目は登録できません。")

    if not form_data["lot_code"]:
        errors.append("ロットコードを入力してください。")

    quantity, quantity_error = parse_non_negative_integer(form_data["quantity"], "入荷数")
    if quantity_error:
        errors.append(quantity_error)

    remaining_quantity, remaining_error = parse_non_negative_integer(
        form_data["remaining_quantity"], "残数"
    )
    if remaining_error:
        errors.append(remaining_error)

    if quantity is not None and remaining_quantity is not None and remaining_quantity > quantity:
        errors.append("残数は入荷数以下で入力してください。")

    received_date, received_error = parse_iso_date(
        form_data["received_date"], "入荷日", required=True
    )
    if received_error:
        errors.append(received_error)

    expiry_date, expiry_error = parse_iso_date(
        form_data["expiry_date"], "消費期限", required=False
    )
    if expiry_error:
        errors.append(expiry_error)

    if received_date and expiry_date and expiry_date < received_date:
        errors.append("消費期限は入荷日以降の日付で入力してください。")

    cleaned_data = {
        "item_id": item_id,
        "lot_code": form_data["lot_code"],
        "quantity": quantity,
        "remaining_quantity": remaining_quantity,
        "received_date": received_date,
        "expiry_date": expiry_date,
        "supplier_name": form_data["supplier_name"] or None,
        "note": form_data["note"] or None,
    }

    return cleaned_data, form_data, errors


def render_inventory_page(
    conn,
    *,
    edit_lot=None,
    create_form=None,
    edit_form=None,
    create_errors=None,
    edit_errors=None,
):
    return render_template(
        "inventory.html",
        stock_lots=fetch_stock_lots(conn),
        items=fetch_items(conn),
        edit_lot=edit_lot,
        create_form=create_form or {},
        edit_form=edit_form or (build_lot_form_defaults(edit_lot) if edit_lot else {}),
        create_errors=create_errors or [],
        edit_errors=edit_errors or [],
    )


def render_detail_page(conn, item, *, target_quantity=None, errors=None):
    return render_template(
        "detail.html",
        item=item,
        lots=fetch_item_lots(conn, item["id"]),
        target_quantity=target_quantity if target_quantity is not None else item["total_remaining"],
        errors=errors or [],
    )


def adjust_item_up(conn, item, amount):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    lot_code = f"ADJ-{item['id']}-{timestamp}"

    cursor = conn.execute(
        """
        INSERT INTO stock_lots (
            item_id,
            lot_code,
            quantity,
            remaining_quantity,
            received_date,
            expiry_date,
            supplier_name,
            note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["id"],
            lot_code,
            amount,
            amount,
            date.today().isoformat(),
            None,
            "在庫調整",
            "詳細画面から在庫を増加",
        ),
    )
    log_stock_change(
        conn,
        item["id"],
        cursor.lastrowid,
        "increase",
        amount,
        "詳細画面から在庫を増加",
    )


def adjust_item_down_fefo(conn, item, amount):
    remaining = amount
    lots = fetch_item_lots(conn, item["id"])

    for lot in lots:
        if remaining <= 0:
            break

        available = quantity_to_int(lot["remaining_quantity"])
        used = min(available, remaining)
        new_remaining = available - used

        conn.execute(
            """
            UPDATE stock_lots
            SET
                remaining_quantity = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_remaining, lot["id"]),
        )
        log_stock_change(
            conn,
            item["id"],
            lot["id"],
            "decrease",
            used,
            "詳細画面から在庫を減少",
        )
        remaining -= used

    if remaining > 0:
        raise ValueError("現在庫を超えて減らすことはできません。")


@app.route("/")
def index():
    conn = get_connection()

    try:
        items = fetch_item_summaries(conn)
    finally:
        conn.close()

    summary = {
        "total": len(items),
        "order_count": sum(1 for item in items if item["alert_kind"] == "order"),
        "warning_count": sum(1 for item in items if item["alert_kind"] == "warning"),
    }

    return render_template(
        "index.html",
        items=items,
        summary=summary,
        today=date.today().isoformat(),
    )


@app.route("/detail/<item_name>")
def detail(item_name):
    conn = get_connection()

    try:
        item = fetch_item_summary_by_name(conn, item_name)
        if item is None:
            flash("指定した品目が見つかりません。", "warning")
            return redirect(url_for("index"))

        return render_detail_page(conn, item)
    finally:
        conn.close()


@app.post("/detail/<item_name>/adjust")
def adjust_item(item_name):
    conn = get_connection()

    try:
        item = fetch_item_summary_by_name(conn, item_name)
        if item is None:
            flash("指定した品目が見つかりません。", "warning")
            return redirect(url_for("index"))

        target_quantity, quantity_error = parse_non_negative_integer(
            request.form.get("target_quantity"), "更新後の在庫数"
        )
        if quantity_error:
            return render_detail_page(
                conn,
                item,
                target_quantity=item["total_remaining"],
                errors=[quantity_error],
            ), 400

        current_quantity = item["total_remaining"]
        delta = target_quantity - current_quantity

        if delta == 0:
            flash("数量変更はありません。", "warning")
            return redirect(url_for("detail", item_name=item_name))

        if delta > 0:
            adjust_item_up(conn, item, delta)
            flash(f"{item['name']} を {delta}{item['unit']} 増やしました。", "success")
        else:
            try:
                adjust_item_down_fefo(conn, item, -delta)
            except ValueError as error:
                return render_detail_page(
                    conn,
                    item,
                    target_quantity=current_quantity,
                    errors=[str(error)],
                ), 400
            flash(f"{item['name']} を {-delta}{item['unit']} 減らしました。", "success")

        conn.commit()
        return redirect(url_for("detail", item_name=item_name))
    finally:
        conn.close()


@app.route("/alerts")
def alerts():
    conn = get_connection()

    try:
        items = fetch_item_summaries(conn)
    finally:
        conn.close()

    order_items = [item for item in items if item["alert_kind"] == "order"]
    warning_items = [item for item in items if item["alert_kind"] == "warning"]

    return render_template(
        "alerts.html",
        order_items=order_items,
        warning_items=warning_items,
    )


@app.route("/inventory")
def inventory():
    edit_id = request.args.get("edit_id", type=int)
    conn = get_connection()

    try:
        edit_lot = None
        if edit_id is not None:
            edit_lot = fetch_stock_lot(conn, edit_id)
            if edit_lot is None:
                flash("指定した在庫ロットが見つかりません。", "warning")
                return redirect(url_for("inventory"))

        return render_inventory_page(conn, edit_lot=edit_lot)
    finally:
        conn.close()


@app.post("/inventory/create")
def create_inventory_lot():
    conn = get_connection()

    try:
        cleaned_data, form_data, errors = validate_lot_form(conn, request.form)
        if errors:
            return render_inventory_page(
                conn,
                create_form=form_data,
                create_errors=errors,
            ), 400

        cursor = conn.execute(
            """
            INSERT INTO stock_lots (
                item_id,
                lot_code,
                quantity,
                remaining_quantity,
                received_date,
                expiry_date,
                supplier_name,
                note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cleaned_data["item_id"],
                cleaned_data["lot_code"],
                cleaned_data["quantity"],
                cleaned_data["remaining_quantity"],
                cleaned_data["received_date"],
                cleaned_data["expiry_date"],
                cleaned_data["supplier_name"],
                cleaned_data["note"],
            ),
        )
        log_stock_change(
            conn,
            cleaned_data["item_id"],
            cursor.lastrowid,
            "create",
            cleaned_data["quantity"],
            "在庫一覧からロット登録",
        )
        conn.commit()
    finally:
        conn.close()

    flash("在庫ロットを登録しました。", "success")
    return redirect(url_for("inventory"))


@app.post("/inventory/<int:lot_id>/update")
def update_inventory_lot(lot_id):
    conn = get_connection()

    try:
        current_lot = fetch_stock_lot(conn, lot_id)
        if current_lot is None:
            flash("更新対象の在庫ロットが見つかりません。", "warning")
            return redirect(url_for("inventory"))

        cleaned_data, form_data, errors = validate_lot_form(conn, request.form)
        if errors:
            return render_inventory_page(
                conn,
                edit_lot=current_lot,
                edit_form=form_data,
                edit_errors=errors,
            ), 400

        conn.execute(
            """
            UPDATE stock_lots
            SET
                item_id = ?,
                lot_code = ?,
                quantity = ?,
                remaining_quantity = ?,
                received_date = ?,
                expiry_date = ?,
                supplier_name = ?,
                note = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                cleaned_data["item_id"],
                cleaned_data["lot_code"],
                cleaned_data["quantity"],
                cleaned_data["remaining_quantity"],
                cleaned_data["received_date"],
                cleaned_data["expiry_date"],
                cleaned_data["supplier_name"],
                cleaned_data["note"],
                lot_id,
            ),
        )
        log_stock_change(
            conn,
            cleaned_data["item_id"],
            lot_id,
            "update",
            cleaned_data["remaining_quantity"],
            "在庫一覧からロット更新",
        )
        conn.commit()
    finally:
        conn.close()

    flash("在庫ロットを更新しました。", "success")
    return redirect(url_for("inventory"))


@app.post("/inventory/<int:lot_id>/delete")
def delete_inventory_lot(lot_id):
    conn = get_connection()

    try:
        current_lot = fetch_stock_lot(conn, lot_id)
        if current_lot is None:
            flash("削除対象の在庫ロットが見つかりません。", "warning")
            return redirect(url_for("inventory"))

        conn.execute(
            """
            DELETE FROM stock_lots
            WHERE id = ?
            """,
            (lot_id,),
        )
        log_stock_change(
            conn,
            current_lot["item_id"],
            lot_id,
            "delete",
            quantity_to_int(current_lot["remaining_quantity"]),
            "在庫一覧からロット削除",
        )
        conn.commit()
    finally:
        conn.close()

    flash("在庫ロットを削除しました。", "success")
    return redirect(url_for("inventory"))


if __name__ == "__main__":
    app.run(debug=True)
