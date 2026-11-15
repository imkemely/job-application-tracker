-- ============================================================
-- Job Application Tracker - database schema
-- COP 4751 Course Project
--
-- Run this whole file in MySQL Workbench (or the mysql CLI)
-- to create the job_tracker database from scratch.
-- WARNING: it drops and recreates the four tables, so any
-- existing data in them will be replaced with the sample data.
-- ============================================================

CREATE DATABASE IF NOT EXISTS job_tracker
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE job_tracker;

-- Drop in reverse dependency order so foreign keys don't block us
DROP TABLE IF EXISTS applications;
DROP TABLE IF EXISTS contacts;
DROP TABLE IF EXISTS jobs;
DROP TABLE IF EXISTS companies;

-- ------------------------------------------------------------
-- companies: every job and contact belongs to a company
-- ------------------------------------------------------------
CREATE TABLE companies (
    company_id    INT AUTO_INCREMENT PRIMARY KEY,
    company_name  VARCHAR(100) NOT NULL,
    industry      VARCHAR(50),
    website       VARCHAR(200),
    city          VARCHAR(50),
    state         VARCHAR(50),
    notes         TEXT
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- jobs: a posting at a company
-- requirements is a JSON array of skills, e.g. ["Python", "SQL"]
-- (the Job Match page compares your skills against this list)
-- ------------------------------------------------------------
CREATE TABLE jobs (
    job_id        INT AUTO_INCREMENT PRIMARY KEY,
    company_id    INT NOT NULL,
    job_title     VARCHAR(100) NOT NULL,
    job_type      ENUM('Full-time', 'Part-time', 'Contract', 'Internship'),
    salary_min    INT,
    salary_max    INT,
    job_url       VARCHAR(300),
    date_posted   DATE,
    requirements  JSON,
    CONSTRAINT fk_jobs_company
        FOREIGN KEY (company_id) REFERENCES companies (company_id)
        ON DELETE CASCADE,
    CONSTRAINT chk_salary_range
        CHECK (salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- applications: one application to one job
-- interview_data is a JSON object with interview details,
-- e.g. {"interview_date": "...", "interview_type": "...", ...}
-- ------------------------------------------------------------
CREATE TABLE applications (
    application_id     INT AUTO_INCREMENT PRIMARY KEY,
    job_id             INT NOT NULL,
    application_date   DATE NOT NULL,
    status             ENUM('Applied', 'Screening', 'Interview', 'Offer', 'Rejected', 'Withdrawn')
                       DEFAULT 'Applied',
    resume_version     VARCHAR(50),
    cover_letter_sent  BOOLEAN DEFAULT FALSE,
    interview_data     JSON,
    CONSTRAINT fk_applications_job
        FOREIGN KEY (job_id) REFERENCES jobs (job_id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- contacts: people you know at a company (recruiters, etc.)
-- ------------------------------------------------------------
CREATE TABLE contacts (
    contact_id    INT AUTO_INCREMENT PRIMARY KEY,
    company_id    INT NOT NULL,
    contact_name  VARCHAR(100) NOT NULL,
    title         VARCHAR(100),
    email         VARCHAR(100),
    phone         VARCHAR(20),
    linkedin_url  VARCHAR(200),
    notes         TEXT,
    CONSTRAINT fk_contacts_company
        FOREIGN KEY (company_id) REFERENCES companies (company_id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================
-- Sample data
-- ============================================================

INSERT INTO companies (company_name, industry, website, city, state, notes) VALUES
('Brightwave Technologies', 'Software',   'https://www.brightwave.example.com',  'Miami',         'FL', 'Mid-size SaaS company, hybrid schedule.'),
('Coral Data Labs',         'Analytics',  'https://www.coraldatalabs.example.com', 'Fort Lauderdale', 'FL', 'Met their recruiter at the FIU career fair.'),
('Sunline Financial',       'Finance',    'https://www.sunlinefinancial.example.com', 'Miami',      'FL', 'Big on Salesforce and cloud.'),
('Everglade Health Systems','Healthcare', 'https://www.evergladehealth.example.com', 'Doral',     'FL', NULL),
('Nimbus Cloud Co.',        'Cloud',      'https://www.nimbuscloud.example.com', 'Austin',        'TX', 'Fully remote option for new grads.'),
('Palmetto Logistics',      'Logistics',  'https://www.palmettologistics.example.com', 'Orlando', 'FL', 'Internal tools team is growing.');

INSERT INTO jobs (company_id, job_title, job_type, salary_min, salary_max, job_url, date_posted, requirements) VALUES
(1, 'Software Developer',         'Full-time',  75000,  90000, 'https://www.brightwave.example.com/careers/101',  '2026-09-15', '["Python", "SQL", "Flask"]'),
(1, 'Frontend Engineer',          'Full-time',  72000,  88000, 'https://www.brightwave.example.com/careers/102',  '2026-10-01', '["JavaScript", "React", "HTML", "CSS"]'),
(2, 'Data Analyst',               'Full-time',  65000,  78000, 'https://www.coraldatalabs.example.com/jobs/7',    '2026-09-20', '["Python", "SQL", "Tableau"]'),
(2, 'Data Engineering Intern',    'Internship', 25000,  30000, 'https://www.coraldatalabs.example.com/jobs/9',    '2026-10-10', '["Python", "SQL", "AWS", "Spark"]'),
(3, 'Salesforce Developer',       'Full-time',  80000,  95000, 'https://www.sunlinefinancial.example.com/jobs/44','2026-09-28', '["Salesforce", "Apex", "SQL", "JavaScript"]'),
(3, 'Cloud Engineer',             'Contract',   90000, 110000, 'https://www.sunlinefinancial.example.com/jobs/51','2026-10-18', '["AWS", "Python", "Linux", "Docker"]'),
(4, 'Database Administrator',     'Full-time',  70000,  85000, 'https://www.evergladehealth.example.com/careers/12','2026-10-05', '["MySQL", "SQL", "Linux", "Backup and Recovery"]'),
(5, 'Backend Engineer (New Grad)','Full-time',  95000, 115000, 'https://www.nimbuscloud.example.com/jobs/2001',   '2026-10-22', '["Java", "Spring Boot", "SQL", "AWS"]'),
(5, 'DevOps Engineer',            'Full-time', 100000, 120000, 'https://www.nimbuscloud.example.com/jobs/2005',   '2026-11-02', '["AWS", "Docker", "Kubernetes", "Linux", "Python"]'),
(6, 'Junior Python Developer',    'Part-time',  30000,  40000, 'https://www.palmettologistics.example.com/jobs/3','2026-11-05', '["Python", "Flask", "HTML", "CSS"]');

INSERT INTO applications (job_id, application_date, status, resume_version, cover_letter_sent, interview_data) VALUES
(1, '2026-09-18', 'Interview', 'v3-software', TRUE,
    '{"interview_date": "2026-10-02", "interview_type": "Technical", "interviewer": "Daniel Reyes", "notes": "Live coding with Python and a SQL JOIN question."}'),
(3, '2026-09-22', 'Screening', 'v2-data',     TRUE,
    '{"interview_date": "2026-10-06", "interview_type": "Phone Screen", "interviewer": "Ana Torres", "notes": "Asked about my Tableau experience."}'),
(5, '2026-09-30', 'Offer',     'v3-software', TRUE,
    '{"interview_date": "2026-10-14", "interview_type": "Final Round", "interviewer": "Marcus Lee", "notes": "Panel interview, went well. Offer received 10/24."}'),
(2, '2026-10-03', 'Rejected',  'v3-software', FALSE, NULL),
(4, '2026-10-12', 'Applied',   'v2-data',     FALSE, NULL),
(7, '2026-10-08', 'Withdrawn', 'v1-general',  FALSE, NULL),
(8, '2026-10-25', 'Interview', 'v3-software', TRUE,
    '{"interview_date": "2026-11-10", "interview_type": "Video", "interviewer": "Priya Shah", "notes": "Behavioral questions plus a Spring Boot system design discussion."}'),
(10, '2026-11-06', 'Applied',  'v3-software', TRUE,  NULL);

INSERT INTO contacts (company_id, contact_name, title, email, phone, linkedin_url, notes) VALUES
(1, 'Daniel Reyes', 'Engineering Manager',   'daniel.reyes@brightwave.example.com',   '305-555-0142', 'https://www.linkedin.com/in/example-daniel-reyes', 'Ran my technical interview.'),
(2, 'Ana Torres',   'Technical Recruiter',   'ana.torres@coraldatalabs.example.com',  '954-555-0187', 'https://www.linkedin.com/in/example-ana-torres',   'Met at the FIU career fair.'),
(3, 'Marcus Lee',   'Salesforce Team Lead',  'marcus.lee@sunlinefinancial.example.com','305-555-0119', NULL, 'Sent a thank-you email after the final round.'),
(4, 'Jasmine Cruz', 'HR Coordinator',        'jasmine.cruz@evergladehealth.example.com', '786-555-0164', NULL, NULL),
(5, 'Priya Shah',   'Senior Software Engineer','priya.shah@nimbuscloud.example.com',  NULL,           'https://www.linkedin.com/in/example-priya-shah',   'Referred me for the new grad role.'),
(6, 'Tom Becker',   'IT Director',           'tom.becker@palmettologistics.example.com', '407-555-0133', NULL, 'Prefers email over phone.');
