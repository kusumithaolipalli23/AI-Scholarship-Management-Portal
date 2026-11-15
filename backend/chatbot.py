"""
Rule-based AI Scholarship Assistant.

No external AI API is configured in this environment, so this chatbot uses
keyword/intent matching combined with live scholarship-database lookups and
the student's profile to produce useful, relevant answers. It is clearly
labeled in the UI as "Rule-Based Assistant", not a real LLM.
"""
from engine import recommend_scholarships, evaluate

GREETINGS = ("hi", "hello", "hey", "good morning", "good afternoon", "good evening")


def _fmt_money(v):
    if v is None:
        return "N/A"
    return f"₹{v:,.0f}"


def handle_message(message, profile, scholarships):
    text = message.strip().lower()

    if not text:
        return "Could you tell me a bit more about what you'd like help with?"

    if any(text.startswith(g) for g in GREETINGS):
        return ("Hello! I'm your Scholarship Assistant (rule-based). I can help you with "
                "recommendations, eligibility, required documents, deadlines, and the application "
                "process. What would you like to know?")

    if "recommend" in text or "suggest" in text or "which scholarship" in text or "eligible for" in text:
        if not profile or profile["cgpa"] is None:
            return ("I can give personalized recommendations once your profile has your CGPA, "
                    "course, state, category and family income filled in. Please complete your "
                    "profile, or ask me about a specific scholarship in the meantime.")
        recs = recommend_scholarships(profile, scholarships, limit=3)
        if not recs:
            return "I couldn't find any scholarships in the database right now. Please check back later."
        lines = ["Based on your profile, here are your top matches:"]
        for r in recs:
            s = r["scholarship"]
            lines.append(f"• {s['name']} ({s['provider']}) — {r['score']}% match, "
                         f"{_fmt_money(s['amount'])}, deadline {s['application_deadline']}")
        lines.append("Ask me 'why am I eligible for <scholarship name>' for details on any of these.")
        return "\n".join(lines)

    if "document" in text:
        matched_sch = _find_scholarship_by_name(text, scholarships)
        if matched_sch:
            docs = matched_sch["required_documents"] or "Not specified"
            return f"Required documents for {matched_sch['name']}: {docs}."
        return ("Commonly required documents include ID Proof, Income Certificate, Caste Certificate, "
                "Bonafide Certificate, Marks Memo, Bank Passbook and Student ID. You can upload and "
                "manage these under 'Documents' in your dashboard. Ask about a specific scholarship "
                "for its exact document list.")

    if "deadline" in text or "last date" in text or "when" in text:
        matched_sch = _find_scholarship_by_name(text, scholarships)
        if matched_sch:
            return f"The application deadline for {matched_sch['name']} is {matched_sch['application_deadline']}."
        upcoming = sorted(scholarships, key=lambda s: s["application_deadline"] or "9999-99-99")[:5]
        lines = ["Here are the nearest upcoming deadlines:"]
        for s in upcoming:
            lines.append(f"• {s['name']} — {s['application_deadline']}")
        return "\n".join(lines)

    if "compare" in text:
        return ("You can compare scholarships side-by-side (amount, eligibility, deadline, documents, "
                "benefits) from the 'Compare' page — select up to 3 scholarships from the search "
                "results using the compare checkbox.")

    if "apply" in text or "application process" in text or "how do i apply" in text:
        return ("To apply: open a scholarship's details page, click 'Check Eligibility', then "
                "'Start Application'. You can save it as a draft, upload the required documents, "
                "and submit. You can track its status (Draft → Submitted → Under Review → "
                "Approved/Rejected) from 'My Applications'.")

    matched_sch = _find_scholarship_by_name(text, scholarships)
    if matched_sch:
        if profile and profile["cgpa"] is not None:
            r = evaluate(profile, matched_sch)
            return (f"{matched_sch['name']} ({matched_sch['provider']}): {_fmt_money(matched_sch['amount'])}, "
                    f"deadline {matched_sch['application_deadline']}. Based on your profile you are "
                    f"currently '{r['eligibility']}' ({r['score']}% match). "
                    f"{matched_sch['description'] or ''}")
        return (f"{matched_sch['name']} ({matched_sch['provider']}): {_fmt_money(matched_sch['amount'])}, "
                f"deadline {matched_sch['application_deadline']}. {matched_sch['description'] or ''}")

    return ("I can help with scholarship recommendations, eligibility checks, required documents, "
            "deadlines, comparisons, and the application process. Try asking, for example: "
            "\"Which scholarships am I eligible for?\" or \"What documents do I need for the "
            "National Merit Scholarship?\"")


def _find_scholarship_by_name(text, scholarships):
    for s in scholarships:
        if s["name"].lower() in text:
            return s
    # try partial word overlap
    best, best_score = None, 0
    for s in scholarships:
        words = set(s["name"].lower().split())
        overlap = len(words & set(text.split()))
        if overlap > best_score:
            best, best_score = s, overlap
    return best if best_score >= 2 else None
