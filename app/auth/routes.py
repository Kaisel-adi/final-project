from datetime import datetime, timezone
from bson import ObjectId
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from app.auth.models import User
from app.auth.validators import validate_email_format
from app.auth.services import stage_pending_signup, verify_and_complete_signup, resend_verification_otp
from app.reports.services import CATEGORIES
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

        # Validate email format
        if not validate_email_format(email):
            flash("Please enter a valid email address.", "danger")
            return render_template("auth/register.html", name=name, email=email)

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
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
            pending = stage_pending_signup(
                name=name,
                email=email,
                password=password,
                home_coords=home_coords,
                digest_opt_in=digest_opt_in,
                digest_radius_km=digest_radius_km
            )
            session["pending_signup_email"] = email.strip().lower()
            if pending.get("is_mock"):
                flash(f"A 6-digit verification code has been sent to {email}. [Dev Mode Code: {pending['otp']}]", "info")
            else:
                flash(f"A 6-digit verification code has been sent to {email}. Please check your inbox and spam folder, and enter it below.", "info")
            return redirect(url_for("auth.verify_otp"))
        except (ValueError, RuntimeError) as e:
            flash(str(e), "danger")
            return render_template("auth/register.html", name=name, email=email)
        except Exception as e:
            flash(f"Error initiating registration: {str(e)}", "danger")
            return render_template("auth/register.html", name=name, email=email)

    return render_template("auth/register.html")


@auth_bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    if current_user.is_authenticated:
        return redirect(url_for("feed.feed_view"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower() or session.get("pending_signup_email")
        otp = request.form.get("otp", "").strip()

        if not email:
            flash("No pending registration session found. Please register again.", "danger")
            return redirect(url_for("auth.register"))

        if not otp:
            flash("Please enter the 6-digit verification code.", "danger")
            return render_template("auth/verify_otp.html", email=email)

        user, msg = verify_and_complete_signup(email, otp)
        if user:
            session.permanent = True
            session.pop("pending_signup_email", None)
            login_user(user, remember=True)
            flash(msg, "success")
            return redirect(url_for("feed.feed_view"))
        else:
            flash(msg, "danger")
            return render_template("auth/verify_otp.html", email=email)

    email = session.get("pending_signup_email") or request.args.get("email", "").strip().lower()
    if not email:
        flash("Please enter your registration details first.", "warning")
        return redirect(url_for("auth.register"))

    return render_template("auth/verify_otp.html", email=email)


@auth_bp.route("/resend-otp", methods=["POST"])
def resend_otp():
    if current_user.is_authenticated:
        return redirect(url_for("feed.feed_view"))

    email = request.form.get("email", "").strip().lower() or session.get("pending_signup_email")
    if not email:
        flash("No pending registration found.", "danger")
        return redirect(url_for("auth.register"))

    success, msg = resend_verification_otp(email)
    flash(msg, "info" if success else "warning")
    return redirect(url_for("auth.verify_otp", email=email))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("feed.feed_view"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        last_lat = request.form.get("last_lat")
        last_lon = request.form.get("last_lon")

        # Validate email format
        if not email or not validate_email_format(email):
            flash("Please enter a valid email address.", "danger")
            return render_template("auth/login.html")

        user = User.get_by_email(email)
        if user and user.check_password(password):
            if getattr(user, "is_banned", False):
                flash("Your account has been suspended by an administrator.", "danger")
                return render_template("auth/login.html")

            session.permanent = True
            login_user(user, remember=True)
            
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
    user_id = ObjectId(current_user.id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        home_lat = request.form.get("home_lat")
        home_lon = request.form.get("home_lon")
        digest_opt_in = request.form.get("digest_opt_in") == "on"
        digest_radius_km = float(request.form.get("digest_radius_km", 5.0))

        update_fields: dict[str, object] = {
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

        db.users.update_one({"_id": user_id}, {"$set": update_fields})
        flash("Profile updated successfully.", "success")
        return redirect(url_for("auth.profile"))

    # Fetch latest user document with resilient fallback
    user_doc = db.users.find_one({"_id": user_id}) or getattr(current_user, "doc", {}) or {}

    # Fetch all reports submitted by this user
    try:
        user_reports = list(db.reports.find({"author_id": user_id}).sort("created_at", -1))
    except Exception:
        user_reports = []

    cat_dict = dict(CATEGORIES)
    for r in user_reports:
        r["cat_label"] = cat_dict.get(r.get("category"), r.get("category", "General"))

    coords = [77.2090, 28.6139]
    if user_doc and isinstance(user_doc.get("home_location"), dict) and user_doc["home_location"].get("coordinates"):
        coords = user_doc["home_location"]["coordinates"]
    elif current_user.home_location and isinstance(current_user.home_location, dict) and current_user.home_location.get("coordinates"):
        coords = current_user.home_location["coordinates"]

    return render_template(
        "auth/profile.html",
        user_doc=user_doc,
        user_reports=user_reports,
        coords=coords
    )


@auth_bp.route("/profile/delete", methods=["POST"])
@login_required
def delete_account():
    db = get_db()
    user_id = ObjectId(current_user.id)

    # 1. Adjust upvotes on reports this user upvoted
    user_upvotes = list(db.upvotes.find({"user_id": user_id}))
    for up in user_upvotes:
        db.reports.update_one({"_id": up["report_id"]}, {"$inc": {"upvote_count": -1}})
    db.upvotes.delete_many({"user_id": user_id})

    # 2. Delete digest logs for this user
    db.digest_log.delete_many({"user_id": user_id})

    # 3. Delete reports submitted by this user
    db.reports.delete_many({"author_id": user_id})

    # 4. Delete user record
    db.users.delete_one({"_id": user_id})
    
    logout_user()
    flash("Your account, reported issues, and associated personal data have been completely deleted.", "info")
    return redirect(url_for("auth.login"))
