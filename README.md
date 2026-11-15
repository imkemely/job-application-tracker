# Alfonso's Job Tracker

COP 4751 (Advanced Database Management) course project, Fall 2026.

A web app for keeping track of my job search: the companies I'm looking at, the jobs I've saved, the applications I've sent, and the people I've talked to. It's built with MySQL, Python/Flask, and HTML/CSS (Bootstrap).

The data in `schema.sql` is my actual job search from this semester. Contacts only use first name + last initial since this repo is public.

## Features

- **Dashboard** with counts for every table, applications by status, response rate, recent applications, interviews, the skills that come up most, and a weekly goal (10 applications a week)
- **Companies, Jobs, Applications, Contacts** each have a list page, a detail page, add/edit forms with validation, and delete with a confirmation
- **Board view** for applications (like a GitHub project board). Drag a card to another column to change its status
- **Job Match**: pick your skills (or type them) and every saved job gets ranked by match % with the skills you have and the ones you're missing
- Search/filter on the Jobs, Applications and Contacts pages
- Confetti when an application moves to Interview or Offer

## Tech

- MySQL 8
- Python 3 + Flask
- mysql-connector-python
- HTML, CSS, Bootstrap 5
- python-dotenv (keeps the database password out of the code)

## Setup

These steps are for Windows (PowerShell). Mac/Linux commands are in parentheses where they're different.

**You need:** Python 3.10+, MySQL 8 running locally, and Git.

1. **Clone the repo**
   ```
   git clone https://github.com/imkemely/job-application-tracker.git
   cd job-application-tracker
   ```

2. **Create a virtual environment and install the packages**
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
   (Mac/Linux: `python3 -m venv venv` and `source venv/bin/activate`)

3. **Create the database**

   Open `schema.sql` in MySQL Workbench and run the whole file (the lightning bolt button), or from a terminal:
   ```
   mysql -u root -p < schema.sql
   ```
   This creates the `job_tracker` database with the 4 tables and loads the data.

4. **Add your MySQL login**
   ```
   copy .env.example .env
   ```
   (Mac/Linux: `cp .env.example .env`)

   Open `.env` and put your MySQL root password after `DB_PASSWORD=`. Leave it empty if root has no password. `.env` is in `.gitignore`, so it never gets pushed.

5. **Run the app**
   ```
   python app.py
   ```
   Then go to **http://127.0.0.1:5000**

### If something goes wrong

- **"Access denied for user 'root'"**: the password in `.env` is wrong or missing.
- **"Can't connect to MySQL server"**: make sure MySQL is running. You can also try `DB_HOST=127.0.0.1` in `.env`.
- **"Unknown database 'job_tracker'"**: run `schema.sql` first (step 3).

## Database

| Table | What it stores | Links to |
|---|---|---|
| `companies` | name, industry, website, location, notes | |
| `jobs` | title, type, salary range, posting link, date posted, `requirements` (JSON list of skills) | `companies` |
| `applications` | date applied, status, resume version, cover letter, `interview_data` (JSON object) | `jobs` |
| `contacts` | name, title, email, phone, LinkedIn, notes | `companies` |

- All three foreign keys use `ON DELETE CASCADE`, so deleting a company also deletes its jobs, their applications, and its contacts.
- There's a `CHECK` constraint so `salary_min` can't be bigger than `salary_max`.
- `requirements` is used by Job Match and the "skills that come up the most" list on the dashboard.
- `interview_data` holds the interview date, type, interviewer and notes, and the dashboard reads the interview dates out of it with `JSON_EXTRACT`.

## Project structure

```
job-application-tracker/
├── app.py              # Flask routes (dashboard, CRUD for all 4 tables, board, job match)
├── database.py         # MySQL connection + query helpers
├── schema.sql          # creates the database and loads the data
├── requirements.txt
├── .env.example        # copy to .env and add your password
├── templates/          # HTML pages (base.html is the shared layout)
├── static/style.css    # my colors and spacing on top of Bootstrap
├── AI_USAGE.md         # how I used AI on this project
└── README.md
```

## Demo video

`demo.mp4` in this repo shows the app running (browser), the Flask server (terminal), and the database changing in MySQL Workbench.

## AI usage

I used AI while building this project. The details are in [AI_USAGE.md](AI_USAGE.md).

Built by Kemely Alfonso
