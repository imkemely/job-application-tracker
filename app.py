"""Job Application Tracker - Flask application."""
import os

import mysql.connector
from flask import Flask, abort, flash, redirect, render_template, request, url_for

from database import execute, query

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")


# ------------------------------------------------------------
# Form helpers
# ------------------------------------------------------------
def clean(value):
    """Trim whitespace from a form value and turn empty strings into None."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def check_length(errors, label, value, max_len):
    """Add an error if a text value is longer than its column allows."""
    if value and len(value) > max_len:
        errors.append(f"{label} must be {max_len} characters or fewer.")


def check_url(errors, label, value):
    """Add an error if a URL doesn't start with http:// or https://."""
    if value and not value.lower().startswith(("http://", "https://")):
        errors.append(f"{label} must start with http:// or https://")


# ------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------
@app.route("/")
def dashboard():
    counts = query(
        """
        SELECT
            (SELECT COUNT(*) FROM companies)    AS companies,
            (SELECT COUNT(*) FROM jobs)         AS jobs,
            (SELECT COUNT(*) FROM applications) AS applications,
            (SELECT COUNT(*) FROM contacts)     AS contacts
        """,
        one=True,
    )
    return render_template("dashboard.html", counts=counts)


# ------------------------------------------------------------
# Companies
# ------------------------------------------------------------
def validate_company(form, company_id=None):
    """Pull company fields out of the form and check them.

    Returns (data, errors). data is a dict ready to save.
    """
    data = {
        "company_name": clean(form.get("company_name")),
        "industry": clean(form.get("industry")),
        "website": clean(form.get("website")),
        "city": clean(form.get("city")),
        "state": clean(form.get("state")),
        "notes": clean(form.get("notes")),
    }
    errors = []

    if not data["company_name"]:
        errors.append("Company name is required.")
    check_length(errors, "Company name", data["company_name"], 100)
    check_length(errors, "Industry", data["industry"], 50)
    check_length(errors, "Website", data["website"], 200)
    check_length(errors, "City", data["city"], 50)
    check_length(errors, "State", data["state"], 50)
    check_url(errors, "Website", data["website"])

    # Don't allow two companies with the same name
    if data["company_name"]:
        duplicate = query(
            "SELECT company_id FROM companies "
            "WHERE LOWER(company_name) = LOWER(%s) AND company_id <> %s",
            (data["company_name"], company_id or 0),
            one=True,
        )
        if duplicate:
            errors.append(f"A company named \"{data['company_name']}\" already exists.")

    return data, errors


def get_company_or_404(company_id):
    company = query("SELECT * FROM companies WHERE company_id = %s", (company_id,), one=True)
    if company is None:
        abort(404)
    return company


@app.route("/companies")
def companies():
    rows = query(
        """
        SELECT c.*,
               (SELECT COUNT(*) FROM jobs j     WHERE j.company_id = c.company_id) AS job_count,
               (SELECT COUNT(*) FROM contacts k WHERE k.company_id = c.company_id) AS contact_count
        FROM companies c
        ORDER BY c.company_name
        """
    )
    return render_template("companies.html", companies=rows)


@app.route("/companies/<int:company_id>")
def company_detail(company_id):
    company = get_company_or_404(company_id)
    jobs = query(
        """
        SELECT j.*, COUNT(a.application_id) AS application_count
        FROM jobs j
        LEFT JOIN applications a ON a.job_id = j.job_id
        WHERE j.company_id = %s
        GROUP BY j.job_id
        ORDER BY j.date_posted DESC
        """,
        (company_id,),
    )
    contacts = query(
        "SELECT * FROM contacts WHERE company_id = %s ORDER BY contact_name",
        (company_id,),
    )
    return render_template("company_detail.html", company=company, jobs=jobs, contacts=contacts)


@app.route("/companies/add", methods=["GET", "POST"])
def add_company():
    if request.method == "POST":
        data, errors = validate_company(request.form)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("company_form.html", company=data, mode="add")

        new_id = execute(
            """
            INSERT INTO companies (company_name, industry, website, city, state, notes)
            VALUES (%(company_name)s, %(industry)s, %(website)s, %(city)s, %(state)s, %(notes)s)
            """,
            data,
        )
        flash(f"Added {data['company_name']}.", "success")
        return redirect(url_for("company_detail", company_id=new_id))

    return render_template("company_form.html", company={}, mode="add")


@app.route("/companies/<int:company_id>/edit", methods=["GET", "POST"])
def edit_company(company_id):
    company = get_company_or_404(company_id)

    if request.method == "POST":
        data, errors = validate_company(request.form, company_id)
        if errors:
            for error in errors:
                flash(error, "danger")
            data["company_id"] = company_id
            return render_template("company_form.html", company=data, mode="edit")

        data["company_id"] = company_id
        execute(
            """
            UPDATE companies
            SET company_name = %(company_name)s, industry = %(industry)s,
                website = %(website)s, city = %(city)s, state = %(state)s,
                notes = %(notes)s
            WHERE company_id = %(company_id)s
            """,
            data,
        )
        flash(f"Updated {data['company_name']}.", "success")
        return redirect(url_for("company_detail", company_id=company_id))

    return render_template("company_form.html", company=company, mode="edit")


@app.route("/companies/<int:company_id>/delete", methods=["POST"])
def delete_company(company_id):
    company = get_company_or_404(company_id)
    # ON DELETE CASCADE in schema.sql also removes this company's
    # jobs, their applications, and the company's contacts.
    execute("DELETE FROM companies WHERE company_id = %s", (company_id,))
    flash(f"Deleted {company['company_name']}.", "success")
    return redirect(url_for("companies"))


# ------------------------------------------------------------
# Error pages
# ------------------------------------------------------------
@app.errorhandler(mysql.connector.Error)
def database_error(error):
    """Show a readable page instead of a stack trace when MySQL fails."""
    return render_template("error.html", error=error), 500


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", error=None, not_found=True), 404


if __name__ == "__main__":
    app.run(debug=True)
