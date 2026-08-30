# RISE — From Ideas to Impact

A modern, responsive public site for the Research & Innovation Society for Emerging Intelligence (RISE), Sanjivani University. It is deliberately dependency-free: the finished site works by opening `index.html` and deploys to any static host.

## Run locally

Open `index.html` in a browser, or use the VS Code **Live Server** extension. No install or build command is required.

## Deploy to GitHub Pages

1. Create an empty GitHub repository, for example `rise-sanjivani`.
2. Upload these files to the repository root (not inside another folder).
3. In the repository, select **Settings → Pages**.
4. Under *Build and deployment*, choose **Deploy from a branch**, then select `main` and `/ (root)`.
5. Save. GitHub will show the public site address shortly afterward.

The same files deploy directly to Netlify (drag the folder into Netlify Drop), Cloudflare Pages, Vercel, or any normal web server.

## Included

- Responsive landing page, research domains, projects, events, opportunities, team and application form.
- Project detail dialog, registration states, application success state, mobile layout and a theme-control hook.
- Representative data for domains, projects, events and opportunities in `app.js`.
- `portal.html`: role-aware member, project lead, mentor, admin and super-admin portal demo.
- Member profile, projects, research idea bank, pipeline, ethics checklist, tasks, events, opportunities, certificates, announcements, reports and team collaboration views.
- Admin applications, members, teams, research management, audit logs, restricted support-records view, CSV-report demo, data-entry forms and browser-persisted sample data.

## Production note

This is a public static website and portal prototype. The role selector and data are browser-only, used to demonstrate all panels; they are not secure authentication. The requested production system requires a backend with university SSO/password reset, database, private document storage, server-side role-based access control, audit logs, protected downloads and email service. Do **not** treat browser-only interfaces as secure access control. A production implementation can use Next.js + Supabase/Firebase, or a Node/Express API + PostgreSQL.

## File structure

```
index.html    Page structure and content
styles.css    Responsive visual system
app.js        Sample data and interactivity
portal.html   Role-aware workspace entry point
portal.css    Workspace layout and components
portal.js     Portal sample data, role views and interactions
```
