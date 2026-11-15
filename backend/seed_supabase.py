"""
Run this once after applying supabase_schema.sql to a fresh Supabase project,
to seed the same admin/demo-student/sample-scholarship data that the SQLite
backend creates automatically. Requires DB_BACKEND=supabase and valid
SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env.

    python3 seed_supabase.py

Not run automatically (unlike the SQLite path) because seeding a shared
production database on every app start would be unexpected/unsafe.
"""
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from config import config
from repo_supabase import SupabaseRepo


def d(days):
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


def main():
    if config.DB_BACKEND != "supabase":
        print("DB_BACKEND is not 'supabase' in your .env — aborting to avoid confusion.")
        return
    repo = SupabaseRepo()
    repo.init()

    if repo.get_user_by_email("admin@scholarship.test"):
        print("Seed data already appears to exist (admin@scholarship.test found). Skipping.")
        return

    admin_id = repo.create_user("Portal Admin", "admin@scholarship.test", "9999999999",
                                 generate_password_hash("admin123"), role="admin")
    print(f"Created admin user id={admin_id}")

    student_id = repo.create_user("Asha Reddy", "student@scholarship.test", "9876543210",
                                   generate_password_hash("student123"), role="student")
    repo.update_profile(student_id, {
        "dob": "2004-05-14", "gender": "Female", "address": "12-3 Lake View Colony",
        "state": "Telangana", "district": "Hyderabad", "pincode": "500001",
        "college_name": "Osmania University College of Engineering", "university": "Osmania University",
        "course": "B.Tech", "branch": "Computer Science", "year_of_study": "3rd Year",
        "semester": "5th Semester", "cgpa": 8.6, "annual_family_income": 320000,
        "category": "OBC", "minority_status": "No", "disability_status": "No", "sports_quota": "No",
        "skills": "Python, Web Development, Public Speaking",
        "achievements": "State-level coding hackathon winner 2025",
    })
    print(f"Created demo student id={student_id}")

    scholarships = [
        dict(name="National Merit Scholarship for Engineering Students", provider="Ministry of Education (Govt. of India)",
             description="Merit-based scholarship for undergraduate engineering students from economically weaker sections, covering tuition and a monthly stipend.",
             scholarship_type="Government", amount=75000, state="All", course="B.Tech", branch="All",
             category="All", min_cgpa=7.5, max_family_income=350000, gender_criteria="Any", min_age=17, max_age=25,
             required_documents="ID Proof,Income Certificate,Marks Memo,Bonafide Certificate",
             application_start=d(-20), application_deadline=d(25),
             official_website="https://scholarships.gov.in", application_link="https://scholarships.gov.in/apply",
             status="Published"),
        dict(name="State Minority Welfare Scholarship", provider="Telangana Minorities Welfare Department",
             description="Financial assistance for minority community students pursuing higher education within the state.",
             scholarship_type="Government", amount=40000, state="Telangana", course="All", branch="All",
             category="All", min_cgpa=6.0, max_family_income=250000, gender_criteria="Any", min_age=16, max_age=30,
             required_documents="ID Proof,Income Certificate,Bonafide Certificate",
             application_start=d(-10), application_deadline=d(15),
             official_website="https://minoritywelfare.telangana.gov.in", application_link="https://minoritywelfare.telangana.gov.in/apply",
             status="Published"),
        dict(name="Girls in STEM Excellence Grant", provider="TechForward Foundation",
             description="Private grant encouraging female students in STEM fields with strong academic performance.",
             scholarship_type="Private", amount=60000, state="All", course="B.Tech", branch="Computer Science",
             category="All", min_cgpa=8.0, max_family_income=600000, gender_criteria="Female", min_age=17, max_age=24,
             required_documents="ID Proof,Marks Memo,Student ID",
             application_start=d(-5), application_deadline=d(40),
             official_website="https://techforward.example.org", application_link="https://techforward.example.org/apply",
             status="Published"),
        dict(name="SC/ST Higher Education Support Scheme", provider="Social Welfare Department",
             description="Scholarship supporting SC/ST students pursuing undergraduate and postgraduate courses.",
             scholarship_type="Government", amount=55000, state="All", course="All", branch="All",
             category="SC/ST", min_cgpa=5.5, max_family_income=250000, gender_criteria="Any", min_age=16, max_age=30,
             required_documents="ID Proof,Caste Certificate,Income Certificate,Bonafide Certificate",
             application_start=d(-30), application_deadline=d(10),
             official_website="https://socialwelfare.gov.in", application_link="https://socialwelfare.gov.in/apply",
             status="Published"),
        dict(name="Sports Achievers Scholarship", provider="Sports Authority Trust",
             description="For students under the sports quota with notable state/national level achievements.",
             scholarship_type="Private", amount=35000, state="All", course="All", branch="All",
             category="All", min_cgpa=5.0, max_family_income=800000, gender_criteria="Any", min_age=16, max_age=26,
             required_documents="ID Proof,Achievement Certificate,Bonafide Certificate",
             application_start=d(-15), application_deadline=d(60),
             official_website="https://sportstrust.example.org", application_link="https://sportstrust.example.org/apply",
             status="Published"),
        dict(name="Differently Abled Students Support Grant", provider="Ministry of Social Justice",
             description="Financial support for differently-abled students to pursue higher education without financial burden.",
             scholarship_type="Government", amount=90000, state="All", course="All", branch="All",
             category="All", min_cgpa=5.0, max_family_income=400000, gender_criteria="Any", min_age=16, max_age=35,
             required_documents="ID Proof,Disability Certificate,Income Certificate",
             application_start=d(-8), application_deadline=d(50),
             official_website="https://socialjustice.gov.in", application_link="https://socialjustice.gov.in/apply",
             status="Published"),
        dict(name="Computer Science Innovators Scholarship", provider="InfoNext Pvt Ltd",
             description="For high-achieving Computer Science / IT branch students showing project or research excellence.",
             scholarship_type="Private", amount=50000, state="All", course="B.Tech", branch="Computer Science",
             category="All", min_cgpa=8.5, max_family_income=1000000, gender_criteria="Any", min_age=17, max_age=24,
             required_documents="ID Proof,Marks Memo,Student ID",
             application_start=d(-2), application_deadline=d(30),
             official_website="https://infonext.example.com", application_link="https://infonext.example.com/apply",
             status="Published"),
        dict(name="EWS Undergraduate Fee Reimbursement", provider="State Higher Education Council",
             description="Fee reimbursement scheme for Economically Weaker Section (EWS) undergraduate students.",
             scholarship_type="Government", amount=45000, state="Telangana", course="All", branch="All",
             category="EWS", min_cgpa=6.0, max_family_income=800000, gender_criteria="Any", min_age=16, max_age=28,
             required_documents="ID Proof,Income Certificate,EWS Certificate,Bonafide Certificate",
             application_start=d(-25), application_deadline=d(5),
             official_website="https://hec.telangana.gov.in", application_link="https://hec.telangana.gov.in/apply",
             status="Published"),
        dict(name="Rural Talent Scholarship", provider="Bharat Rural Development Trust",
             description="For meritorious students from rural districts pursuing any undergraduate degree.",
             scholarship_type="Private", amount=30000, state="All", course="All", branch="All",
             category="All", min_cgpa=6.5, max_family_income=300000, gender_criteria="Any", min_age=16, max_age=25,
             required_documents="ID Proof,Income Certificate,Bonafide Certificate",
             application_start=d(-12), application_deadline=d(3),
             official_website="https://ruraldevtrust.example.org", application_link="https://ruraldevtrust.example.org/apply",
             status="Published"),
        dict(name="Post Graduate Research Fellowship", provider="National Science & Technology Board",
             description="Fellowship for students pursuing postgraduate research in core engineering and science branches.",
             scholarship_type="Government", amount=120000, state="All", course="M.Tech", branch="All",
             category="All", min_cgpa=8.0, max_family_income=1200000, gender_criteria="Any", min_age=21, max_age=32,
             required_documents="ID Proof,Marks Memo,Research Proposal",
             application_start=d(-1), application_deadline=d(70),
             official_website="https://nstb.gov.in", application_link="https://nstb.gov.in/apply",
             status="Published"),
    ]
    for s in scholarships:
        repo.create_scholarship(s)
    print(f"Created {len(scholarships)} sample scholarships")

    repo.create_notification(student_id, "Welcome to the Scholarship Portal",
                              "Complete your profile to get personalized AI-powered scholarship recommendations.",
                              "Announcement")
    repo.create_notification(None, "New scholarships added",
                              "10 sample scholarships are now available on the portal. Explore and check your eligibility.",
                              "New Scholarship")
    print("Seed complete.")


if __name__ == "__main__":
    main()
