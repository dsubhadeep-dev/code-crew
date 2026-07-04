# HRMS Running Instructions

## What this project does
This project is a simple Human Resource Management System built with Flask, SQLite, and server-rendered HTML templates. It includes:

- User login and signup
- Admin and employee roles
- Employee dashboard and profile management
- Attendance check-in/check-out
- Leave requests and approvals
- Salary information and calculation views
- Company settings

## Requirements
Make sure Python 3 is installed on your system.

## Run the project locally
1. Open a terminal in the project folder:
   ```bash
   cd hrms
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
   On Windows PowerShell:
   ```powershell
   venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the app:
   ```bash
   python app.py
   ```
5. Open the app in your browser:
   ```text
   http://127.0.0.1:5000
   ```

## Demo login details
The app seeds demo users on first run.

- Admin login ID: OIADUS20260001
- Admin password: admin123
- Employee login ID: OIRISH20260001
- Employee password: employee123

## Notes
- The SQLite database file will be created automatically on first run.
- Uploaded files are stored in the static/uploads folder.
