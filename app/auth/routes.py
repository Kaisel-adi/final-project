from datetime import datetime, timezone
from bson import ObjectId
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app.auth.models import User
from app.db import get_db

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("feed.feed_view"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        home_lat = request.form.get("home_lat")
        home_lon = request.form.get("home_lon")
        digest_opt_in = request.form.get("digest_opt_in") == "on"
        digest_radius_km = float(request.form.get("digest_radius_km", 5.0))

        if not name or not email or not password:
            flash("Name, email, and password are required.", "danger")
            return render_template("auth/register.html", name=name, email=email)

        home_coords = None
        if home_lat and home_lon:
            try:
                lat = float(home_lat)
                lon = float(home_lon)
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    home_coords = [lon, lat]  # Standard GeoJSON [longitude, latitude]
            except ValueError:
                pass

        try:
            user = User.create(
                name=name,
                email=email,
                password=password,
                home_coords=home_coords,
                digest_opt_in=digest_opt_in,
                digest_radius_km=digest_radius_km
            )
            login_user(user)
            flash("Account created successfully! Welcome to GCIR.", "success")
            return redirect(url_for("feed.feed_view"))
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("auth/register.html", name=name, email=email)

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("feed.feed_view"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        last_lat = request.form.get("last_lat")
        last_lon = request.form.get("last_lon")

        user = User.get_by_email(email)
        if user and user.check_password(password):
            login_user(user)
            
            # Update last_login_at and optionally last_login_location
            db = get_db()
            update_fields: dict[str, object] = {"last_login_at": datetime.now(timezone.utc)}
            if last_lat and last_lon:
                try:
                    lat, lon = float(last_lat), float(last_lon)
                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                        update_fields["last_login_location"] = {
                            "type": "Point",
                            "coordinates": [lon, lat]
                        }
                except ValueError:
                    pass

            db.users.update_one({"_id": ObjectId(user.id)}, {"$set": update_fields})
            flash(f"Welcome back, {user.name}!", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("feed.feed_view"))
        else:
            flash("Invalid email or password.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        home_lat = request.form.get("home_lat")
        home_lon = request.form.get("home_lon")
        digest_opt_in = request.form.get("digest_opt_in") == "on"
        digest_radius_km = float(request.form.get("digest_radius_km", 5.0))

        update_fields = {
            "name": name,
            "digest_opt_in": digest_opt_in,
            "digest_radius_km": digest_radius_km
        }

        if home_lat and home_lon:
            try:
                lat, lon = float(home_lat), float(home_lon)
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    update_fields["home_location"] = {
                        "type": "Point",
                        "coordinates": [lon, lat]
                    }
            except ValueError:
                pass

        db.users.update_one({"_id": ObjectId(current_user.id)}, {"$set": update_fields})
        flash("Profile updated successfully.", "success")
        return redirect(url_for("auth.profile"))

    # Fetch latest user document
    user_doc = db.users.find_one({"_id": ObjectId(current_user.id)})
    return render_template("auth/profile.html", user_doc=user_doc)


@auth_bp.route("/profile/delete", methods=["POST"])
@login_required
def delete_account():
    db = get_db()
    user_id = ObjectId(current_user.id)
    # Remove upvotes by this user
    db.upvotes.delete_many({"user_id": user_id})
    # Remove digest logs for this user
    db.digest_log.delete_many({"user_id": user_id})
    # Delete user record
    db.users.delete_one({"_id": user_id})
    
    logout_user()
    flash("Your account and associated personal data have been completely deleted.", "info")
    return redirect(url_for("auth.login"))
