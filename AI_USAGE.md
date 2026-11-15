# AI Usage Documentation

## Tools Used

- **Claude (Anthropic)**: I used it as a step-by-step help for the project. It helped me plan the steps, helped me write some of the Flask and HTML code, explained things I didn't understand, helped me debug errors on my computer.

I worked in VS Code and MySQL Workbench and did all the setup, running, testing and Git commits on my own computer. I told Claude not to change anything without asking me first, so I approved each step before it was built.

## Key Prompts

These are some of the main things I asked (mostly in my own words):

1. "Explain the project to me." I used this first to understand the spec, the 4 tables and the rubric.
2. "Help me build it, but don't do anything without asking me first." This set up the step-by-step plan: database, Flask setup, CRUD one table at a time, dashboard, Job Match, then docs.
3. "Should it have a section similar to the board in GitHub used to track sprints?"
4. "How would I add a job or application that's not in the dropdown?"
5. "Double check that everything meets all of the requirements before I push."

## What Worked Well

- **Building in small steps.** Getting full CRUD working for one table (companies) first and then repeating the pattern for jobs, applications and contacts made it easier to follow, and I could commit after each step.
- **Debugging.** When my app showed a database error, it turned out my MySQL root user had a password. Putting it in the `.env` file fixed it. It also helped when PowerShell didn't understand `%USERPROFILE%` (that's Command Prompt syntax) and when `tar` kept unzipping an old download because Windows had renamed the new ones to `(1)`, `(2)`, etc.
- **Explanations.** It explained foreign keys and `ON DELETE CASCADE`, why delete has to be a POST request, how the JSON columns are saved and read back, and why the forms only let you pick a company or job that already exists.
- **Testing.** Before each step it ran the code against a test database, including a test where it set the project up from a fresh copy to make sure it works for someone cloning the repo.

## What I Modified / Decided Myself

- **Used my real job search as the data** instead of made-up sample companies. I gave it my list of applications (companies, roles, pay ranges, statuses, recruiters). Because the repo is public, I only used initials for contacts and left out personal notes. For the job skills, Claude pulled them from the postings I had links for, and for the ones without links it used the usual skills for that kind of role.
- **Simplified the code and UI.** The first version had a lot of extras and looked generic. I asked to remove features I didn't need (skill nicknames, a "skills worth learning" sidebar, a complicated phone number check), to use plain text buttons instead of icons, and to keep the code simpler so I can explain it.
- **Picked the design.** I went through a few versions: purple/pastel first, then I switched to baby blue and baby yellow, picked the Nunito font, more spacing because things felt bunched up, and clearer detail pages.
- **Fun features from my ideas.** I wanted the app to feel less sad when looking at rejections, so I added:
  - a **board view** like the GitHub project boards I've used for sprints, where you drag applications between status columns
  - **confetti** when something moves to Interview or Offer
  - a **weekly goal** of 10 applications on the dashboard
- **Things I tried and took out.** I tried a "rejection jar" on the dashboard and emojis on the statuses, but I didn't like them and wasn't sure my professor would, so I removed them.
- **Job Match.** I asked for clickable skill buttons first with a box to type anything else, instead of only typing.
- **Small UX fixes I noticed while testing:** the Filter button now changes color when you change the dropdown so it's clear you have to press it, and job posting links show the site name instead of "Open posting."


## Lessons Learned

- AI can write a lot of code fast, but the first version looked generic and had more than I needed. I had to keep editing.
- Going one step at a time and testing each step on my own computer mattered. Some problems only showed up on my machine (like the MySQL password), not in the AI's testing.
- Screenshots helped a lot, since the AI can't see my screen.
- I need to understand the code I submit. Asking "why" (like why the dropdowns only show existing companies) taught me more about foreign keys than just copying code.
- Be careful with what goes on GitHub: passwords go in `.env`, which is in `.gitignore`, and real people's info should be kept minimal in a public repo.

