-- Job Application Tracker - COP 4751 course project
-- Creates the job_tracker database and loads my real job search data.
-- Running this drops and recreates the four tables.

CREATE DATABASE IF NOT EXISTS job_tracker
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE job_tracker;

-- drop children first because of the foreign keys
DROP TABLE IF EXISTS applications;
DROP TABLE IF EXISTS contacts;
DROP TABLE IF EXISTS jobs;
DROP TABLE IF EXISTS companies;

CREATE TABLE companies (
    company_id    INT AUTO_INCREMENT PRIMARY KEY,
    company_name  VARCHAR(100) NOT NULL,
    industry      VARCHAR(50),
    website       VARCHAR(200),
    city          VARCHAR(50),
    state         VARCHAR(50),
    notes         TEXT
) ENGINE=InnoDB;

-- requirements = JSON list of skills, used by the Job Match page
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

-- interview_data = JSON object: interview_date, interview_type, interviewer, notes
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


-- ------------------------------------------------------------
-- Data from my job search (as of Nov 2026)
-- Contacts use initials only since this repo is public.
-- ------------------------------------------------------------

INSERT INTO companies (company_name, industry, website, city, state, notes) VALUES
('Microsoft',               'Software',            'https://www.microsoft.com',          'Redmond',       'WA', 'Applied to a TPM II role. Check my candidate profile to confirm which posting I submitted for.'),
('Pinterest',               'Social Media',        'https://www.pinterest.com',          'San Francisco', 'CA', 'Remote TPM role on the infrastructure team.'),
('The Home Depot',          'Retail',              'https://www.homedepot.com',          'Atlanta',       'GA', 'Two remote PM roles. An online assessment may follow for the Project Manager one.'),
('Anthropic',               'Artificial Intelligence', 'https://www.anthropic.com',      'San Francisco', 'CA', 'Senior role, long shot. Application materials are ready.'),
('Palantir Technologies',   'Software',            'https://www.palantir.com',           'Denver',        'CO', 'TPM role requires willingness to get a Secret clearance.'),
('Wasabi Technologies',     'Cloud Storage',       'https://wasabi.com',                 'Boston',        'MA', 'Looking for Agile and Jira experience.'),
('Smartleaf',               'Fintech',             'https://www.smartleaf.com',          'Boston',        'MA', 'Remote with some travel to Boston. Found on LinkedIn.'),
('Vetcove',                 'Veterinary Tech',     'https://www.vetcove.com',            NULL,            NULL, 'Found on LinkedIn.'),
('American Express',        'Financial Services',  'https://www.americanexpress.com',    'New York',      'NY', 'Summer 2026 internship program in Phoenix, AZ.'),
('Boats Group',             'Online Marketplace',  'https://www.boatsgroup.com',         'Miami',         'FL', '2026 summer internship program.'),
('Royal Caribbean Group',   'Travel & Hospitality','https://www.royalcaribbeangroup.com','Miami',         'FL', 'Tech internships based in Miami.'),
('Netflix',                 'Entertainment',       'https://www.netflix.com',            'Los Gatos',     'CA', '2026 summer internship program.'),
('CORSAIR',                 'Consumer Electronics','https://www.corsair.com',            'Fremont',       'CA', NULL),
('UKG',                     'HR Software',         'https://www.ukg.com',                'Weston',        'FL', 'Break Through Tech Miami Sprinternship. Built an AI-powered skills assessment platform.'),
('OneUnited Bank',          'Banking',             'https://www.oneunited.com',          'Boston',        'MA', 'Salesforce and Apex development internship.'),
('Oracle',                  'Cloud',               'https://www.oracle.com',             'Austin',        'TX', 'Skipped the Principal TPM role, too senior for now.'),
('Insurance company (via recruiter)', 'Insurance', NULL,                                 'Miami',         'FL', '12-month hybrid contract role. A recruiter reached out in Mar 2025.');

INSERT INTO jobs (company_id, job_title, job_type, salary_min, salary_max, job_url, date_posted, requirements) VALUES
(1,  'Technical Program Manager II (IC3)', 'Full-time', 102100, 202200,
     'https://apply.careers.microsoft.com/careers/job/1970393557044302', NULL,
     '["Program Management", "Capacity Planning", "Cloud Computing", "Azure", "Financial Modeling", "Data Analysis"]'),
(2,  'Technical Program Manager II, Infrastructure Capacity & Efficiency', 'Full-time', 103965, 214044,
     'https://www.pinterestcareers.com/jobs/8209324/technical-program-manager-ii-infrastructure-capacity-efficiency/', NULL,
     '["Program Management", "AWS", "Capacity Planning", "SQL", "Tableau", "Data Analysis"]'),
(3,  'Project Manager (Remote)', 'Full-time', 80000, 160000,
     'https://careers.homedepot.com/job/24115397/project-manager-remote-remote/', NULL,
     '["Project Management", "Agile", "Budgeting", "Stakeholder Management", "Microsoft Office"]'),
(3,  'IT Project Manager, Orange Apron Media (Remote)', 'Full-time', 65000, 180000,
     'https://careers.homedepot.com/job/23915306/it-project-manager-orange-apron-media-remote-remote/', NULL,
     '["Project Management", "Agile", "Waterfall", "Tableau", "Budgeting", "Risk Management"]'),
(4,  'Technical Program Manager, Apps Platform', 'Full-time', 365000, 435000,
     'https://job-boards.greenhouse.io/anthropic/jobs/5251609008', '2026-06-09',
     '["Program Management", "Roadmap Planning", "Platform Engineering", "Stakeholder Management", "Technical Documentation"]'),
(5,  'Technical Program Manager', 'Full-time', 93000, 160000, NULL, NULL,
     '["Program Management", "Stakeholder Management", "Data Analysis", "SQL", "Security Clearance"]'),
(6,  'Technical Program Manager', 'Full-time', 120000, 140000,
     'https://job-boards.greenhouse.io/wasabi/jobs/5454019008', NULL,
     '["Program Management", "Agile", "Jira", "Cloud Storage", "Risk Management"]'),
(7,  'Technical Product Manager', 'Full-time', 100000, 120000, NULL, NULL,
     '["Product Management", "Agile", "Jira", "SQL", "Requirements Gathering"]'),
(8,  'Associate Product Manager', 'Full-time', 70000, 110000, NULL, NULL,
     '["Product Management", "Data Analysis", "SQL", "User Research", "Jira"]'),
(9,  'Software Engineer Intern, Campus Graduate Summer Internship', 'Internship', NULL, NULL, NULL, NULL,
     '["Java", "JavaScript", "React", "AWS", "SQL", "Git"]'),
(10, 'Software Development Intern, 2026 Summer Internship', 'Internship', NULL, NULL, NULL, NULL,
     '["JavaScript", "Python", "React", "SQL", "Git"]'),
(11, 'Software Engineering Intern', 'Internship', NULL, NULL, NULL, NULL,
     '["Java", "JavaScript", "SQL", "Git", "Agile"]'),
(12, 'Software Engineering Intern, 2026 Summer Internship', 'Internship', NULL, NULL, NULL, NULL,
     '["Java", "Python", "Algorithms", "Distributed Systems", "Git"]'),
(13, 'Web Design Intern', 'Internship', NULL, NULL, NULL, NULL,
     '["HTML", "CSS", "JavaScript", "Figma", "Adobe Photoshop"]'),
(14, 'Software Engineer Intern', 'Internship', NULL, NULL, NULL, NULL,
     '["Java", "Spring Boot", "Next.js", "SQL", "Git"]'),
(15, 'Full-Stack Engineer Intern', 'Internship', NULL, NULL, NULL, NULL,
     '["Salesforce", "Apex", "JavaScript", "SQL"]'),
(16, 'Principal Technical Program Manager (OCI)', 'Full-time', NULL, NULL, NULL, NULL,
     '["Program Management", "Oracle Cloud Infrastructure", "Cloud Computing", "Stakeholder Management"]');

-- Jobs 4 (Home Depot IT PM), 5 (Anthropic) and 17 (Oracle) are saved but have no application yet.
INSERT INTO applications (job_id, application_date, status, resume_version, cover_letter_sent, interview_data) VALUES
(1,  '2026-10-20', 'Applied',  'TPM-resume', FALSE, NULL),
(2,  '2026-11-06', 'Applied',  'TPM-resume', FALSE, NULL),
(3,  '2026-11-12', 'Applied',  'TPM-resume', FALSE, NULL),
(6,  '2026-10-08', 'Rejected', 'TPM-resume', FALSE, NULL),
(7,  '2026-10-15', 'Rejected', 'TPM-resume', FALSE, NULL),
(8,  '2026-10-28', 'Applied',  'TPM-resume', FALSE, NULL),
(9,  '2026-10-30', 'Applied',  'TPM-resume', FALSE, NULL),
(10, '2025-11-20', 'Rejected', 'SWE-resume', FALSE,
     '{"interview_date": "2026-01-23", "interview_type": "Final Round", "notes": "Behavioral and technical interview with a full-stack cloud engineering team. Did the HireVue in Dec 2025."}'),
(11, '2025-12-10', 'Rejected', 'SWE-resume', FALSE,
     '{"interview_date": "2026-01-15", "interview_type": "Phone Screen", "notes": "Recruiter screening call."}'),
(12, '2025-09-25', 'Rejected', 'SWE-resume', FALSE,
     '{"interview_date": "2025-10-17", "interview_type": "Interview", "notes": "Followed up with the recruiter in Nov 2025."}'),
(13, '2025-10-20', 'Applied',  'SWE-resume', FALSE, NULL),
(14, '2025-02-15', 'Rejected', 'SWE-resume', FALSE, NULL),
(15, '2025-03-10', 'Offer',    'SWE-resume', FALSE, NULL),
(16, '2025-01-20', 'Offer',    'SWE-resume', FALSE, NULL);

INSERT INTO contacts (company_id, contact_name, title, email, phone, linkedin_url, notes) VALUES
(9,  'Leai C.',     'Recruiter',                                         NULL, NULL, NULL, 'Recruiter for the SWE internship.'),
(10, 'Michele A.',  'Recruiter',                                         NULL, NULL, NULL, 'Set up the screening call.'),
(11, 'Nicole F.',   'Lead Talent Acquisition Partner, Early Career',     NULL, NULL, NULL, 'Followed up with her after my interview.'),
(13, 'Hector Z.',   'Senior Web Designer',                               NULL, NULL, NULL, 'Sent a thank-you email after hearing back.'),
(17, 'Hayden W.',   'Recruiter',                                         NULL, NULL, NULL, 'Reached out about the contract role. I replied that I was interested.');
