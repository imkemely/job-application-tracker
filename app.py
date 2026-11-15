"""Job Application Tracker - Flask application."""
import json
import os
from datetime import date, datetime

import mysql.connector
from flask import Flask, abort, flash, redirect, render_template, request, url_for

from database import execute, query

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")

# These match the ENUM values in schema.sql
JOB_TYPES = ["Full-time", "Part-time", "Contract", "Internship"]
STATUSES = ["Applied", "Screening", "Interview", "Offer", "Rejected", "Withdrawn"]

# Bootstrap color for each application status badge
STATUS_COLORS = {
    "Applied": "primary",
    "Screening": "info",
    "Interview": "warning",
    "Offer": "success",
    "Rejected": "danger",
    "Withdrawn": "secondary",
}


# Make these lists available in every template (and in _macros.html)
app.jinja_env.globals.update(JOB_TYPES=JOB_TYPES, STATUSES=STATUSES, STATUS_COLORS=STATUS_COLORS)


@app.context_processor
def template_today():
    """Today's date as YYYY-MM-DD, used to stop date pickers going into the future."""
    return {"today": date.today().isoformat()}


@app.template_filter("money")
def money(value):
    """Format a number as $75,000."""
    if value is None:
        return ""
    return f"${value:,.0f}"


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


def parse_int(errors, label, value, minimum=0, maximum=10_000_000):
    """Turn a form value into an int, or add an error. Empty -> None."""
    if value is None:
        return None
    try:
        number = int(value.replace(",", "").replace("$", ""))
    except ValueError:
        errors.append(f"{label} must be a whole number.")
        return None
    if number < minimum or number > maximum:
        errors.append(f"{label} must be between {minimum:,} and {maximum:,}.")
        return None
    return number


def parse_date(errors, label, value, allow_future=True):
    """Turn a YYYY-MM-DD form value into a date, or add an error. Empty -> None."""
    if value is None:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        errors.append(f"{label} must be a valid date.")
        return None
    if not allow_future and parsed > date.today():
        errors.append(f"{label} can't be in the future.")
        return None
    return parsed


def parse_skills(text):
    """Split "Python, SQL, flask" into ["Python", "SQL", "flask"], dropping duplicates."""
    skills, seen = [], set()
    for part in (text or "").split(","):
        skill = part.strip()
        if skill and skill.lower() not in seen:
            seen.add(skill.lower())
            skills.append(skill)
    return skills


def load_json(value, default):
    """Read a JSON column. MySQL can hand it back as str, bytes, or already parsed."""
    if value is None:
        return default
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return default
    return value


def add_skills(rows):
    """Attach a Python list of skills to each job row as row['skills']."""
    for row in rows:
        skills = load_json(row.get("requirements"), [])
        row["skills"] = skills if isinstance(skills, list) else []
    return rows


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
# Jobs
# ------------------------------------------------------------
def company_choices():
    """Companies for the dropdown on the job and contact forms."""
    return query("SELECT company_id, company_name FROM companies ORDER BY company_name")


def validate_job(form):
    """Pull job fields out of the form and check them. Returns (data, errors)."""
    errors = []
    data = {
        "company_id": clean(form.get("company_id")),
        "job_title": clean(form.get("job_title")),
        "job_type": clean(form.get("job_type")),
        "job_url": clean(form.get("job_url")),
        "skills_text": form.get("skills", ""),
    }

    # Company must be picked and must actually exist
    if not data["company_id"]:
        errors.append("Please choose a company.")
    elif not query("SELECT 1 FROM companies WHERE company_id = %s", (data["company_id"],), one=True):
        errors.append("That company doesn't exist.")

    if not data["job_title"]:
        errors.append("Job title is required.")
    check_length(errors, "Job title", data["job_title"], 100)

    if data["job_type"] and data["job_type"] not in JOB_TYPES:
        errors.append("Please choose a valid job type.")

    check_length(errors, "Job URL", data["job_url"], 300)
    check_url(errors, "Job URL", data["job_url"])

    data["salary_min"] = parse_int(errors, "Minimum salary", clean(form.get("salary_min")))
    data["salary_max"] = parse_int(errors, "Maximum salary", clean(form.get("salary_max")))
    if (data["salary_min"] is not None and data["salary_max"] is not None
            and data["salary_min"] > data["salary_max"]):
        errors.append("Minimum salary can't be higher than maximum salary.")

    data["date_posted"] = parse_date(errors, "Date posted", clean(form.get("date_posted")),
                                     allow_future=False)

    skills = parse_skills(data["skills_text"])
    for skill in skills:
        check_length(errors, f"Skill \"{skill[:20]}\"", skill, 50)
    data["skills"] = skills
    data["requirements"] = json.dumps(skills)

    return data, errors


def get_job_or_404(job_id):
    job = query(
        """
        SELECT j.*, c.company_name
        FROM jobs j
        JOIN companies c ON c.company_id = j.company_id
        WHERE j.job_id = %s
        """,
        (job_id,),
        one=True,
    )
    if job is None:
        abort(404)
    add_skills([job])
    return job


def save_job_params(data):
    """Only the columns the INSERT/UPDATE needs."""
    keys = ["company_id", "job_title", "job_type", "salary_min", "salary_max",
            "job_url", "date_posted", "requirements"]
    return {key: data[key] for key in keys}


@app.route("/jobs")
def jobs():
    search = clean(request.args.get("q"))
    job_type = clean(request.args.get("type"))

    sql = """
        SELECT j.*, c.company_name, COUNT(a.application_id) AS application_count
        FROM jobs j
        JOIN companies c ON c.company_id = j.company_id
        LEFT JOIN applications a ON a.job_id = j.job_id
        WHERE 1 = 1
    """
    params = []
    if search:
        sql += " AND (j.job_title LIKE %s OR c.company_name LIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    if job_type in JOB_TYPES:
        sql += " AND j.job_type = %s"
        params.append(job_type)
    sql += " GROUP BY j.job_id ORDER BY j.date_posted DESC, j.job_id DESC"

    rows = add_skills(query(sql, params))
    return render_template("jobs.html", jobs=rows, search=search or "", job_type=job_type or "")


@app.route("/jobs/<int:job_id>")
def job_detail(job_id):
    job = get_job_or_404(job_id)
    applications = query(
        "SELECT * FROM applications WHERE job_id = %s ORDER BY application_date DESC",
        (job_id,),
    )
    return render_template("job_detail.html", job=job, applications=applications)


@app.route("/jobs/add", methods=["GET", "POST"])
def add_job():
    if request.method == "POST":
        data, errors = validate_job(request.form)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("job_form.html", job=data, mode="add",
                                   companies=company_choices())

        new_id = execute(
            """
            INSERT INTO jobs (company_id, job_title, job_type, salary_min, salary_max,
                              job_url, date_posted, requirements)
            VALUES (%(company_id)s, %(job_title)s, %(job_type)s, %(salary_min)s, %(salary_max)s,
                    %(job_url)s, %(date_posted)s, %(requirements)s)
            """,
            save_job_params(data),
        )
        flash(f"Added {data['job_title']}.", "success")
        return redirect(url_for("job_detail", job_id=new_id))

    # ?company_id=3 pre-selects the company (used by "Add job" on a company page)
    job = {"company_id": request.args.get("company_id")}
    return render_template("job_form.html", job=job, mode="add", companies=company_choices())


@app.route("/jobs/<int:job_id>/edit", methods=["GET", "POST"])
def edit_job(job_id):
    job = get_job_or_404(job_id)

    if request.method == "POST":
        data, errors = validate_job(request.form)
        data["job_id"] = job_id
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("job_form.html", job=data, mode="edit",
                                   companies=company_choices())

        params = save_job_params(data)
        params["job_id"] = job_id
        execute(
            """
            UPDATE jobs
            SET company_id = %(company_id)s, job_title = %(job_title)s, job_type = %(job_type)s,
                salary_min = %(salary_min)s, salary_max = %(salary_max)s, job_url = %(job_url)s,
                date_posted = %(date_posted)s, requirements = %(requirements)s
            WHERE job_id = %(job_id)s
            """,
            params,
        )
        flash(f"Updated {data['job_title']}.", "success")
        return redirect(url_for("job_detail", job_id=job_id))

    job["skills_text"] = ", ".join(job["skills"])
    return render_template("job_form.html", job=job, mode="edit", companies=company_choices())


@app.route("/jobs/<int:job_id>/delete", methods=["POST"])
def delete_job(job_id):
    job = get_job_or_404(job_id)
    # ON DELETE CASCADE also removes this job's applications
    execute("DELETE FROM jobs WHERE job_id = %s", (job_id,))
    flash(f"Deleted {job['job_title']} at {job['company_name']}.", "success")
    return redirect(url_for("jobs"))


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
