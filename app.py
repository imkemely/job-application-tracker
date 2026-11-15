import json
import os
from collections import Counter
from datetime import date, datetime

import mysql.connector
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for

from database import execute, query

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")

# same values as the ENUMs in schema.sql
JOB_TYPES = ["Full-time", "Part-time", "Contract", "Internship"]
STATUSES = ["Applied", "Screening", "Interview", "Offer", "Rejected", "Withdrawn"]

app.jinja_env.globals.update(JOB_TYPES=JOB_TYPES, STATUSES=STATUSES)


@app.context_processor
def add_today():
    # used as the max date on the date inputs
    return {"today": date.today().isoformat()}


@app.template_filter("money")
def money(value):
    if value is None:
        return ""
    return f"${value:,.0f}"


@app.template_filter("short_url")
def short_url(url, keep_path=False):
    # "https://www.careers.example.com/jobs/123" -> "careers.example.com"
    text = url.split("://", 1)[-1]
    if text.startswith("www."):
        text = text[4:]
    if not keep_path:
        text = text.split("/")[0]
    return text.rstrip("/")


# ---------- helpers for the forms ----------

def clean(value):
    # strip spaces and treat empty fields as NULL
    if value is None:
        return None
    value = value.strip()
    return value or None


def check_length(errors, label, value, max_len):
    if value and len(value) > max_len:
        errors.append(f"{label} must be {max_len} characters or fewer.")


def check_url(errors, label, value):
    if value and not value.lower().startswith(("http://", "https://")):
        errors.append(f"{label} must start with http:// or https://")


def parse_int(errors, label, value):
    if value is None:
        return None
    try:
        number = int(value.replace(",", "").replace("$", ""))
    except ValueError:
        errors.append(f"{label} must be a whole number.")
        return None
    if number < 0 or number > 10000000:
        errors.append(f"{label} must be between 0 and 10,000,000.")
        return None
    return number


def parse_date(errors, label, value, allow_future=True):
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
    # "Python, SQL, python" -> ["Python", "SQL"]
    skills = []
    for part in (text or "").split(","):
        skill = part.strip()
        if skill and skill.lower() not in [s.lower() for s in skills]:
            skills.append(skill)
    return skills


def load_json(value, default):
    # mysql connector gives JSON columns back as a string (sometimes bytes)
    if value is None:
        return default
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def add_skills(jobs):
    # requirements JSON -> python list, stored in job["skills"]
    for job in jobs:
        job["skills"] = load_json(job.get("requirements"), [])
    return jobs


def percent(part, whole):
    if whole == 0:
        return 0
    return round(part * 100 / whole)


# ---------- fun stuff ----------

WEEKLY_GOAL = 10

# saving an application with one of these statuses sets off confetti
CELEBRATE = ["Interview", "Offer"]


# ---------- dashboard ----------

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

    status_counts = {}
    for status in STATUSES:
        status_counts[status] = 0
    for row in query("SELECT status, COUNT(*) AS n FROM applications GROUP BY status"):
        status_counts[row["status"]] = row["n"]

    total = counts["applications"]
    active = status_counts["Applied"] + status_counts["Screening"] + status_counts["Interview"]
    # response rate = anything that got past "Applied" (not counting ones I withdrew)
    considered = total - status_counts["Withdrawn"]
    heard_back = considered - status_counts["Applied"]
    response_rate = percent(heard_back, considered)

    # applications since Monday (mode 1 = weeks start on Monday)
    this_week = query(
        "SELECT COUNT(*) AS n FROM applications "
        "WHERE YEARWEEK(application_date, 1) = YEARWEEK(CURDATE(), 1)",
        one=True,
    )["n"]

    # interview date lives inside the interview_data JSON column
    interviews = query(
        """
        SELECT a.application_id, j.job_title, c.company_name,
               JSON_UNQUOTE(JSON_EXTRACT(a.interview_data, '$.interview_date')) AS interview_date,
               JSON_UNQUOTE(JSON_EXTRACT(a.interview_data, '$.interview_type')) AS interview_type
        FROM applications a
        JOIN jobs j ON j.job_id = a.job_id
        JOIN companies c ON c.company_id = j.company_id
        WHERE a.interview_data IS NOT NULL
        ORDER BY interview_date DESC
        LIMIT 5
        """
    )

    recent = query(
        """
        SELECT a.application_id, a.application_date, a.status, j.job_title, c.company_name
        FROM applications a
        JOIN jobs j ON j.job_id = a.job_id
        JOIN companies c ON c.company_id = j.company_id
        ORDER BY a.application_date DESC
        LIMIT 5
        """
    )

    # how many jobs ask for each skill
    skill_counts = Counter()
    for job in add_skills(query("SELECT requirements FROM jobs")):
        for skill in job["skills"]:
            skill_counts[skill] += 1

    return render_template(
        "dashboard.html",
        counts=counts,
        status_counts=status_counts,
        total=total,
        active=active,
        response_rate=response_rate,
        interviews=interviews,
        recent=recent,
        top_skills=skill_counts.most_common(10),
        this_week=this_week,
        weekly_goal=WEEKLY_GOAL,
        week_percent=min(percent(this_week, WEEKLY_GOAL), 100),
    )


# ---------- companies ----------

def validate_company(form, company_id=None):
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

    # no duplicate company names
    if data["company_name"]:
        existing = query(
            "SELECT company_id FROM companies WHERE LOWER(company_name) = LOWER(%s) AND company_id <> %s",
            (data["company_name"], company_id or 0),
            one=True,
        )
        if existing:
            errors.append(f"{data['company_name']} is already in your companies.")

    return data, errors


def get_company(company_id):
    company = query("SELECT * FROM companies WHERE company_id = %s", (company_id,), one=True)
    if company is None:
        abort(404)
    return company


@app.route("/companies")
def companies():
    rows = query(
        """
        SELECT c.*,
               (SELECT COUNT(*) FROM jobs j WHERE j.company_id = c.company_id) AS job_count,
               (SELECT COUNT(*) FROM contacts k WHERE k.company_id = c.company_id) AS contact_count
        FROM companies c
        ORDER BY c.company_name
        """
    )
    return render_template("companies.html", companies=rows)


@app.route("/companies/<int:company_id>")
def company_detail(company_id):
    company = get_company(company_id)
    jobs = query(
        """
        SELECT j.*,
               (SELECT COUNT(*) FROM applications a WHERE a.job_id = j.job_id) AS application_count
        FROM jobs j
        WHERE j.company_id = %s
        """,
        (company_id,),
    )
    contacts = query("SELECT * FROM contacts WHERE company_id = %s", (company_id,))
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
            "INSERT INTO companies (company_name, industry, website, city, state, notes) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (data["company_name"], data["industry"], data["website"],
             data["city"], data["state"], data["notes"]),
        )
        flash(f"Added {data['company_name']}.", "success")
        return redirect(url_for("company_detail", company_id=new_id))

    return render_template("company_form.html", company={}, mode="add")


@app.route("/companies/<int:company_id>/edit", methods=["GET", "POST"])
def edit_company(company_id):
    company = get_company(company_id)

    if request.method == "POST":
        data, errors = validate_company(request.form, company_id)
        data["company_id"] = company_id
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("company_form.html", company=data, mode="edit")

        execute(
            "UPDATE companies SET company_name = %s, industry = %s, website = %s, "
            "city = %s, state = %s, notes = %s WHERE company_id = %s",
            (data["company_name"], data["industry"], data["website"],
             data["city"], data["state"], data["notes"], company_id),
        )
        flash(f"Saved changes to {data['company_name']}.", "success")
        return redirect(url_for("company_detail", company_id=company_id))

    return render_template("company_form.html", company=company, mode="edit")


@app.route("/companies/<int:company_id>/delete", methods=["POST"])
def delete_company(company_id):
    company = get_company(company_id)
    # ON DELETE CASCADE takes care of its jobs, applications and contacts
    execute("DELETE FROM companies WHERE company_id = %s", (company_id,))
    flash(f"Deleted {company['company_name']}.", "success")
    return redirect(url_for("companies"))


# ---------- jobs ----------

def company_list():
    return query("SELECT company_id, company_name FROM companies ORDER BY company_name")


def validate_job(form):
    errors = []
    data = {
        "company_id": clean(form.get("company_id")),
        "job_title": clean(form.get("job_title")),
        "job_type": clean(form.get("job_type")),
        "job_url": clean(form.get("job_url")),
        "skills_text": form.get("skills", ""),
    }

    if not data["company_id"]:
        errors.append("Pick a company.")
    elif not query("SELECT 1 FROM companies WHERE company_id = %s", (data["company_id"],), one=True):
        errors.append("That company doesn't exist.")

    if not data["job_title"]:
        errors.append("Job title is required.")
    check_length(errors, "Job title", data["job_title"], 100)

    if data["job_type"] and data["job_type"] not in JOB_TYPES:
        errors.append("Pick a valid job type.")

    check_length(errors, "Job URL", data["job_url"], 300)
    check_url(errors, "Job URL", data["job_url"])

    data["salary_min"] = parse_int(errors, "Min salary", clean(form.get("salary_min")))
    data["salary_max"] = parse_int(errors, "Max salary", clean(form.get("salary_max")))
    if data["salary_min"] and data["salary_max"] and data["salary_min"] > data["salary_max"]:
        errors.append("Min salary can't be more than max salary.")

    data["date_posted"] = parse_date(errors, "Date posted", clean(form.get("date_posted")),
                                     allow_future=False)

    # skills get saved as a JSON list in the requirements column
    data["skills"] = parse_skills(data["skills_text"])
    data["requirements"] = json.dumps(data["skills"])

    return data, errors


def get_job(job_id):
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


@app.route("/jobs")
def jobs():
    search = clean(request.args.get("q"))
    job_type = clean(request.args.get("type"))

    sql = """
        SELECT j.*, c.company_name,
               (SELECT COUNT(*) FROM applications a WHERE a.job_id = j.job_id) AS application_count
        FROM jobs j
        JOIN companies c ON c.company_id = j.company_id
    """
    conditions = []
    params = []
    if search:
        conditions.append("(j.job_title LIKE %s OR c.company_name LIKE %s)")
        params += ["%" + search + "%", "%" + search + "%"]
    if job_type in JOB_TYPES:
        conditions.append("j.job_type = %s")
        params.append(job_type)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY c.company_name, j.job_title"

    rows = add_skills(query(sql, params))
    return render_template("jobs.html", jobs=rows, search=search or "", job_type=job_type or "")


@app.route("/jobs/<int:job_id>")
def job_detail(job_id):
    job = get_job(job_id)
    applications = query("SELECT * FROM applications WHERE job_id = %s", (job_id,))
    return render_template("job_detail.html", job=job, applications=applications)


@app.route("/jobs/add", methods=["GET", "POST"])
def add_job():
    if request.method == "POST":
        data, errors = validate_job(request.form)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("job_form.html", job=data, mode="add", companies=company_list())

        new_id = execute(
            "INSERT INTO jobs (company_id, job_title, job_type, salary_min, salary_max, "
            "job_url, date_posted, requirements) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (data["company_id"], data["job_title"], data["job_type"], data["salary_min"],
             data["salary_max"], data["job_url"], data["date_posted"], data["requirements"]),
        )
        flash(f"Added {data['job_title']}.", "success")
        return redirect(url_for("job_detail", job_id=new_id))

    # the "Add job" link on a company page passes ?company_id= so it's already selected
    job = {"company_id": request.args.get("company_id")}
    return render_template("job_form.html", job=job, mode="add", companies=company_list())


@app.route("/jobs/<int:job_id>/edit", methods=["GET", "POST"])
def edit_job(job_id):
    job = get_job(job_id)

    if request.method == "POST":
        data, errors = validate_job(request.form)
        data["job_id"] = job_id
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("job_form.html", job=data, mode="edit", companies=company_list())

        execute(
            "UPDATE jobs SET company_id = %s, job_title = %s, job_type = %s, salary_min = %s, "
            "salary_max = %s, job_url = %s, date_posted = %s, requirements = %s WHERE job_id = %s",
            (data["company_id"], data["job_title"], data["job_type"], data["salary_min"],
             data["salary_max"], data["job_url"], data["date_posted"], data["requirements"], job_id),
        )
        flash(f"Saved changes to {data['job_title']}.", "success")
        return redirect(url_for("job_detail", job_id=job_id))

    job["skills_text"] = ", ".join(job["skills"])
    return render_template("job_form.html", job=job, mode="edit", companies=company_list())


@app.route("/jobs/<int:job_id>/delete", methods=["POST"])
def delete_job(job_id):
    job = get_job(job_id)
    execute("DELETE FROM jobs WHERE job_id = %s", (job_id,))
    flash(f"Deleted {job['job_title']} ({job['company_name']}).", "success")
    return redirect(url_for("jobs"))


# ---------- applications ----------

def job_list():
    return query(
        """
        SELECT j.job_id, j.job_title, c.company_name
        FROM jobs j
        JOIN companies c ON c.company_id = j.company_id
        ORDER BY c.company_name, j.job_title
        """
    )


def validate_application(form):
    errors = []
    data = {
        "job_id": clean(form.get("job_id")),
        "status": clean(form.get("status")) or "Applied",
        "resume_version": clean(form.get("resume_version")),
        "cover_letter_sent": form.get("cover_letter_sent") == "on",
    }

    if not data["job_id"]:
        errors.append("Pick a job.")
    elif not query("SELECT 1 FROM jobs WHERE job_id = %s", (data["job_id"],), one=True):
        errors.append("That job doesn't exist.")

    application_date = clean(form.get("application_date"))
    if not application_date:
        errors.append("Application date is required.")
    data["application_date"] = parse_date(errors, "Application date", application_date,
                                          allow_future=False)

    if data["status"] not in STATUSES:
        errors.append("Pick a valid status.")
    check_length(errors, "Resume version", data["resume_version"], 50)

    # interview info is saved together as one JSON object
    interview = {
        "interview_date": clean(form.get("interview_date")),
        "interview_type": clean(form.get("interview_type")),
        "interviewer": clean(form.get("interviewer")),
        "notes": clean(form.get("notes")),
    }
    interview_date = parse_date(errors, "Interview date", interview["interview_date"])
    if interview_date and data["application_date"] and interview_date < data["application_date"]:
        errors.append("Interview date can't be before the application date.")
    check_length(errors, "Interview type", interview["interview_type"], 50)
    check_length(errors, "Interviewer", interview["interviewer"], 100)

    data["interview"] = interview
    filled_in = {}
    for key, value in interview.items():
        if value:
            filled_in[key] = value
    if filled_in:
        data["interview_data"] = json.dumps(filled_in)
    else:
        data["interview_data"] = None

    return data, errors


def get_application(application_id):
    application = query(
        """
        SELECT a.*, j.job_title, j.job_url, j.company_id, c.company_name
        FROM applications a
        JOIN jobs j ON j.job_id = a.job_id
        JOIN companies c ON c.company_id = j.company_id
        WHERE a.application_id = %s
        """,
        (application_id,),
        one=True,
    )
    if application is None:
        abort(404)
    application["interview"] = load_json(application["interview_data"], {})
    return application


@app.route("/applications")
def applications():
    status = clean(request.args.get("status"))

    sql = """
        SELECT a.*, j.job_title, c.company_name,
               JSON_UNQUOTE(JSON_EXTRACT(a.interview_data, '$.interview_date')) AS interview_date
        FROM applications a
        JOIN jobs j ON j.job_id = a.job_id
        JOIN companies c ON c.company_id = j.company_id
    """
    params = []
    if status in STATUSES:
        sql += " WHERE a.status = %s"
        params.append(status)
    sql += " ORDER BY a.application_date DESC"

    return render_template("applications.html", applications=query(sql, params), status=status or "")


@app.route("/applications/board")
def applications_board():
    rows = query(
        """
        SELECT a.application_id, a.application_date, a.status, j.job_title, c.company_name
        FROM applications a
        JOIN jobs j ON j.job_id = a.job_id
        JOIN companies c ON c.company_id = j.company_id
        ORDER BY a.application_date DESC
        """
    )
    # one list of cards per status column
    columns = {}
    for status in STATUSES:
        columns[status] = []
    for row in rows:
        columns[row["status"]].append(row)
    return render_template("applications_board.html", columns=columns)


@app.route("/applications/<int:application_id>/status", methods=["POST"])
def move_application(application_id):
    # called by the board when a card gets dragged to another column
    application = get_application(application_id)
    new_status = (request.get_json(silent=True) or {}).get("status")
    if new_status not in STATUSES:
        return jsonify({"error": "Invalid status"}), 400

    execute("UPDATE applications SET status = %s WHERE application_id = %s",
            (new_status, application_id))
    celebrate = new_status in CELEBRATE and new_status != application["status"]
    return jsonify({"status": new_status, "celebrate": celebrate})


@app.route("/applications/<int:application_id>")
def application_detail(application_id):
    return render_template("application_detail.html", application=get_application(application_id))


@app.route("/applications/add", methods=["GET", "POST"])
def add_application():
    if request.method == "POST":
        data, errors = validate_application(request.form)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("application_form.html", application=data, mode="add", jobs=job_list())

        new_id = execute(
            "INSERT INTO applications (job_id, application_date, status, resume_version, "
            "cover_letter_sent, interview_data) VALUES (%s, %s, %s, %s, %s, %s)",
            (data["job_id"], data["application_date"], data["status"], data["resume_version"],
             data["cover_letter_sent"], data["interview_data"]),
        )
        flash("Application added.", "success")
        if data["status"] in CELEBRATE:
            session["confetti"] = True
        return redirect(url_for("application_detail", application_id=new_id))

    # default to today, and preselect the job if we came from a job page
    application = {
        "job_id": request.args.get("job_id"),
        "application_date": date.today().isoformat(),
        "status": "Applied",
        "interview": {},
    }
    return render_template("application_form.html", application=application, mode="add", jobs=job_list())


@app.route("/applications/<int:application_id>/edit", methods=["GET", "POST"])
def edit_application(application_id):
    application = get_application(application_id)

    if request.method == "POST":
        data, errors = validate_application(request.form)
        data["application_id"] = application_id
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("application_form.html", application=data, mode="edit", jobs=job_list())

        execute(
            "UPDATE applications SET job_id = %s, application_date = %s, status = %s, "
            "resume_version = %s, cover_letter_sent = %s, interview_data = %s "
            "WHERE application_id = %s",
            (data["job_id"], data["application_date"], data["status"], data["resume_version"],
             data["cover_letter_sent"], data["interview_data"], application_id),
        )
        flash("Application updated.", "success")
        # only celebrate when the status actually moves up to Interview or Offer
        if data["status"] in CELEBRATE and data["status"] != application["status"]:
            session["confetti"] = True
        return redirect(url_for("application_detail", application_id=application_id))

    return render_template("application_form.html", application=application, mode="edit", jobs=job_list())


@app.route("/applications/<int:application_id>/delete", methods=["POST"])
def delete_application(application_id):
    application = get_application(application_id)
    execute("DELETE FROM applications WHERE application_id = %s", (application_id,))
    flash(f"Deleted the application for {application['job_title']}.", "success")
    return redirect(url_for("applications"))


# ---------- contacts ----------

def validate_contact(form):
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
        errors.append("Pick a company.")
    elif not query("SELECT 1 FROM companies WHERE company_id = %s", (data["company_id"],), one=True):
        errors.append("That company doesn't exist.")

    if not data["contact_name"]:
        errors.append("Name is required.")
    check_length(errors, "Name", data["contact_name"], 100)
    check_length(errors, "Title", data["title"], 100)

    email = data["email"]
    check_length(errors, "Email", email, 100)
    if email and (email.count("@") != 1 or "." not in email.split("@")[1] or " " in email):
        errors.append("That email doesn't look right.")

    phone = data["phone"]
    check_length(errors, "Phone", phone, 20)
    if phone:
        digits = 0
        for ch in phone:
            if ch.isdigit():
                digits += 1
        if digits < 7 or digits > 15:
            errors.append("Phone number should have 7 to 15 digits.")

    check_length(errors, "LinkedIn URL", data["linkedin_url"], 200)
    check_url(errors, "LinkedIn URL", data["linkedin_url"])
    if data["linkedin_url"] and "linkedin.com" not in data["linkedin_url"].lower():
        errors.append("LinkedIn URL should be a linkedin.com link.")

    return data, errors


def get_contact(contact_id):
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
    """
    conditions = []
    params = []
    if search:
        conditions.append("(k.contact_name LIKE %s OR k.title LIKE %s OR k.email LIKE %s)")
        params += ["%" + search + "%"] * 3
    if company_id and company_id.isdigit():
        conditions.append("k.company_id = %s")
        params.append(company_id)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY k.contact_name"

    return render_template("contacts.html", contacts=query(sql, params), companies=company_list(),
                           search=search or "", company_id=company_id or "")


@app.route("/contacts/<int:contact_id>")
def contact_detail(contact_id):
    return render_template("contact_detail.html", contact=get_contact(contact_id))


@app.route("/contacts/add", methods=["GET", "POST"])
def add_contact():
    if request.method == "POST":
        data, errors = validate_contact(request.form)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("contact_form.html", contact=data, mode="add", companies=company_list())

        new_id = execute(
            "INSERT INTO contacts (company_id, contact_name, title, email, phone, linkedin_url, notes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (data["company_id"], data["contact_name"], data["title"], data["email"],
             data["phone"], data["linkedin_url"], data["notes"]),
        )
        flash(f"Added {data['contact_name']}.", "success")
        return redirect(url_for("contact_detail", contact_id=new_id))

    contact = {"company_id": request.args.get("company_id")}
    return render_template("contact_form.html", contact=contact, mode="add", companies=company_list())


@app.route("/contacts/<int:contact_id>/edit", methods=["GET", "POST"])
def edit_contact(contact_id):
    contact = get_contact(contact_id)

    if request.method == "POST":
        data, errors = validate_contact(request.form)
        data["contact_id"] = contact_id
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("contact_form.html", contact=data, mode="edit", companies=company_list())

        execute(
            "UPDATE contacts SET company_id = %s, contact_name = %s, title = %s, email = %s, "
            "phone = %s, linkedin_url = %s, notes = %s WHERE contact_id = %s",
            (data["company_id"], data["contact_name"], data["title"], data["email"],
             data["phone"], data["linkedin_url"], data["notes"], contact_id),
        )
        flash(f"Saved changes to {data['contact_name']}.", "success")
        return redirect(url_for("contact_detail", contact_id=contact_id))

    return render_template("contact_form.html", contact=contact, mode="edit", companies=company_list())


@app.route("/contacts/<int:contact_id>/delete", methods=["POST"])
def delete_contact(contact_id):
    contact = get_contact(contact_id)
    execute("DELETE FROM contacts WHERE contact_id = %s", (contact_id,))
    flash(f"Deleted {contact['contact_name']}.", "success")
    return redirect(url_for("contacts"))


# ---------- job match ----------

def match_jobs(my_skills, jobs):
    # match % = how many of the job's skills I have / how many it asks for
    have = [s.lower() for s in my_skills]
    results = []

    for job in jobs:
        if not job["skills"]:
            continue

        matched = []
        missing = []
        for skill in job["skills"]:
            if skill.lower() in have:
                matched.append(skill)
            else:
                missing.append(skill)

        results.append({
            "job": job,
            "matched": matched,
            "missing": missing,
            "total": len(job["skills"]),
            "percent": percent(len(matched), len(job["skills"])),
        })

    results.sort(key=lambda r: r["percent"], reverse=True)
    return results


@app.route("/job-match")
def job_match():
    # skills come from the buttons you click plus anything typed in the box
    picked = request.args.getlist("skill")
    skills_text = request.args.get("skills", "")
    my_skills = parse_skills(", ".join(picked + [skills_text]))
    show_all = request.args.get("show_all") == "on"

    jobs = add_skills(query(
        """
        SELECT j.job_id, j.job_title, j.requirements, c.company_name,
               (SELECT a.status FROM applications a WHERE a.job_id = j.job_id LIMIT 1) AS applied_status
        FROM jobs j
        JOIN companies c ON c.company_id = j.company_id
        """
    ))

    # every skill from my saved jobs, for the buttons
    skill_options = []
    for job in jobs:
        for skill in job["skills"]:
            if skill.lower() not in [s.lower() for s in skill_options]:
                skill_options.append(skill)
    skill_options.sort(key=str.lower)

    results = []
    if my_skills:
        results = match_jobs(my_skills, jobs)
        if not show_all:
            results = [r for r in results if r["percent"] > 0]

    return render_template("job_match.html", skills_text=skills_text, my_skills=my_skills,
                           picked=[s.lower() for s in picked], skill_options=skill_options,
                           show_all=show_all, results=results)


# ---------- errors ----------

@app.errorhandler(mysql.connector.Error)
def database_error(error):
    return render_template("error.html", error=error), 500


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", error=None, not_found=True), 404


if __name__ == "__main__":
    app.run(debug=True)
