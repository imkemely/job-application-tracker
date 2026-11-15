"""Job Application Tracker - Flask application."""
import json
import os
import re
from collections import Counter
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
def percent(part, whole):
    """Whole-number percentage, or 0 if there's nothing to divide by."""
    return round(part * 100 / whole) if whole else 0


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

    # Applications per status (every status shows up, even with 0)
    status_counts = {status: 0 for status in STATUSES}
    for row in query("SELECT status, COUNT(*) AS n FROM applications GROUP BY status"):
        status_counts[row["status"]] = row["n"]

    total = counts["applications"]
    withdrawn = status_counts["Withdrawn"]
    considered = total - withdrawn  # applications the company actually got to decide on
    heard_back = considered - status_counts["Applied"]  # anything past "Applied"
    stats = {
        "active": status_counts["Applied"] + status_counts["Screening"] + status_counts["Interview"],
        "offers": status_counts["Offer"],
        "response_rate": percent(heard_back, considered),
        "interview_rate": percent(status_counts["Interview"] + status_counts["Offer"], considered),
    }
    pipeline = [
        {"status": s, "count": status_counts[s], "percent": percent(status_counts[s], total)}
        for s in STATUSES
    ]

    # Interviews come out of the interview_data JSON column
    interview_sql = """
        SELECT * FROM (
            SELECT a.application_id, a.status, j.job_title, c.company_name,
                   CAST(JSON_UNQUOTE(JSON_EXTRACT(a.interview_data, '$.interview_date')) AS DATE) AS interview_date,
                   JSON_UNQUOTE(JSON_EXTRACT(a.interview_data, '$.interview_type')) AS interview_type
            FROM applications a
            JOIN jobs j      ON j.job_id = a.job_id
            JOIN companies c ON c.company_id = j.company_id
            WHERE JSON_EXTRACT(a.interview_data, '$.interview_date') IS NOT NULL
        ) AS interviews
    """
    upcoming = query(interview_sql + " WHERE interview_date >= CURDATE() ORDER BY interview_date LIMIT 5")
    past = query(interview_sql + " WHERE interview_date < CURDATE() ORDER BY interview_date DESC LIMIT 3")

    recent = query(
        """
        SELECT a.application_id, a.application_date, a.status, j.job_title, c.company_name
        FROM applications a
        JOIN jobs j      ON j.job_id = a.job_id
        JOIN companies c ON c.company_id = j.company_id
        ORDER BY a.application_date DESC, a.application_id DESC
        LIMIT 5
        """
    )

    # Most requested skills across all jobs (from the requirements JSON)
    skill_counts = Counter()
    display_name = {}
    for job in add_skills(query("SELECT requirements FROM jobs")):
        for skill in job["skills"]:
            key = skill.lower()
            skill_counts[key] += 1
            display_name.setdefault(key, skill)
    top_skills = [(display_name[key], n) for key, n in skill_counts.most_common(10)]

    return render_template(
        "dashboard.html",
        counts=counts,
        stats=stats,
        pipeline=pipeline,
        upcoming=upcoming,
        past=past,
        recent=recent,
        top_skills=top_skills,
    )


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
# Applications
# ------------------------------------------------------------
INTERVIEW_FIELDS = ["interview_date", "interview_type", "interviewer", "notes"]


def job_choices():
    """Jobs for the dropdown on the application form, labeled with the company."""
    return query(
        """
        SELECT j.job_id, j.job_title, c.company_name
        FROM jobs j
        JOIN companies c ON c.company_id = j.company_id
        ORDER BY c.company_name, j.job_title
        """
    )


def validate_application(form):
    """Pull application fields out of the form and check them. Returns (data, errors)."""
    errors = []
    data = {
        "job_id": clean(form.get("job_id")),
        "status": clean(form.get("status")) or "Applied",
        "resume_version": clean(form.get("resume_version")),
        "cover_letter_sent": form.get("cover_letter_sent") == "on",
    }

    if not data["job_id"]:
        errors.append("Please choose a job.")
    elif not query("SELECT 1 FROM jobs WHERE job_id = %s", (data["job_id"],), one=True):
        errors.append("That job doesn't exist.")

    application_date = clean(form.get("application_date"))
    if not application_date:
        errors.append("Application date is required.")
    data["application_date"] = parse_date(errors, "Application date", application_date,
                                          allow_future=False)

    if data["status"] not in STATUSES:
        errors.append("Please choose a valid status.")
    check_length(errors, "Resume version", data["resume_version"], 50)

    # Interview details are stored together as one JSON object
    interview = {field: clean(form.get(field)) for field in INTERVIEW_FIELDS}
    interview_date = parse_date(errors, "Interview date", interview["interview_date"])
    if interview_date and data["application_date"] and interview_date < data["application_date"]:
        errors.append("Interview date can't be before the application date.")
    check_length(errors, "Interview type", interview["interview_type"], 50)
    check_length(errors, "Interviewer", interview["interviewer"], 100)
    check_length(errors, "Interview notes", interview["notes"], 2000)

    data["interview"] = interview
    # Only keep the fields that were filled in. Nothing filled in -> NULL.
    filled = {key: value for key, value in interview.items() if value}
    data["interview_data"] = json.dumps(filled) if filled else None

    return data, errors


def get_application_or_404(application_id):
    application = query(
        """
        SELECT a.*, j.job_title, j.company_id, c.company_name
        FROM applications a
        JOIN jobs j      ON j.job_id = a.job_id
        JOIN companies c ON c.company_id = j.company_id
        WHERE a.application_id = %s
        """,
        (application_id,),
        one=True,
    )
    if application is None:
        abort(404)
    interview = load_json(application.get("interview_data"), {})
    application["interview"] = interview if isinstance(interview, dict) else {}
    return application


def save_application_params(data):
    keys = ["job_id", "application_date", "status", "resume_version",
            "cover_letter_sent", "interview_data"]
    return {key: data[key] for key in keys}


@app.route("/applications")
def applications():
    status = clean(request.args.get("status"))

    sql = """
        SELECT a.*, j.job_title, c.company_name,
               JSON_UNQUOTE(JSON_EXTRACT(a.interview_data, '$.interview_date')) AS interview_date
        FROM applications a
        JOIN jobs j      ON j.job_id = a.job_id
        JOIN companies c ON c.company_id = j.company_id
    """
    params = []
    if status in STATUSES:
        sql += " WHERE a.status = %s"
        params.append(status)
    sql += " ORDER BY a.application_date DESC, a.application_id DESC"
    rows = query(sql, params)

    # How many applications are in each status, for the filter buttons
    counts = {row["status"]: row["n"] for row in query(
        "SELECT status, COUNT(*) AS n FROM applications GROUP BY status")}
    total = sum(counts.values())

    return render_template("applications.html", applications=rows, status=status or "",
                           counts=counts, total=total)


@app.route("/applications/<int:application_id>")
def application_detail(application_id):
    application = get_application_or_404(application_id)
    return render_template("application_detail.html", application=application)


@app.route("/applications/add", methods=["GET", "POST"])
def add_application():
    if request.method == "POST":
        data, errors = validate_application(request.form)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("application_form.html", application=data, mode="add",
                                   jobs=job_choices())

        new_id = execute(
            """
            INSERT INTO applications (job_id, application_date, status, resume_version,
                                      cover_letter_sent, interview_data)
            VALUES (%(job_id)s, %(application_date)s, %(status)s, %(resume_version)s,
                    %(cover_letter_sent)s, %(interview_data)s)
            """,
            save_application_params(data),
        )
        flash("Application added.", "success")
        return redirect(url_for("application_detail", application_id=new_id))

    # ?job_id=4 pre-selects the job (used by "Add application" on a job page)
    application = {
        "job_id": request.args.get("job_id"),
        "application_date": date.today().isoformat(),
        "status": "Applied",
        "interview": {},
    }
    return render_template("application_form.html", application=application, mode="add",
                           jobs=job_choices())


@app.route("/applications/<int:application_id>/edit", methods=["GET", "POST"])
def edit_application(application_id):
    application = get_application_or_404(application_id)

    if request.method == "POST":
        data, errors = validate_application(request.form)
        data["application_id"] = application_id
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("application_form.html", application=data, mode="edit",
                                   jobs=job_choices())

        params = save_application_params(data)
        params["application_id"] = application_id
        execute(
            """
            UPDATE applications
            SET job_id = %(job_id)s, application_date = %(application_date)s,
                status = %(status)s, resume_version = %(resume_version)s,
                cover_letter_sent = %(cover_letter_sent)s, interview_data = %(interview_data)s
            WHERE application_id = %(application_id)s
            """,
            params,
        )
        flash("Application updated.", "success")
        return redirect(url_for("application_detail", application_id=application_id))

    return render_template("application_form.html", application=application, mode="edit",
                           jobs=job_choices())


@app.route("/applications/<int:application_id>/delete", methods=["POST"])
def delete_application(application_id):
    application = get_application_or_404(application_id)
    execute("DELETE FROM applications WHERE application_id = %s", (application_id,))
    flash(f"Deleted your application for {application['job_title']} at "
          f"{application['company_name']}.", "success")
    return redirect(url_for("applications"))


# ------------------------------------------------------------
# Contacts
# ------------------------------------------------------------
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PATTERN = re.compile(r"^[0-9+()\-.\s]+(\s*(x|ext\.?)\s*[0-9]+)?$", re.IGNORECASE)


def validate_contact(form):
    """Pull contact fields out of the form and check them. Returns (data, errors)."""
    errors = []
    data = {
        "company_id": clean(form.get("company_id")),
        "contact_name": clean(form.get("contact_name")),
        "title": clean(form.get("title")),
        "email": clean(form.get("email")),
        "phone": clean(form.get("phone")),
        "linkedin_url": clean(form.get("linkedin_url")),
        "notes": clean(form.get("notes")),
    }

    if not data["company_id"]:
        errors.append("Please choose a company.")
    elif not query("SELECT 1 FROM companies WHERE company_id = %s", (data["company_id"],), one=True):
        errors.append("That company doesn't exist.")

    if not data["contact_name"]:
        errors.append("Contact name is required.")
    check_length(errors, "Contact name", data["contact_name"], 100)
    check_length(errors, "Title", data["title"], 100)

    check_length(errors, "Email", data["email"], 100)
    if data["email"] and not EMAIL_PATTERN.match(data["email"]):
        errors.append("Please enter a valid email address (like name@company.com).")

    check_length(errors, "Phone", data["phone"], 20)
    if data["phone"]:
        digits = sum(ch.isdigit() for ch in data["phone"])
        if not PHONE_PATTERN.match(data["phone"]) or digits < 7:
            errors.append("Please enter a valid phone number (like 305-555-0142).")

    check_length(errors, "LinkedIn URL", data["linkedin_url"], 200)
    check_url(errors, "LinkedIn URL", data["linkedin_url"])
    if data["linkedin_url"] and "linkedin.com" not in data["linkedin_url"].lower():
        errors.append("LinkedIn URL should be a linkedin.com link.")

    return data, errors


def get_contact_or_404(contact_id):
    contact = query(
        """
        SELECT k.*, c.company_name
        FROM contacts k
        JOIN companies c ON c.company_id = k.company_id
        WHERE k.contact_id = %s
        """,
        (contact_id,),
        one=True,
    )
    if contact is None:
        abort(404)
    return contact


@app.route("/contacts")
def contacts():
    search = clean(request.args.get("q"))
    company_id = clean(request.args.get("company_id"))

    sql = """
        SELECT k.*, c.company_name
        FROM contacts k
        JOIN companies c ON c.company_id = k.company_id
        WHERE 1 = 1
    """
    params = []
    if search:
        sql += " AND (k.contact_name LIKE %s OR k.title LIKE %s OR k.email LIKE %s)"
        params += [f"%{search}%"] * 3
    if company_id and company_id.isdigit():
        sql += " AND k.company_id = %s"
        params.append(company_id)
    sql += " ORDER BY k.contact_name"

    return render_template("contacts.html", contacts=query(sql, params),
                           companies=company_choices(), search=search or "",
                           company_id=company_id or "")


@app.route("/contacts/<int:contact_id>")
def contact_detail(contact_id):
    contact = get_contact_or_404(contact_id)
    return render_template("contact_detail.html", contact=contact)


@app.route("/contacts/add", methods=["GET", "POST"])
def add_contact():
    if request.method == "POST":
        data, errors = validate_contact(request.form)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("contact_form.html", contact=data, mode="add",
                                   companies=company_choices())

        new_id = execute(
            """
            INSERT INTO contacts (company_id, contact_name, title, email, phone, linkedin_url, notes)
            VALUES (%(company_id)s, %(contact_name)s, %(title)s, %(email)s, %(phone)s,
                    %(linkedin_url)s, %(notes)s)
            """,
            data,
        )
        flash(f"Added {data['contact_name']}.", "success")
        return redirect(url_for("contact_detail", contact_id=new_id))

    # ?company_id=3 pre-selects the company (used by "Add contact" on a company page)
    contact = {"company_id": request.args.get("company_id")}
    return render_template("contact_form.html", contact=contact, mode="add",
                           companies=company_choices())


@app.route("/contacts/<int:contact_id>/edit", methods=["GET", "POST"])
def edit_contact(contact_id):
    contact = get_contact_or_404(contact_id)

    if request.method == "POST":
        data, errors = validate_contact(request.form)
        data["contact_id"] = contact_id
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("contact_form.html", contact=data, mode="edit",
                                   companies=company_choices())

        execute(
            """
            UPDATE contacts
            SET company_id = %(company_id)s, contact_name = %(contact_name)s, title = %(title)s,
                email = %(email)s, phone = %(phone)s, linkedin_url = %(linkedin_url)s,
                notes = %(notes)s
            WHERE contact_id = %(contact_id)s
            """,
            data,
        )
        flash(f"Updated {data['contact_name']}.", "success")
        return redirect(url_for("contact_detail", contact_id=contact_id))

    return render_template("contact_form.html", contact=contact, mode="edit",
                           companies=company_choices())


@app.route("/contacts/<int:contact_id>/delete", methods=["POST"])
def delete_contact(contact_id):
    contact = get_contact_or_404(contact_id)
    execute("DELETE FROM contacts WHERE contact_id = %s", (contact_id,))
    flash(f"Deleted {contact['contact_name']}.", "success")
    return redirect(url_for("contacts"))


# ------------------------------------------------------------
# Job Match
# ------------------------------------------------------------
# Different ways people write the same skill, all mapped to one name
SKILL_ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "python3": "python",
    "k8s": "kubernetes",
    "postgres": "postgresql",
    "springboot": "spring boot",
    "node": "node.js",
    "nodejs": "node.js",
    "reactjs": "react",
    "react.js": "react",
    "amazon web services": "aws",
    "html5": "html",
    "css3": "css",
}


def normalize_skill(skill):
    """Lowercase, trim, collapse spaces and apply aliases so "  Py " matches "Python"."""
    key = " ".join(skill.lower().split())
    return SKILL_ALIASES.get(key, key)


def match_jobs(user_skills, jobs):
    """Score every job against the user's skills.

    match % = (required skills the user has) / (total required skills) * 100

    Returns a list of result dicts sorted best match first. Jobs that don't
    list any required skills are skipped, since there's nothing to compare.
    """
    have = {normalize_skill(s) for s in user_skills}
    results = []

    for job in jobs:
        if not job["skills"]:
            continue
        matched, missing = [], []
        for skill in job["skills"]:
            (matched if normalize_skill(skill) in have else missing).append(skill)

        total = len(job["skills"])
        results.append({
            "job": job,
            "matched": matched,
            "missing": missing,
            "total": total,
            "percent": round(len(matched) * 100 / total),
        })

    # Highest % first; ties go to the job where you match more skills, then by title
    results.sort(key=lambda r: (-r["percent"], -len(r["matched"]), r["job"]["job_title"].lower()))
    return results


@app.route("/job-match")
def job_match():
    skills_text = request.args.get("skills", "")
    user_skills = parse_skills(skills_text)
    show_all = request.args.get("show_all") == "on"

    jobs_with_skills = add_skills(query(
        """
        SELECT j.job_id, j.job_title, j.job_type, j.salary_min, j.salary_max, j.requirements,
               c.company_name,
               (SELECT a.status FROM applications a WHERE a.job_id = j.job_id
                ORDER BY a.application_date DESC LIMIT 1) AS application_status
        FROM jobs j
        JOIN companies c ON c.company_id = j.company_id
        """
    ))

    # Every skill that appears in any job, for the "click to add" chips
    all_skills = {}
    for job in jobs_with_skills:
        for skill in job["skills"]:
            all_skills.setdefault(normalize_skill(skill), skill)
    skill_options = sorted(all_skills.values(), key=str.lower)

    results, hidden, skills_to_learn = [], 0, []
    if user_skills:
        results = match_jobs(user_skills, jobs_with_skills)
        if not show_all:
            hidden = sum(1 for r in results if r["percent"] == 0)
            results = [r for r in results if r["percent"] > 0]

        # Missing skills that show up most often in the jobs you partly match
        missing_counts = Counter()
        names = {}
        for r in results:
            for skill in r["missing"]:
                key = normalize_skill(skill)
                missing_counts[key] += 1
                names.setdefault(key, skill)
        skills_to_learn = [(names[key], n) for key, n in missing_counts.most_common(5)]

    return render_template(
        "job_match.html",
        skills_text=skills_text,
        user_skills=user_skills,
        show_all=show_all,
        results=results,
        hidden=hidden,
        skills_to_learn=skills_to_learn,
        skill_options=skill_options,
    )


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
