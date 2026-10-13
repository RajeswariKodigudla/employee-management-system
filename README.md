<<<<<<< HEAD
# Employee Management System
A Django portfolio application with employee CRUD, department management, authentication, dashboard metrics, search and filters, CSV export, attendance records, leave request review and responsive UI.

## Windows setup
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DJANGO_SECRET_KEY = (python -c "import secrets; print(secrets.token_urlsafe(50))")
$env:DJANGO_DEBUG = "True"
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```
Keep using the same PowerShell window for Django commands because the environment variables above are scoped to that window. The development key is randomly generated and is not stored in the repository; if you open a new window, set it again. For deployment, configure a private, stable `DJANGO_SECRET_KEY`, set `DJANGO_DEBUG=False`, and set `DJANGO_ALLOWED_HOSTS` to a comma-separated list of the application's hostnames. `DEBUG` defaults to `False`, local hosts are the default allowed hosts, and Django startup fails if `DJANGO_SECRET_KEY` is missing.

Open http://127.0.0.1:8000/ and sign in with the superuser credentials.

### Static files
Static assets are served from `static/` during local development when `DJANGO_DEBUG=True`. With `DJANGO_DEBUG=False`, collect assets into the ignored `staticfiles/` directory before running the server or deploying:
```powershell
python manage.py collectstatic --noinput
```
WhiteNoise serves the collected files without requiring a separate static-file server. Repeat `collectstatic` after changing or adding static assets.

## Features
- Real dashboard counts and department distribution.
- Employee create/read/update/delete, search, department/status filters, bulk delete, superuser-only Delete All confirmation, CSV export.
- Department CRUD with deletion protection when employees exist.
- Attendance records with unique employee/day constraint.
- Leave request creation and staff approval/rejection.
- Staff-only Reports & Analytics with joining-date, attendance-date, and leave-start-date filters, monthly attendance charts, leave-status summaries, and CSV export.
- Admin-only User & Role Management with paginated accounts, secure user creation, role assignment, account activation controls, and Django permission groups.
- Admin/HR Holidays & Calendar with company holiday CRUD, duplicate protection, month view, upcoming dates, search, and year/month filters.
- Authenticated Notifications inbox with idempotent pending-leave and upcoming-holiday alerts, unread badge, filters, and read controls.
- Admin/HR-only Payroll & Salary Management with monthly payroll records, validated salary calculations, employee history, filters, summaries, and CSV export.
- Admin/HR-only downloadable PDF payslips generated from each stored payroll record.
- Admin/HR-only Employee Performance & Appraisal reviews with validated ratings, employee histories, summaries, filters, and CSV export.
- Admin-only, read-only Audit Logs for tracked administrative changes, with safe change summaries, filters, and pagination.
- Login, registration, password change and Django admin.
- Responsive white/purple dashboard design.

## Reports & Analytics
Sign in with a staff account and select **Reports & Analytics** in the sidebar. The optional date range filters employee counts by joining date, attendance summaries by attendance date, and leave request counts by leave start date. Leave counts include Pending, Approved, and Rejected statuses, including zero-count statuses. Use **Export CSV** to download all report sections for the selected range.

To test the reports manually, add employees with different joining dates and departments, create attendance records in multiple months, and create leave requests in each status. Open `/reports/`, apply a range that includes some but not all records, and compare the charts, tables, and CSV download. Clearing the date filters shows all available records. Empty departments, attendance, and leave datasets are also supported.

Run the automated report tests with:
```powershell
python manage.py test core.test_reports
```

## User & Role Management
After updating the application, run `python manage.py migrate` to create the **Admin** and **HR** permission groups without deleting or resetting existing records. Existing superusers are assigned to Admin and other existing staff accounts are assigned to HR. Sign in as an administrator and open **User & Role Management** in the sidebar to list, create, edit, activate/deactivate, or assign an Employee, HR, or Admin role. New application-managed users are created through Django's password validation and hashing; existing passwords cannot be viewed.

HR group members receive employee, department, attendance, leave, and report permissions, but no user-management permission. User-management endpoints require the Admin role on the server. The application prevents an administrator from demoting themselves and prevents deactivating/demoting the last active administrator. Public self-registration remains available and creates an ordinary Employee account.

Run user and role permission tests with:
```powershell
python manage.py test core.test_user_management
```

## Holidays & Calendar
Run `python manage.py migrate` to add the holiday table and grant holiday permissions to the existing **Admin** and **HR** groups without resetting application data. Sign in as an Admin or HR user and open **Holidays & Calendar**. The monthly calendar defaults to the current month; search filters holiday names and descriptions, and year/month filters select the calendar period. Use **Add holiday** or the edit/delete actions to manage entries. Holiday names are unique per date, including case-insensitive duplicate checks in the form and a database uniqueness constraint.

Run the holiday CRUD and permission tests with:
```powershell
python manage.py test core.test_holidays
```

## Notifications
Run `python manage.py migrate` to add the per-user notifications table. The authenticated header/sidebar badge synchronizes pending leave alerts for users with leave-view permission and upcoming holiday alerts for all signed-in users for the next 30 days. Events are keyed per user and source record with a database uniqueness constraint, so reloading pages does not create duplicates. Leave alerts are removed when the request is no longer pending. Open **Notifications** to filter All, Read, or Unread; marking notifications read requires POST and only affects the current user's records.

Run notification behavior and access tests with:
```powershell
python manage.py test core.test_notifications
```

## Payroll & Salary Management
Run `python manage.py migrate` to create the payroll table and grant payroll permissions to the existing **Admin** and **HR** groups. Payroll records are monthly, unique per employee and pay month, and retain exact decimal amounts for basic salary, allowances, and deductions. Gross salary is basic salary plus allowances; net salary is gross salary less deductions. Amounts cannot be negative, deductions cannot exceed gross salary, and payment dates cannot precede the payroll month.

Authorized users can select **Payroll & Salary** in the sidebar to create or edit payroll records, filter by employee/year/month, review monthly totals, export the selected rows to CSV, and open each employee's salary history. The payroll list and history contain sensitive salary information and require payroll view permission; create and edit operations separately require their corresponding permissions. Only Admin and HR receive these permissions from the migration. Existing employee records remain intact; employee deletion is protected while payroll records refer to that employee.

Run payroll calculation, validation, permission, history, and export tests with:
```powershell
python manage.py test core.test_payroll
```

### Payslip PDF downloads
Each payroll row and employee salary-history row has a **Payslip** action. It downloads a PDF containing the company name, employee and department details, pay month, payment status/date, and the stored basic salary, allowances, gross, deductions, and net salary, formatted in rupees to two decimal places. The download uses the payroll record's existing calculated gross/net properties and does not modify payment status.

Only signed-in users with `core.view_payrollrecord` can download payslips. Employee accounts are not currently linked to Employee records in this project, so payslips are limited to authorized Admin/HR users; do not infer ownership from a matching email address. The default company name is set with `PAYSLIP_COMPANY_NAME` in `config/settings.py`. ReportLab uses an installed TrueType font containing the rupee glyph; if the server cannot find one automatically, set `PAYSLIP_FONT_PATH` to a suitable `.ttf` font. `reportlab` is included in `requirements.txt`.

Test PDF output, stored salary values, authentication, permissions, and missing records with:
```powershell
python manage.py test core.test_payslips
```

## Performance & Appraisal
Run `python manage.py migrate` to add performance review records and grant view/add/change/delete review permissions to the existing **Admin** and **HR** groups. The migration is additive and preserves the existing employee, payroll, holiday, and other application data.

Authorized Admin/HR users can open **Performance & Appraisal** in the sidebar to create and edit employee reviews, search by employee name or ID, filter by department, review-period start year, and rating, view rating and employee summaries, open employee-wise review history, and export filtered reviews to CSV. Ratings are limited to 1–5; review end dates cannot precede start dates; goals, achievements, strengths, improvement areas, and feedback are required. Reviewer identity is assigned from the signed-in user and retained when a review is edited. Review data is confidential and all list, history, edit, and export views enforce Django permissions on the server.

Run CRUD, validation, search/filter, export, and permission tests with:
```powershell
python manage.py test core.test_performance
```

## Audit Logs
Run `python manage.py migrate` to add the audit log table and grant its read-only view permission only to the existing **Admin** group. The migration does not alter or delete existing records. Open **Audit Logs** as an Admin to search across users, records, and descriptions; filter by acting user, action type, and date range; and browse paginated events.

Successful employee and department creation, updates and deletions; leave approvals/rejections; payroll create/update/delete; holiday CRUD; and performance review create/update/delete are recorded transactionally with the corresponding operation. Update entries include only selected safe fields. Payroll amounts and appraisal narrative fields are deliberately excluded. Audit records have no application create/edit/delete endpoints or model permissions; the interface is read-only.

Run audit event, redaction, duplicate-key, filtering, and access tests with:
```powershell
python manage.py test core.test_audit_logs
```

## Notes
Local portfolio project only. Before production deployment, configure environment-based secrets, DEBUG=False, HTTPS, email password reset, backups, logging, privacy rules and a production database. Delete All is destructive; test only with sample records. Biometric attendance and automated email notifications are not implemented.
=======
# employee-management-system
Django Employee Management System with payroll, attendance, leave management and audit logs
>>>>>>> da8acb3e20370d78158f400a88457ae40b210687
