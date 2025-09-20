from flask import Blueprint, render_template, redirect

pages_bp = Blueprint("pages", __name__)

@pages_bp.get("/")
def home():
    return render_template("dashboard.html")
