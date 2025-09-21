from flask import Blueprint, render_template, redirect, url_for, session

pages_bp = Blueprint("pages", __name__)

@pages_bp.get("/")
def home():
    if "user" not in session:
        return redirect(url_for("pages.login_page"))
    return render_template("main.html")


@pages_bp.get("/login")
def login_page():
    return render_template("login.html")
