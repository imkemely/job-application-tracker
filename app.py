"""Job Application Tracker - Flask application."""
import os

import mysql.connector
from flask import Flask, render_template

from database import query

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")


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
