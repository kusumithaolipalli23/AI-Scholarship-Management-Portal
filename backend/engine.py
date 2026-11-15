"""
Rule-based Scholarship Recommendation & Eligibility Engine.

NOTE: No external AI API is configured in this environment, so this module
implements a transparent, rule-based scoring system (NOT a machine-learning
or LLM-based model). All responses from this engine are clearly labeled as
"Rule-Based" throughout the app so they are never confused with real AI output.
"""
from datetime import datetime


def _age_from_dob(dob_str):
    if not dob_str:
        return None
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d")
        today = datetime.now()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except Exception:
        return None


def evaluate(profile, scholarship):
    """
    Compare a student profile (sqlite3.Row or dict) against a scholarship
    (sqlite3.Row or dict). Returns a dict with:
      - matched: list of (label, detail) that satisfy criteria
      - missing: list of (label, detail) that fail or are unknown
      - missing_profile_fields: profile fields needed but not filled in
      - score: 0-100 weighted match score
      - eligibility: 'Eligible' | 'Partially Eligible' | 'Not Eligible'
    """
    matched = []
    missing = []
    missing_profile_fields = []

    criteria_weights = {
        "cgpa": 20,
        "income": 20,
        "category": 15,
        "state": 15,
        "course": 15,
        "branch": 10,
        "gender": 5,
    }
    total_weight = 0
    earned_weight = 0

    # CGPA
    total_weight += criteria_weights["cgpa"]
    cgpa = profile.get("cgpa") if isinstance(profile, dict) else profile["cgpa"]
    min_cgpa = scholarship["min_cgpa"] if scholarship["min_cgpa"] is not None else 0
    if cgpa is None:
        missing_profile_fields.append("CGPA / Percentage")
        missing.append(("CGPA", f"Add your CGPA to check against minimum requirement of {min_cgpa}"))
    elif cgpa >= min_cgpa:
        matched.append(("CGPA", f"Your CGPA {cgpa} meets the minimum requirement of {min_cgpa}"))
        earned_weight += criteria_weights["cgpa"]
    else:
        missing.append(("CGPA", f"Your CGPA {cgpa} is below the minimum requirement of {min_cgpa}"))

    # Income
    total_weight += criteria_weights["income"]
    income = profile.get("annual_family_income") if isinstance(profile, dict) else profile["annual_family_income"]
    max_income = scholarship["max_family_income"]
    if income is None:
        missing_profile_fields.append("Annual Family Income")
        missing.append(("Family Income", "Add your annual family income to verify eligibility"))
    elif max_income is None or income <= max_income:
        matched.append(("Family Income", f"Your family income is within the allowed limit"
                         + (f" of ₹{max_income:,.0f}" if max_income else "")))
        earned_weight += criteria_weights["income"]
    else:
        missing.append(("Family Income", f"Your family income exceeds the maximum limit of ₹{max_income:,.0f}"))

    # Category
    total_weight += criteria_weights["category"]
    category = profile.get("category") if isinstance(profile, dict) else profile["category"]
    sch_category = scholarship["category"]
    if not sch_category or sch_category == "All":
        matched.append(("Category", "Open to all categories"))
        earned_weight += criteria_weights["category"]
    elif not category:
        missing_profile_fields.append("Category")
        missing.append(("Category", f"Add your category to check against required: {sch_category}"))
    elif category.strip().upper() in [c.strip().upper() for c in sch_category.split("/")]:
        matched.append(("Category", f"Your category ({category}) matches the requirement"))
        earned_weight += criteria_weights["category"]
    else:
        missing.append(("Category", f"This scholarship is reserved for category: {sch_category}"))

    # State
    total_weight += criteria_weights["state"]
    state = profile.get("state") if isinstance(profile, dict) else profile["state"]
    sch_state = scholarship["state"]
    if not sch_state or sch_state == "All":
        matched.append(("State", "Open to students from all states"))
        earned_weight += criteria_weights["state"]
    elif not state:
        missing_profile_fields.append("State")
        missing.append(("State", f"Add your state to check against required: {sch_state}"))
    elif state.strip().lower() == sch_state.strip().lower():
        matched.append(("State", f"You are from the required state ({sch_state})"))
        earned_weight += criteria_weights["state"]
    else:
        missing.append(("State", f"This scholarship is only for students from {sch_state}"))

    # Course
    total_weight += criteria_weights["course"]
    course = profile.get("course") if isinstance(profile, dict) else profile["course"]
    sch_course = scholarship["course"]
    if not sch_course or sch_course == "All":
        matched.append(("Course", "Open to all courses"))
        earned_weight += criteria_weights["course"]
    elif not course:
        missing_profile_fields.append("Course")
        missing.append(("Course", f"Add your course to check against required: {sch_course}"))
    elif course.strip().lower() == sch_course.strip().lower():
        matched.append(("Course", f"Your course ({course}) matches the requirement"))
        earned_weight += criteria_weights["course"]
    else:
        missing.append(("Course", f"This scholarship requires course: {sch_course}"))

    # Branch
    total_weight += criteria_weights["branch"]
    branch = profile.get("branch") if isinstance(profile, dict) else profile["branch"]
    sch_branch = scholarship["branch"]
    if not sch_branch or sch_branch == "All":
        matched.append(("Branch", "Open to all branches"))
        earned_weight += criteria_weights["branch"]
    elif not branch:
        missing_profile_fields.append("Branch")
        missing.append(("Branch", f"Add your branch to check against required: {sch_branch}"))
    elif branch.strip().lower() == sch_branch.strip().lower():
        matched.append(("Branch", f"Your branch ({branch}) matches the requirement"))
        earned_weight += criteria_weights["branch"]
    else:
        missing.append(("Branch", f"This scholarship requires branch: {sch_branch}"))

    # Gender
    total_weight += criteria_weights["gender"]
    gender = profile.get("gender") if isinstance(profile, dict) else profile["gender"]
    sch_gender = scholarship["gender_criteria"]
    if not sch_gender or sch_gender == "Any":
        matched.append(("Gender", "Open to all genders"))
        earned_weight += criteria_weights["gender"]
    elif not gender:
        missing_profile_fields.append("Gender")
        missing.append(("Gender", f"Add your gender to check against required: {sch_gender}"))
    elif gender.strip().lower() == sch_gender.strip().lower():
        matched.append(("Gender", "Your gender matches the requirement"))
        earned_weight += criteria_weights["gender"]
    else:
        missing.append(("Gender", f"This scholarship is only open to: {sch_gender}"))

    # Age (informational, not weighted heavily but checked)
    dob = profile.get("dob") if isinstance(profile, dict) else profile["dob"]
    age = _age_from_dob(dob)
    min_age = scholarship["min_age"]
    max_age = scholarship["max_age"]
    if (min_age or max_age) and age is not None:
        if (min_age is None or age >= min_age) and (max_age is None or age <= max_age):
            matched.append(("Age", f"Your age ({age}) is within the allowed range"))
        else:
            missing.append(("Age", f"Age requirement is {min_age or 0}-{max_age or '∞'}; your age is {age}"))
    elif (min_age or max_age) and age is None:
        missing_profile_fields.append("Date of Birth")

    score = round((earned_weight / total_weight) * 100) if total_weight else 0

    hard_fails = any(label in ("CGPA", "Family Income", "Category", "State", "Course", "Branch", "Gender")
                      for label, _ in missing)
    if score >= 90 and not hard_fails:
        eligibility = "Eligible"
    elif score >= 50:
        eligibility = "Partially Eligible"
    else:
        eligibility = "Not Eligible"

    return {
        "matched": matched,
        "missing": missing,
        "missing_profile_fields": missing_profile_fields,
        "score": score,
        "eligibility": eligibility,
    }


def why_recommended(result):
    matched_labels = [label for label, _ in result["matched"]]
    if not matched_labels:
        return "Not enough profile information to determine a strong match yet."
    return "Recommended because your " + ", ".join(matched_labels[:-1]) + \
        ((" and " + matched_labels[-1]) if len(matched_labels) > 1 else matched_labels[0]) + \
        " match this scholarship's requirements."


def recommend_scholarships(profile, scholarships, limit=None):
    results = []
    for sch in scholarships:
        r = evaluate(profile, sch)
        results.append({
            "scholarship": sch,
            "score": r["score"],
            "eligibility": r["eligibility"],
            "matched": r["matched"],
            "missing": r["missing"],
            "missing_profile_fields": r["missing_profile_fields"],
            "why": why_recommended(r),
        })
    results.sort(key=lambda x: x["score"], reverse=True)
    if limit:
        results = results[:limit]
    return results
