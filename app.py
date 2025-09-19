import os
import re
from datetime import datetime
from functools import wraps
from io import BytesIO

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   send_file, session, url_for)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class DiningTable(db.Model):
    __tablename__ = "dining_table"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)


class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, default="")
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(80), nullable=True)
    available = db.Column(db.Boolean, default=True)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey("dining_table.id"), nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)
    total_amount = db.Column(db.Float, default=0.0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    requested_assistance = db.Column(db.Boolean, default=False, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    payment_method = db.Column(db.String(40), nullable=True)

    table = db.relationship("DiningTable", backref=db.backref("orders", lazy=True))
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")
    created_by = db.relationship("User")

    @property
    def is_active(self) -> bool:
        return self.status not in {"paid", "cancelled"}

    def recalculate_total(self) -> None:
        self.total_amount = sum(item.subtotal for item in self.items)
        self.updated_at = datetime.utcnow()


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_item.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)

    menu_item = db.relationship("MenuItem")

    @property
    def subtotal(self) -> float:
        return round(self.quantity * self.price, 2)


STATUS_FLOW = ["pending", "preparing", "served", "completed", "paid"]


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"[^\w-]", "", value)
    return value or "section"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(app.root_path, 'restaurant.db')}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    @app.before_request
    def load_logged_in_user() -> None:
        user_id = session.get("user_id")
        g.user = User.query.get(user_id) if user_id else None

    @app.context_processor
    def inject_globals():
        return {
            "current_user": g.get("user"),
            "STATUS_FLOW": STATUS_FLOW,
            "current_year": datetime.utcnow().year,
        }

    def login_required(roles=None):
        def decorator(view):
            @wraps(view)
            def wrapped_view(**kwargs):
                if g.user is None:
                    flash("กรุณาเข้าสู่ระบบก่อน", "warning")
                    return redirect(url_for("login"))
                if roles:
                    allowed = roles
                    if isinstance(roles, (str,)):
                        allowed = [roles]
                    if g.user.role not in allowed:
                        abort(403)
                return view(**kwargs)

            return wrapped_view

        return decorator

    def parse_order_items(form_data, menu_items):
        selected_items = []
        for item in menu_items:
            raw_qty = form_data.get(f"item_{item.id}")
            try:
                qty = int(raw_qty or 0)
            except ValueError:
                qty = 0
            if qty > 0:
                selected_items.append((item, qty))
        return selected_items

    @app.route("/")
    def index():
        if g.user:
            if g.user.role == "admin":
                return redirect(url_for("admin_dashboard"))
            if g.user.role == "staff":
                return redirect(url_for("staff_dashboard"))
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                session.clear()
                session["user_id"] = user.id
                flash("เข้าสู่ระบบสำเร็จ", "success")
                if user.role == "admin":
                    return redirect(url_for("admin_dashboard"))
                return redirect(url_for("staff_dashboard"))
            flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "danger")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("ออกจากระบบแล้ว", "info")
        return redirect(url_for("login"))

    # ------------------- Admin views -------------------
    @app.route("/admin/dashboard")
    @login_required(roles="admin")
    def admin_dashboard():
        total_sales = (
            db.session.query(db.func.coalesce(db.func.sum(Order.total_amount), 0))
            .filter(Order.status == "paid")
            .scalar()
        )
        today = datetime.utcnow().date()
        today_sales = (
            db.session.query(db.func.coalesce(db.func.sum(Order.total_amount), 0))
            .filter(
                Order.status == "paid",
                Order.paid_at.isnot(None),
                db.func.date(Order.paid_at) == today.isoformat(),
            )
            .scalar()
        )
        open_orders = (
            Order.query.filter(Order.status != "paid")
            .order_by(Order.created_at.desc())
            .limit(10)
            .all()
        )
        return render_template(
            "admin/dashboard.html",
            total_sales=total_sales,
            today_sales=today_sales,
            open_orders=open_orders,
        )

    @app.route("/admin/menu")
    @login_required(roles="admin")
    def admin_menu():
        menu_items = MenuItem.query.order_by(MenuItem.category, MenuItem.name).all()
        return render_template("admin/menu_list.html", menu_items=menu_items)

    @app.route("/admin/menu/new", methods=["GET", "POST"])
    @login_required(roles="admin")
    def admin_menu_new():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip()
            price = request.form.get("price")
            category = request.form.get("category", "").strip() or None
            available = bool(request.form.get("available"))
            try:
                price_value = float(price)
            except (TypeError, ValueError):
                flash("กรุณากรอกราคาที่ถูกต้อง", "danger")
                return render_template("admin/menu_form.html")
            if not name:
                flash("กรุณากรอกชื่อเมนู", "danger")
                return render_template("admin/menu_form.html")
            item = MenuItem(
                name=name,
                description=description,
                price=round(price_value, 2),
                category=category,
                available=available,
            )
            db.session.add(item)
            db.session.commit()
            flash("เพิ่มเมนูเรียบร้อย", "success")
            return redirect(url_for("admin_menu"))
        return render_template("admin/menu_form.html")

    @app.route("/admin/menu/<int:item_id>/edit", methods=["GET", "POST"])
    @login_required(roles="admin")
    def admin_menu_edit(item_id):
        item = MenuItem.query.get_or_404(item_id)
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip()
            price = request.form.get("price")
            category = request.form.get("category", "").strip() or None
            available = bool(request.form.get("available"))
            try:
                price_value = float(price)
            except (TypeError, ValueError):
                flash("กรุณากรอกราคาที่ถูกต้อง", "danger")
                return render_template("admin/menu_form.html", item=item)
            if not name:
                flash("กรุณากรอกชื่อเมนู", "danger")
                return render_template("admin/menu_form.html", item=item)
            item.name = name
            item.description = description
            item.price = round(price_value, 2)
            item.category = category
            item.available = available
            db.session.commit()
            flash("แก้ไขเมนูเรียบร้อย", "success")
            return redirect(url_for("admin_menu"))
        return render_template("admin/menu_form.html", item=item)

    @app.route("/admin/menu/<int:item_id>/delete", methods=["POST"])
    @login_required(roles="admin")
    def admin_menu_delete(item_id):
        item = MenuItem.query.get_or_404(item_id)
        db.session.delete(item)
        db.session.commit()
        flash("ลบเมนูเรียบร้อย", "info")
        return redirect(url_for("admin_menu"))

    @app.route("/admin/tables", methods=["GET", "POST"])
    @login_required(roles="admin")
    def admin_tables():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            code = request.form.get("code", "").strip().upper()
            if not name or not code:
                flash("กรุณากรอกชื่อโต๊ะและรหัสโต๊ะ", "danger")
            elif DiningTable.query.filter_by(code=code).first():
                flash("มีรหัสโต๊ะนี้อยู่แล้ว", "danger")
            else:
                table = DiningTable(name=name, code=code)
                db.session.add(table)
                db.session.commit()
                flash("เพิ่มโต๊ะเรียบร้อย", "success")
            return redirect(url_for("admin_tables"))
        tables = DiningTable.query.order_by(DiningTable.code).all()
        return render_template("admin/tables.html", tables=tables)

    @app.route("/admin/tables/<int:table_id>/delete", methods=["POST"])
    @login_required(roles="admin")
    def admin_table_delete(table_id):
        table = DiningTable.query.get_or_404(table_id)
        if table.orders:
            flash("ไม่สามารถลบโต๊ะที่มีออเดอร์อยู่ได้", "danger")
        else:
            db.session.delete(table)
            db.session.commit()
            flash("ลบโต๊ะเรียบร้อย", "info")
        return redirect(url_for("admin_tables"))

    @app.route("/admin/tables/<int:table_id>/qr")
    @login_required(roles="admin")
    def admin_table_qr(table_id):
        import qrcode

        table = DiningTable.query.get_or_404(table_id)
        qr_url = url_for("table_view", code=table.code, _external=True)
        img = qrcode.make(qr_url)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return send_file(
            buffer,
            mimetype="image/png",
            as_attachment=True,
            download_name=f"table_{table.code}.png",
        )

    # ------------------- Staff views -------------------
    @app.route("/staff/dashboard")
    @login_required(roles=["staff", "admin"])
    def staff_dashboard():
        open_orders = (
            Order.query.order_by(Order.created_at.desc())
            .filter(Order.status != "paid")
            .all()
        )
        tables = DiningTable.query.order_by(DiningTable.code).all()
        return render_template("staff/dashboard.html", orders=open_orders, tables=tables)

    @app.route("/staff/orders/new", methods=["GET", "POST"])
    @login_required(roles=["staff", "admin"])
    def staff_new_order():
        tables = DiningTable.query.order_by(DiningTable.code).all()
        menu_items = MenuItem.query.filter_by(available=True).order_by(MenuItem.name).all()
        if request.method == "POST":
            table_id = request.form.get("table_id")
            table = DiningTable.query.get(table_id)
            if not table:
                flash("กรุณาเลือกโต๊ะ", "danger")
                return render_template(
                    "staff/order_form.html", tables=tables, menu_items=menu_items
                )
            selected_items = parse_order_items(request.form, menu_items)
            if not selected_items:
                flash("กรุณาเลือกเมนูอย่างน้อย 1 รายการ", "danger")
                return render_template(
                    "staff/order_form.html", tables=tables, menu_items=menu_items
                )
            order = Order(table=table, status="pending", created_by=g.user)
            db.session.add(order)
            for menu_item, qty in selected_items:
                order_item = OrderItem(
                    order=order,
                    menu_item=menu_item,
                    quantity=qty,
                    price=menu_item.price,
                )
                db.session.add(order_item)
            order.recalculate_total()
            db.session.commit()
            flash("สร้างออเดอร์เรียบร้อย", "success")
            return redirect(url_for("staff_order_detail", order_id=order.id))
        return render_template(
            "staff/order_form.html", tables=tables, menu_items=menu_items
        )

    @app.route("/staff/orders/<int:order_id>")
    @login_required(roles=["staff", "admin"])
    def staff_order_detail(order_id):
        order = Order.query.get_or_404(order_id)
        return render_template("staff/order_detail.html", order=order)

    @app.route("/staff/orders/<int:order_id>/status", methods=["POST"])
    @login_required(roles=["staff", "admin"])
    def staff_update_status(order_id):
        order = Order.query.get_or_404(order_id)
        status = request.form.get("status")
        if status not in STATUS_FLOW:
            flash("สถานะไม่ถูกต้อง", "danger")
        else:
            order.status = status
            order.updated_at = datetime.utcnow()
            if status == "paid":
                order.paid_at = datetime.utcnow()
                payment_method = request.form.get("payment_method", "").strip()
                order.payment_method = payment_method or None
            else:
                order.payment_method = None
                order.paid_at = None
            db.session.commit()
            flash("อัปเดตสถานะเรียบร้อย", "success")
        return redirect(url_for("staff_order_detail", order_id=order.id))

    @app.route("/staff/orders/<int:order_id>/acknowledge", methods=["POST"])
    @login_required(roles=["staff", "admin"])
    def staff_acknowledge(order_id):
        order = Order.query.get_or_404(order_id)
        order.requested_assistance = False
        order.updated_at = datetime.utcnow()
        db.session.commit()
        flash("รับทราบการเรียกพนักงานแล้ว", "info")
        return redirect(url_for("staff_order_detail", order_id=order.id))

    # ------------------- Customer views -------------------
    @app.route("/table/<code>", methods=["GET", "POST"])
    def table_view(code):
        table = DiningTable.query.filter_by(code=code.upper()).first_or_404()
        menu_items = (
            MenuItem.query.filter_by(available=True)
            .order_by(MenuItem.category, MenuItem.name)
            .all()
        )
        menu_sections = []
        fallback_index = 1
        for item in menu_items:
            category_name = item.category or "เมนูแนะนำ"
            if not menu_sections or menu_sections[-1]["name"] != category_name:
                anchor = slugify(category_name)
                if anchor == "section":
                    anchor = f"section-{fallback_index}"
                    fallback_index += 1
                menu_sections.append({"name": category_name, "anchor": anchor, "items": []})
            menu_sections[-1]["items"].append(item)
        active_orders = (
            Order.query.filter(Order.table == table, Order.status != "paid")
            .order_by(Order.created_at.desc())
            .all()
        )
        latest_order = active_orders[0] if active_orders else None
        if request.method == "POST":
            selected_items = parse_order_items(request.form, menu_items)
            if not selected_items:
                flash("กรุณาเลือกเมนูอย่างน้อย 1 รายการ", "danger")
                return render_template(
                    "customer/table_view.html",
                    table=table,
                    menu_sections=menu_sections,
                    active_orders=active_orders,
                    latest_order=latest_order,
                )
            order = Order(table=table, status="pending")
            db.session.add(order)
            for menu_item, qty in selected_items:
                order_item = OrderItem(
                    order=order,
                    menu_item=menu_item,
                    quantity=qty,
                    price=menu_item.price,
                )
                db.session.add(order_item)
            order.recalculate_total()
            db.session.commit()
            flash("ส่งออเดอร์เรียบร้อย กรุณารอพนักงานยืนยัน", "success")
            return redirect(url_for("customer_order_summary", code=table.code, order_id=order.id))
        return render_template(
            "customer/table_view.html",
            table=table,
            menu_sections=menu_sections,
            active_orders=active_orders,
            latest_order=latest_order,
        )

    @app.route("/table/<code>/orders/<int:order_id>")
    def customer_order_summary(code, order_id):
        table = DiningTable.query.filter_by(code=code.upper()).first_or_404()
        order = Order.query.filter_by(id=order_id, table=table).first_or_404()
        current_status_index = (
            STATUS_FLOW.index(order.status) if order.status in STATUS_FLOW else -1
        )
        return render_template(
            "customer/order_summary.html",
            table=table,
            order=order,
            current_status_index=current_status_index,
        )

    @app.route("/table/<code>/orders/<int:order_id>/call", methods=["POST"])
    def customer_call_staff(code, order_id):
        table = DiningTable.query.filter_by(code=code.upper()).first_or_404()
        order = Order.query.filter_by(id=order_id, table=table).first_or_404()
        order.requested_assistance = True
        order.updated_at = datetime.utcnow()
        db.session.commit()
        flash("แจ้งพนักงานเรียบร้อย กรุณารอสักครู่", "info")
        return redirect(url_for("customer_order_summary", code=table.code, order_id=order.id))

    def init_database() -> None:
        with app.app_context():
            db.create_all()
            seed_data()

    def seed_data() -> None:
        if User.query.count() == 0:
            admin = User(username="admin", role="admin")
            admin.set_password("admin123")
            staff = User(username="staff", role="staff")
            staff.set_password("staff123")
            db.session.add_all([admin, staff])

        if DiningTable.query.count() == 0:
            tables = [
                DiningTable(name="โต๊ะ 1", code="T1"),
                DiningTable(name="โต๊ะ 2", code="T2"),
                DiningTable(name="โต๊ะ VIP", code="VIP"),
            ]
            db.session.add_all(tables)

        if MenuItem.query.count() == 0:
            menu_items = [
                MenuItem(name="ผัดไทยกุ้งสด", price=80.0, category="อาหารจานหลัก"),
                MenuItem(name="ต้มยำกุ้ง", price=120.0, category="ซุป"),
                MenuItem(name="ชาเย็น", price=45.0, category="เครื่องดื่ม"),
                MenuItem(name="ข้าวเหนียวมะม่วง", price=60.0, category="ของหวาน"),
            ]
            db.session.add_all(menu_items)
        db.session.commit()

    init_database()
    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
