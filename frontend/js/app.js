/* ===================== Global State & Helpers ===================== */
const state = { user: null, theme: localStorage.getItem("theme") || "light" };
document.body.setAttribute("data-theme", state.theme);

const $app = document.getElementById("app");

function escapeHtml(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmtMoney(v) {
  if (v === null || v === undefined || v === "") return "—";
  return "₹" + Number(v).toLocaleString("en-IN");
}
function fmtDate(v) {
  if (!v) return "—";
  try { return new Date(v).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }); }
  catch (e) { return v; }
}
function daysLeft(v) {
  if (!v) return null;
  const diff = Math.ceil((new Date(v) - new Date()) / 86400000);
  return diff;
}
function pillClass(status) {
  const map = {
    "Eligible": "pill-eligible", "Partially Eligible": "pill-partial", "Not Eligible": "pill-not",
    "Draft": "pill-draft", "Submitted": "pill-submitted", "Under Review": "pill-under-review",
    "Approved": "pill-approved", "Rejected": "pill-rejected", "Cancelled": "pill-cancelled",
  };
  return map[status] || "pill-draft";
}
let toastTimer = null;
function toast(msg, type) {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    el.style.cssText = "position:fixed;top:18px;left:50%;transform:translateX(-50%);z-index:999;padding:12px 20px;border-radius:8px;font-size:14px;font-weight:600;box-shadow:0 6px 20px rgba(0,0,0,.2);";
    document.body.appendChild(el);
  }
  const colors = { error: ["#fdecec", "#dc2626"], success: ["#eafaf0", "#16a34a"], info: ["#e6f6fd", "#0284c7"] };
  const [bg, fg] = colors[type || "info"];
  el.style.background = bg; el.style.color = fg;
  el.textContent = msg;
  el.style.display = "block";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.style.display = "none"; }, 3500);
}
function toggleTheme() {
  state.theme = state.theme === "light" ? "dark" : "light";
  document.body.setAttribute("data-theme", state.theme);
  localStorage.setItem("theme", state.theme);
  render();
}

/* ===================== Router ===================== */
const routes = {};
function route(path, handler) { routes[path] = handler; }
function navigate(hash) { window.location.hash = hash; }
window.addEventListener("hashchange", render);
window.addEventListener("DOMContentLoaded", init);

async function init() {
  try {
    const res = await API.get("/api/auth/me");
    state.user = res.user;
  } catch (e) { state.user = null; }
  render();
}

function currentPath() {
  return window.location.hash.replace(/^#/, "") || (state.user ? (state.user.role === "admin" ? "/admin/dashboard" : "/dashboard") : "/login");
}

function matchRoute(path) {
  const parts = path.split("/").filter(Boolean);
  for (const pattern in routes) {
    const pParts = pattern.split("/").filter(Boolean);
    if (pParts.length !== parts.length) continue;
    const params = {};
    let ok = true;
    for (let i = 0; i < pParts.length; i++) {
      if (pParts[i].startsWith(":")) params[pParts[i].slice(1)] = decodeURIComponent(parts[i]);
      else if (pParts[i] !== parts[i]) { ok = false; break; }
    }
    if (ok) return { handler: routes[pattern], params };
  }
  return null;
}

async function render() {
  const path = currentPath();
  const publicPaths = ["/login", "/register", "/forgot-password", "/reset-password"];
  if (!state.user && !publicPaths.includes(path.split("?")[0])) {
    window.location.hash = "/login";
    return;
  }
  if (state.user && publicPaths.includes(path.split("?")[0])) {
    window.location.hash = state.user.role === "admin" ? "/admin/dashboard" : "/dashboard";
    return;
  }
  const m = matchRoute(path.split("?")[0]);
  window.scrollTo(0, 0);
  if (!m) { $app.innerHTML = `<div class="empty-state"><div class="emoji">🔍</div><h3>Page not found</h3></div>`; return; }
  try {
    await m.handler(m.params);
  } catch (e) {
    console.error(e);
    $app.innerHTML = `<div class="empty-state"><div class="emoji">⚠️</div><h3>Something went wrong</h3><p>${escapeHtml(e.message)}</p></div>`;
  }
}

async function logout() {
  await API.post("/api/auth/logout");
  state.user = null;
  navigate("/login");
}

/* ===================== Auth Pages ===================== */
route("/login", renderLogin);
route("/register", renderRegister);
route("/forgot-password", renderForgotPassword);
route("/reset-password", renderResetPassword);

function renderLogin() {
  $app.innerHTML = `
  <div class="auth-wrap">
    <div class="auth-card">
      <h1>ScholarAI</h1>
      <p class="sub">Sign in to your scholarship portal</p>
      <div class="role-toggle">
        <button id="rt-student" class="active">Student</button>
        <button id="rt-admin">Admin</button>
      </div>
      <div id="alertBox"></div>
      <form id="loginForm">
        <div class="field"><label>Email</label><input type="email" id="email" required placeholder="you@example.com"></div>
        <div class="field"><label>Password</label><input type="password" id="password" required placeholder="••••••••"></div>
        <button class="btn btn-primary btn-block" type="submit">Login</button>
      </form>
      <p style="margin-top:16px;font-size:13px;" class="text-muted">
        <button class="link-btn" onclick="navigate('/forgot-password')">Forgot password?</button>
      </p>
      <p style="margin-top:8px;font-size:13px;" id="regLine">New student? <button class="link-btn" onclick="navigate('/register')">Create an account</button></p>
      <div class="alert alert-info" style="margin-top:16px;">
        Demo logins — Student: student@scholarship.test / student123<br>Admin: admin@scholarship.test / admin123
      </div>
    </div>
  </div>`;
  let role = "student";
  document.getElementById("rt-student").onclick = () => { role = "student"; toggleRole(); };
  document.getElementById("rt-admin").onclick = () => { role = "admin"; toggleRole(); };
  function toggleRole() {
    document.getElementById("rt-student").classList.toggle("active", role === "student");
    document.getElementById("rt-admin").classList.toggle("active", role === "admin");
    document.getElementById("regLine").style.display = role === "admin" ? "none" : "block";
  }
  document.getElementById("loginForm").onsubmit = async (e) => {
    e.preventDefault();
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    try {
      const res = await API.post("/api/auth/login", { email, password, role });
      state.user = res.user;
      navigate(role === "admin" ? "/admin/dashboard" : "/dashboard");
    } catch (err) {
      document.getElementById("alertBox").innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
    }
  };
}

function renderRegister() {
  $app.innerHTML = `
  <div class="auth-wrap">
    <div class="auth-card">
      <h1>Create your account</h1>
      <p class="sub">Register as a student to get started</p>
      <div id="alertBox"></div>
      <form id="regForm">
        <div class="field"><label>Full Name</label><input id="full_name" required></div>
        <div class="field"><label>Email</label><input type="email" id="email" required></div>
        <div class="field"><label>Mobile Number</label><input id="mobile" required></div>
        <div class="field"><label>Password (min 6 characters)</label><input type="password" id="password" minlength="6" required></div>
        <div class="field"><label>Confirm Password</label><input type="password" id="confirm_password" minlength="6" required></div>
        <button class="btn btn-primary btn-block" type="submit">Register</button>
      </form>
      <p style="margin-top:16px;font-size:13px;">Already have an account? <button class="link-btn" onclick="navigate('/login')">Login</button></p>
    </div>
  </div>`;
  document.getElementById("regForm").onsubmit = async (e) => {
    e.preventDefault();
    const body = {
      full_name: document.getElementById("full_name").value.trim(),
      email: document.getElementById("email").value.trim(),
      mobile: document.getElementById("mobile").value.trim(),
      password: document.getElementById("password").value,
      confirm_password: document.getElementById("confirm_password").value,
    };
    try {
      const res = await API.post("/api/auth/register", body);
      state.user = res.user;
      navigate("/dashboard");
    } catch (err) {
      document.getElementById("alertBox").innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
    }
  };
}

function renderForgotPassword() {
  $app.innerHTML = `
  <div class="auth-wrap">
    <div class="auth-card">
      <h1>Forgot password</h1>
      <p class="sub">Enter your email to receive a reset token</p>
      <div id="alertBox"></div>
      <form id="fpForm">
        <div class="field"><label>Email</label><input type="email" id="email" required></div>
        <button class="btn btn-primary btn-block" type="submit">Send reset token</button>
      </form>
      <p style="margin-top:16px;font-size:13px;"><button class="link-btn" onclick="navigate('/login')">Back to login</button></p>
    </div>
  </div>`;
  document.getElementById("fpForm").onsubmit = async (e) => {
    e.preventDefault();
    const email = document.getElementById("email").value.trim();
    try {
      const res = await API.post("/api/auth/forgot-password", { email });
      let extra = "";
      if (res.demo_reset_token) {
        extra = `<div class="alert alert-info">No email service is configured in this demo, so here is your reset token directly:<br><code>${escapeHtml(res.demo_reset_token)}</code></div>
        <button class="btn btn-outline btn-block" onclick="navigate('/reset-password?token=${encodeURIComponent(res.demo_reset_token)}')">Continue to reset password</button>`;
      }
      document.getElementById("alertBox").innerHTML = `<div class="alert alert-success">${escapeHtml(res.message)}</div>${extra}`;
    } catch (err) {
      document.getElementById("alertBox").innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
    }
  };
}

function renderResetPassword() {
  const params = new URLSearchParams(window.location.hash.split("?")[1] || "");
  const prefillToken = params.get("token") || "";
  $app.innerHTML = `
  <div class="auth-wrap">
    <div class="auth-card">
      <h1>Reset password</h1>
      <p class="sub">Enter the token and your new password</p>
      <div id="alertBox"></div>
      <form id="rpForm">
        <div class="field"><label>Reset Token</label><input id="token" required value="${escapeHtml(prefillToken)}"></div>
        <div class="field"><label>New Password (min 6 characters)</label><input type="password" id="password" minlength="6" required></div>
        <button class="btn btn-primary btn-block" type="submit">Reset Password</button>
      </form>
      <p style="margin-top:16px;font-size:13px;"><button class="link-btn" onclick="navigate('/login')">Back to login</button></p>
    </div>
  </div>`;
  document.getElementById("rpForm").onsubmit = async (e) => {
    e.preventDefault();
    const token = document.getElementById("token").value.trim();
    const password = document.getElementById("password").value;
    try {
      const res = await API.post("/api/auth/reset-password", { token, password });
      document.getElementById("alertBox").innerHTML = `<div class="alert alert-success">${escapeHtml(res.message)}</div>`;
      setTimeout(() => navigate("/login"), 1200);
    } catch (err) {
      document.getElementById("alertBox").innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
    }
  };
}

/* ===================== App Shell (Sidebar + Topbar) ===================== */
const studentNav = [
  ["/dashboard", "🏠", "Dashboard"],
  ["/scholarships", "🎓", "Find Scholarships"],
  ["/recommendations", "✨", "AI Recommendations"],
  ["/compare", "⚖️", "Compare"],
  ["/saved", "❤️", "Saved"],
  ["/applications", "📄", "My Applications"],
  ["/documents", "📁", "Documents"],
  ["/calendar", "📅", "Calendar"],
  ["/notifications", "🔔", "Notifications"],
  ["/profile", "👤", "Profile"],
];
const adminNav = [
  ["/admin/dashboard", "📊", "Analytics"],
  ["/admin/students", "🧑‍🎓", "Students"],
  ["/admin/scholarships", "🎓", "Scholarships"],
  ["/admin/applications", "📄", "Applications"],
  ["/admin/documents", "📁", "Documents"],
  ["/admin/reports", "🗂️", "Reports"],
  ["/admin/announcements", "📢", "Announcements"],
];

let unreadCount = 0;

function shell(innerHtml, activePath, pageTitle) {
  const nav = state.user.role === "admin" ? adminNav : studentNav;
  const navHtml = nav.map(([path, icon, label]) => `
    <div class="nav-item ${activePath === path ? "active" : ""}" onclick="navigate('${path}')">
      <span>${icon}</span><span>${label}</span>
    </div>`).join("");
  $app.innerHTML = `
  <div class="shell">
    <div class="sidebar" id="sidebar">
      <div class="brand">Scholar<span>AI</span></div>
      ${navHtml}
      <div style="flex:1"></div>
      <div class="nav-item" onclick="logout()"><span>🚪</span><span>Logout</span></div>
    </div>
    <div class="main">
      <div class="topbar">
        <div style="display:flex;align-items:center;gap:10px;">
          <button class="icon-btn menu-toggle" onclick="document.getElementById('sidebar').classList.toggle('open')">☰</button>
          <div class="title">${pageTitle}</div>
        </div>
        <div class="topbar-actions">
          <button class="icon-btn" title="Toggle theme" onclick="toggleTheme()">${state.theme === "light" ? "🌙" : "☀️"}</button>
          ${state.user.role === "student" ? `<button class="icon-btn" title="Notifications" onclick="navigate('/notifications')">🔔${unreadCount > 0 ? `<span class="badge">${unreadCount}</span>` : ""}</button>` : ""}
          <div style="font-size:13px;font-weight:700;">${escapeHtml(state.user.full_name)}</div>
        </div>
      </div>
      <div class="content">${innerHtml}</div>
    </div>
  </div>
  ${state.user.role === "student" ? chatbotWidgetHtml() : ""}
  `;
  if (state.user.role === "student") initChatbotWidget();
}

function loadingHtml() { return `<div class="loading">Loading…</div>`; }
function emptyState(emoji, title, sub) {
  return `<div class="empty-state"><div class="emoji">${emoji}</div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(sub || "")}</p></div>`;
}
function paginationControls(page, totalPages, total, onPageChangeFnName) {
  if (total === 0) return "";
  const prevDisabled = page <= 1 ? "disabled" : "";
  const nextDisabled = page >= totalPages ? "disabled" : "";
  return `
    <div class="flex-between" style="margin-top:14px;flex-wrap:wrap;gap:10px;">
      <span class="text-muted" style="font-size:13px;">Page ${page} of ${totalPages} · ${total} total</span>
      <div style="display:flex;gap:8px;">
        <button class="btn btn-outline btn-sm" ${prevDisabled} onclick="${onPageChangeFnName}(${page - 1})">← Prev</button>
        <button class="btn btn-outline btn-sm" ${nextDisabled} onclick="${onPageChangeFnName}(${page + 1})">Next →</button>
      </div>
    </div>`;
}

/* ===================== Student Dashboard ===================== */
route("/dashboard", renderDashboard);
async function renderDashboard() {
  shell(loadingHtml(), "/dashboard", "Dashboard");
  const d = await API.get("/api/dashboard");
  unreadCount = d.unread_notifications;
  const recHtml = d.recommended.length ? d.recommended.map(r => `
    <div class="card sch-card">
      <div class="top-row">
        <div><h3>${escapeHtml(r.scholarship.name)}</h3><div class="provider">${escapeHtml(r.scholarship.provider)}</div></div>
        <span class="pill ${pillClass(r.eligibility)}">${r.eligibility}</span>
      </div>
      <div class="meta"><span class="amount">${fmtMoney(r.scholarship.amount)}</span><span>Score: ${r.score}%</span><span>Deadline: ${fmtDate(r.scholarship.application_deadline)}</span></div>
      <p class="text-muted" style="margin:4px 0;font-size:13px;">${escapeHtml(r.why)}</p>
      <div class="actions"><button class="btn btn-primary btn-sm" onclick="navigate('/scholarships/${r.scholarship.id}')">View Details</button></div>
    </div>`).join("") : emptyState("🎯", "No recommendations yet", "Complete your profile to get AI-powered matches.");

  const appsHtml = d.applications.length ? `<div class="table-wrap"><table><thead><tr><th>Scholarship</th><th>Reference</th><th>Status</th><th>Deadline</th></tr></thead><tbody>
    ${d.applications.map(a => `<tr><td>${escapeHtml(a.scholarship_name)}</td><td>${a.reference_id}</td><td><span class="pill ${pillClass(a.status)}">${a.status}</span></td><td>${fmtDate(a.application_deadline)}</td></tr>`).join("")}
  </tbody></table></div>` : emptyState("📄", "No applications yet", "Start applying to scholarships you're eligible for.");

  const deadlinesHtml = d.upcoming_deadlines.length ? d.upcoming_deadlines.map(s => `
    <div class="doc-row"><span>${escapeHtml(s.name)}</span><span class="text-muted">${fmtDate(s.application_deadline)} (${daysLeft(s.application_deadline)}d left)</span></div>`).join("")
    : emptyState("📅", "No upcoming deadlines", "");

  shell(`
    <p class="text-muted mt-0">Welcome back, ${escapeHtml(d.full_name)}! Here's what's happening with your scholarships.</p>
    <div class="card">
      <div class="flex-between"><strong>Profile Completion</strong><span>${d.profile_completion}%</span></div>
      <div class="progress-bar" style="margin-top:8px;"><div class="fill" style="width:${d.profile_completion}%"></div></div>
      ${d.profile_completion < 100 ? `<button class="btn btn-outline btn-sm" style="margin-top:10px;" onclick="navigate('/profile')">Complete Profile</button>` : ""}
    </div>
    <div class="stat-grid" style="margin-top:16px;">
      <div class="stat-card"><div class="value">${d.eligible_count}</div><div class="label">Eligible Scholarships</div></div>
      <div class="stat-card"><div class="value">${d.saved_count}</div><div class="label">Saved</div></div>
      <div class="stat-card"><div class="value">${d.applications.length}</div><div class="label">Applications</div></div>
      <div class="stat-card"><div class="value">${d.upcoming_deadlines.length}</div><div class="label">Upcoming Deadlines</div></div>
    </div>
    <div class="section-title">Quick Actions</div>
    <div class="grid-3">
      <button class="btn btn-outline" onclick="navigate('/scholarships')">🔍 Find Scholarships</button>
      <button class="btn btn-outline" onclick="navigate('/recommendations')">✨ View Recommendations</button>
      <button class="btn btn-outline" onclick="navigate('/documents')">📁 Upload Documents</button>
      <button class="btn btn-outline" onclick="navigate('/applications')">📄 Track Applications</button>
      <button class="btn btn-outline" onclick="navigate('/calendar')">📅 Deadline Calendar</button>
      <button class="btn btn-outline" onclick="document.getElementById('chatFab').click()">🤖 Ask AI Assistant</button>
    </div>
    <div class="section-title">AI Recommended Scholarships (Rule-Based Engine) <button class="btn btn-sm btn-outline" onclick="navigate('/recommendations')">See all</button></div>
    <div class="list-grid">${recHtml}</div>
    <div class="section-title">Recent Applications</div>
    <div class="card">${appsHtml}</div>
    <div class="section-title">Upcoming Deadlines</div>
    <div class="card">${deadlinesHtml}</div>
  `, "/dashboard", "Dashboard");
}

/* ===================== Scholarship Search ===================== */
route("/scholarships", renderScholarships);
let compareSelection = JSON.parse(sessionStorage.getItem("compareSelection") || "[]");

async function renderScholarships() {
  shell(loadingHtml(), "/scholarships", "Find Scholarships");
  const list = await fetchScholarshipList();
  renderScholarshipListPage(list);
}
async function fetchScholarshipList(filters) {
  const params = new URLSearchParams(filters || {});
  return API.get("/api/scholarships?" + params.toString());
}
function renderScholarshipListPage(list, filters) {
  filters = filters || {};
  const cardsHtml = list.length ? list.map(scholarshipCard).join("") : emptyState("🔍", "No scholarships found", "Try adjusting your filters.");
  shell(`
    <div class="filters-bar">
      <input id="fq" placeholder="Search by name or provider" value="${escapeHtml(filters.q || "")}" style="min-width:220px;">
      <select id="ftype"><option value="All">All Types</option><option value="Government">Government</option><option value="Private">Private</option></select>
      <select id="fstate"><option value="All">All States</option><option>Telangana</option><option>Andhra Pradesh</option><option>Karnataka</option><option>Maharashtra</option></select>
      <select id="fcategory"><option value="All">All Categories</option><option>General</option><option>OBC</option><option>SC/ST</option><option>EWS</option></select>
      <select id="fsort"><option value="relevance">Sort: Relevance</option><option value="deadline">Sort: Deadline</option><option value="amount">Sort: Amount</option></select>
      <button class="btn btn-primary btn-sm" id="applyFilters">Search</button>
      ${compareSelection.length ? `<button class="btn btn-outline btn-sm" onclick="navigate('/compare')">Compare (${compareSelection.length})</button>` : ""}
    </div>
    <div class="list-grid">${cardsHtml}</div>
  `, "/scholarships", "Find Scholarships");

  document.getElementById("applyFilters").onclick = async () => {
    const f = {
      q: document.getElementById("fq").value,
      type: document.getElementById("ftype").value,
      state: document.getElementById("fstate").value,
      category: document.getElementById("fcategory").value,
      sort: document.getElementById("fsort").value,
    };
    const newList = await fetchScholarshipList(f);
    renderScholarshipListPage(newList, f);
  };
}
function scholarshipCard(s) {
  const dl = daysLeft(s.application_deadline);
  const checked = compareSelection.includes(s.id) ? "checked" : "";
  return `
  <div class="card sch-card">
    <label class="compare-check" title="Select to compare">
      <input type="checkbox" ${checked} onchange="toggleCompare(${s.id}, this.checked)">
    </label>
    <div class="top-row"><div><h3>${escapeHtml(s.name)}</h3><div class="provider">${escapeHtml(s.provider)} · ${s.scholarship_type}</div></div></div>
    <p class="text-muted" style="font-size:13px;margin:2px 0;">${escapeHtml((s.description || "").slice(0, 110))}${(s.description || "").length > 110 ? "…" : ""}</p>
    <div class="meta">
      <span class="amount">${fmtMoney(s.amount)}</span>
      <span>${escapeHtml(s.state || "All States")}</span>
      <span>${dl !== null && dl >= 0 ? dl + "d left" : "Closed"}</span>
    </div>
    <div class="actions">
      <button class="btn btn-primary btn-sm" onclick="navigate('/scholarships/${s.id}')">View Details</button>
      <button class="btn btn-outline btn-sm" onclick="quickSave(${s.id}, this)">❤️ Save</button>
    </div>
  </div>`;
}
function toggleCompare(id, checked) {
  if (checked) { if (compareSelection.length >= 3) { toast("You can compare up to 3 scholarships", "error"); render(); return; } compareSelection.push(id); }
  else compareSelection = compareSelection.filter(x => x !== id);
  sessionStorage.setItem("compareSelection", JSON.stringify(compareSelection));
  render();
}
async function quickSave(id, btn) {
  try { await API.post(`/api/saved/${id}`); toast("Scholarship saved", "success"); }
  catch (e) { toast(e.message, "error"); }
}

/* ===================== Scholarship Detail + Eligibility ===================== */
route("/scholarships/:id", renderScholarshipDetail);
async function renderScholarshipDetail(params) {
  shell(loadingHtml(), "/scholarships", "Scholarship Details");
  const s = await API.get(`/api/scholarships/${params.id}`);
  let elig = null;
  try { elig = await API.get(`/api/scholarships/${params.id}/eligibility`); } catch (e) {}
  const dl = daysLeft(s.application_deadline);

  const eligBlock = elig ? `
    <div class="card">
      <div class="flex-between"><strong>Eligibility Check (Rule-Based)</strong><span class="pill ${pillClass(elig.eligibility)}">${elig.eligibility}</span></div>
      <div class="progress-bar" style="margin:10px 0;"><div class="fill" style="width:${elig.score}%"></div></div>
      <div class="grid-2">
        <div><strong style="font-size:13px;">Matched</strong>
          ${elig.matched.map(([l, d]) => `<div class="check-row ok">✅ <span>${escapeHtml(d)}</span></div>`).join("") || "<div class='text-muted' style='font-size:13px;'>None yet</div>"}
        </div>
        <div><strong style="font-size:13px;">Not Matched / Missing</strong>
          ${elig.missing.map(([l, d]) => `<div class="check-row bad">❌ <span>${escapeHtml(d)}</span></div>`).join("") || "<div class='text-muted' style='font-size:13px;'>None</div>"}
        </div>
      </div>
      ${elig.missing_profile_fields.length ? `<div class="alert alert-info" style="margin-top:10px;">Add these to your profile for a more accurate check: ${elig.missing_profile_fields.join(", ")}</div>` : ""}
    </div>` : "";

  shell(`
    <button class="btn btn-outline btn-sm" onclick="navigate('/scholarships')">← Back to search</button>
    <div class="card" style="margin-top:12px;">
      <div class="flex-between"><h2 style="margin:0;">${escapeHtml(s.name)}</h2><span class="amount">${fmtMoney(s.amount)}</span></div>
      <p class="text-muted">${escapeHtml(s.provider)} · ${s.scholarship_type} ${s.is_sample ? " · <em>Sample/Demo data</em>" : ""}</p>
      <p>${escapeHtml(s.description || "")}</p>
      <div class="grid-2">
        <div><strong style="font-size:13px;">Eligibility Criteria</strong>
          <ul style="font-size:13px;color:var(--text-muted);">
            <li>Course: ${escapeHtml(s.course || "All")} ${s.branch && s.branch !== "All" ? "/ " + escapeHtml(s.branch) : ""}</li>
            <li>Category: ${escapeHtml(s.category || "All")}</li>
            <li>State: ${escapeHtml(s.state || "All")}</li>
            <li>Min CGPA: ${s.min_cgpa}</li>
            <li>Max Family Income: ${fmtMoney(s.max_family_income)}</li>
            <li>Gender: ${escapeHtml(s.gender_criteria || "Any")}</li>
          </ul>
        </div>
        <div><strong style="font-size:13px;">Key Dates & Documents</strong>
          <ul style="font-size:13px;color:var(--text-muted);">
            <li>Opens: ${fmtDate(s.application_start)}</li>
            <li>Deadline: ${fmtDate(s.application_deadline)} ${dl !== null ? `(${dl >= 0 ? dl + " days left" : "closed"})` : ""}</li>
            <li>Documents: ${escapeHtml(s.required_documents || "—")}</li>
            ${s.official_website ? `<li><a href="${escapeHtml(s.official_website)}" target="_blank" rel="noopener">Official website ↗</a></li>` : ""}
          </ul>
        </div>
      </div>
      <div class="actions" style="margin-top:14px;">
        <button class="btn btn-outline btn-sm" onclick="quickSave(${s.id}, this)">❤️ Save</button>
        <button class="btn btn-primary btn-sm" onclick="startApplication(${s.id})">Start Application</button>
      </div>
    </div>
    ${eligBlock}
  `, "/scholarships", "Scholarship Details");
}

async function startApplication(sid) {
  try {
    const res = await API.post("/api/applications", { scholarship_id: sid });
    toast("Application started as draft", "success");
    navigate("/applications");
  } catch (e) {
    if (e.data && e.data.application) { toast("You already have an application for this scholarship", "info"); navigate("/applications"); }
    else toast(e.message, "error");
  }
}

/* ===================== AI Recommendations Page ===================== */
route("/recommendations", renderRecommendations);
async function renderRecommendations() {
  shell(loadingHtml(), "/recommendations", "AI Recommendations");
  const res = await API.get("/api/recommendations");
  const html = res.recommendations.length ? res.recommendations.map(r => `
    <div class="card sch-card">
      <div class="top-row">
        <div><h3>${escapeHtml(r.scholarship.name)}</h3><div class="provider">${escapeHtml(r.scholarship.provider)}</div></div>
        <span class="pill ${pillClass(r.eligibility)}">${r.eligibility}</span>
      </div>
      <div class="meta"><span class="amount">${fmtMoney(r.scholarship.amount)}</span><span>Match score: ${r.score}%</span><span>Deadline: ${fmtDate(r.scholarship.application_deadline)}</span></div>
      <p style="font-size:13px;margin:4px 0;"><strong>Why recommended:</strong> ${escapeHtml(r.why)}</p>
      <details style="font-size:12px;"><summary style="cursor:pointer;color:var(--text-muted);">Matching vs missing criteria</summary>
        <div class="grid-2" style="margin-top:6px;">
          <div>${r.matched.map(([l, d]) => `<div class="check-row ok">✅ ${escapeHtml(d)}</div>`).join("")}</div>
          <div>${r.missing.map(([l, d]) => `<div class="check-row bad">❌ ${escapeHtml(d)}</div>`).join("")}</div>
        </div>
      </details>
      <div class="actions"><button class="btn btn-primary btn-sm" onclick="navigate('/scholarships/${r.scholarship.id}')">View & Apply</button></div>
    </div>`).join("") : emptyState("✨", "No recommendations yet", "Complete your profile to see personalized matches.");
  shell(`
    <div class="alert alert-info">These recommendations are generated by a transparent <strong>rule-based scoring engine</strong> comparing your profile to each scholarship's criteria — not a black-box AI model, since no external AI API is configured in this environment.</div>
    <div class="list-grid">${html}</div>
  `, "/recommendations", "AI Recommendations");
}

/* ===================== Compare ===================== */
route("/compare", renderCompare);
async function renderCompare() {
  shell(loadingHtml(), "/compare", "Compare Scholarships");
  if (!compareSelection.length) {
    shell(emptyState("⚖️", "No scholarships selected", "Go to Find Scholarships and select up to 3 to compare."), "/compare", "Compare Scholarships");
    return;
  }
  const list = await API.post("/api/compare", { ids: compareSelection });
  const rows = [
    ["Provider", s => s.provider],
    ["Amount", s => fmtMoney(s.amount)],
    ["Eligibility", s => s.eligibility ? `<span class="pill ${pillClass(s.eligibility)}">${s.eligibility}</span>` : "—"],
    ["Match Score", s => s.score !== undefined ? s.score + "%" : "—"],
    ["Deadline", s => fmtDate(s.application_deadline)],
    ["Min CGPA", s => s.min_cgpa],
    ["Max Income", s => fmtMoney(s.max_family_income)],
    ["Documents", s => s.required_documents],
  ];
  const html = `
  <div class="table-wrap">
  <table><thead><tr><th></th>${list.map(s => `<th>${escapeHtml(s.name)}</th>`).join("")}</tr></thead>
  <tbody>
    ${rows.map(([label, fn]) => `<tr><td><strong>${label}</strong></td>${list.map(s => `<td>${fn(s)}</td>`).join("")}</tr>`).join("")}
    <tr><td></td>${list.map(s => `<td><button class="btn btn-primary btn-sm" onclick="navigate('/scholarships/${s.id}')">View</button></td>`).join("")}</tr>
  </tbody></table></div>
  <button class="btn btn-outline btn-sm" style="margin-top:14px;" onclick="clearCompare()">Clear comparison</button>
  `;
  shell(html, "/compare", "Compare Scholarships");
}
function clearCompare() { compareSelection = []; sessionStorage.setItem("compareSelection", "[]"); navigate("/scholarships"); }

/* ===================== Saved ===================== */
route("/saved", renderSaved);
async function renderSaved() {
  shell(loadingHtml(), "/saved", "Saved Scholarships");
  const list = await API.get("/api/saved");
  const html = list.length ? `<div class="list-grid">${list.map(s => `
    <div class="card sch-card">
      <div class="top-row"><div><h3>${escapeHtml(s.name)}</h3><div class="provider">${escapeHtml(s.provider)}</div></div></div>
      <div class="meta"><span class="amount">${fmtMoney(s.amount)}</span><span>Deadline: ${fmtDate(s.application_deadline)}</span></div>
      <div class="actions">
        <button class="btn btn-primary btn-sm" onclick="navigate('/scholarships/${s.id}')">View</button>
        <button class="btn btn-danger btn-sm" onclick="removeSaved(${s.id})">Remove</button>
      </div>
    </div>`).join("")}</div>` : emptyState("❤️", "No saved scholarships", "Save scholarships you're interested in to find them here later.");
  shell(html, "/saved", "Saved Scholarships");
}
async function removeSaved(id) { await API.del(`/api/saved/${id}`); toast("Removed", "success"); renderSaved(); }

/* ===================== Applications ===================== */
route("/applications", renderApplications);
async function renderApplications() {
  shell(loadingHtml(), "/applications", "My Applications");
  const list = await API.get("/api/applications");
  const stages = ["Draft", "Submitted", "Under Review", "Approved"];
  const html = list.length ? list.map(a => {
    const isRejected = a.status === "Rejected";
    const isCancelled = a.status === "Cancelled";
    const curIdx = isRejected ? 2 : stages.indexOf(a.status);
    return `
    <div class="card">
      <div class="flex-between">
        <div><strong>${escapeHtml(a.scholarship_name)}</strong><div class="text-muted" style="font-size:12px;">${a.reference_id} · ${a.provider}</div></div>
        <span class="pill ${pillClass(a.status)}">${a.status}</span>
      </div>
      ${!isCancelled ? `<div class="timeline">
        ${stages.map((s, i) => `
          <div class="timeline-step ${isRejected && i === 3 ? "rejected" : (i < curIdx ? "done" : i === curIdx ? "current" : "")}">
            <div class="dot">${i < curIdx ? "✓" : i + 1}</div>
            <div class="label">${isRejected && i === 3 ? "Rejected" : s}</div>
          </div>`).join("")}
      </div>` : `<p class="text-muted" style="font-size:13px;">This application was cancelled.</p>`}
      <div class="text-muted" style="font-size:12px;">Deadline: ${fmtDate(a.application_deadline)} · Last updated: ${fmtDate(a.updated_at)}</div>
      <div class="actions" style="margin-top:10px;">
        ${a.status === "Draft" ? `<button class="btn btn-primary btn-sm" onclick="submitApplication(${a.id})">Submit Application</button>
          <button class="btn btn-danger btn-sm" onclick="cancelApplication(${a.id})">Cancel</button>` : ""}
        <button class="btn btn-outline btn-sm" onclick="navigate('/scholarships/${a.scholarship_id}')">View Scholarship</button>
      </div>
    </div>`;
  }).join("") : emptyState("📄", "No applications yet", "Browse scholarships and start your first application.");
  shell(html, "/applications", "My Applications");
}
async function submitApplication(id) {
  try { await API.put(`/api/applications/${id}`, { status: "Submitted" }); toast("Application submitted", "success"); renderApplications(); }
  catch (e) { toast(e.message, "error"); }
}
async function cancelApplication(id) {
  if (!confirm("Cancel this application?")) return;
  try { await API.put(`/api/applications/${id}`, { status: "Cancelled" }); toast("Application cancelled", "info"); renderApplications(); }
  catch (e) { toast(e.message, "error"); }
}

/* ===================== Documents ===================== */
route("/documents", renderDocuments);
const DOC_TYPES = ["ID Proof", "Income Certificate", "Caste Certificate", "Bonafide Certificate", "Marks Memo", "Bank Passbook", "Student ID"];
async function renderDocuments() {
  shell(loadingHtml(), "/documents", "Documents");
  const list = await API.get("/api/documents");
  const byType = {};
  list.forEach(d => { byType[d.doc_type] = d; });
  const statusPill = s => `<span class="pill ${s === "Verified" ? "pill-eligible" : s === "Rejected" ? "pill-not" : s === "Pending Verification" ? "pill-partial" : "pill-draft"}">${s}</span>`;
  const rowsHtml = DOC_TYPES.map(type => {
    const d = byType[type];
    return `<div class="doc-row">
      <div><strong>${type}</strong>${d ? `<div class="text-muted" style="font-size:12px;">${escapeHtml(d.file_name)}</div>` : ""}</div>
      <div style="display:flex;align-items:center;gap:8px;">
        ${d ? statusPill(d.status) : `<span class="pill pill-not">Missing</span>`}
        ${d ? `<button class="btn btn-outline btn-sm" onclick="downloadDoc(${d.id})">Preview/Download</button>
               <button class="btn btn-danger btn-sm" onclick="deleteDoc(${d.id})">Delete</button>` : ""}
        <label class="btn btn-primary btn-sm" style="margin:0;">
          ${d ? "Replace" : "Upload"}<input type="file" accept=".pdf,.png,.jpg,.jpeg" style="display:none;" onchange="uploadDoc('${type}', this)">
        </label>
      </div>
    </div>`;
  }).join("");
  shell(`<div class="card"><p class="text-muted" style="margin-top:0;">Accepted formats: PDF, JPG, PNG. Max size 5MB.</p>${rowsHtml}</div>`, "/documents", "Documents");
}
async function uploadDoc(type, input) {
  const file = input.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  fd.append("doc_type", type);
  try { await API.postForm("/api/documents", fd); toast("Document uploaded", "success"); renderDocuments(); }
  catch (e) { toast(e.message, "error"); }
}
function downloadDoc(id) { window.open(`/api/documents/${id}/file`, "_blank"); }
async function deleteDoc(id) {
  if (!confirm("Delete this document?")) return;
  await API.del(`/api/documents/${id}`); toast("Deleted", "info"); renderDocuments();
}

/* ===================== Notifications ===================== */
route("/notifications", renderNotifications);
async function renderNotifications() {
  shell(loadingHtml(), "/notifications", "Notifications");
  const list = await API.get("/api/notifications");
  unreadCount = list.filter(n => !n.is_read).length;
  const icons = { "Deadline": "⏰", "Missing Documents": "📁", "Application Submitted": "✅", "Status Changed": "🔄", "New Scholarship": "🎓", "Announcement": "📢", "General": "🔔" };
  const html = list.length ? `
    <button class="btn btn-outline btn-sm" style="margin-bottom:12px;" onclick="markAllRead()">Mark all as read</button>
    <div class="card">${list.map(n => `
      <div class="doc-row" style="opacity:${n.is_read ? 0.65 : 1};">
        <div style="display:flex;gap:10px;"><span>${icons[n.type] || "🔔"}</span>
          <div><strong>${escapeHtml(n.title)}</strong><div class="text-muted" style="font-size:13px;">${escapeHtml(n.message)}</div>
          <div class="text-muted" style="font-size:11px;">${fmtDate(n.created_at)}</div></div>
        </div>
        ${!n.is_read ? `<button class="btn btn-outline btn-sm" onclick="markRead(${n.id})">Mark read</button>` : ""}
      </div>`).join("")}</div>` : emptyState("🔔", "No notifications", "You're all caught up.");
  shell(html, "/notifications", "Notifications");
}
async function markRead(id) { await API.put(`/api/notifications/${id}/read`); renderNotifications(); }
async function markAllRead() { await API.put("/api/notifications/read-all"); renderNotifications(); }

/* ===================== Calendar ===================== */
route("/calendar", renderCalendar);
async function renderCalendar() {
  shell(loadingHtml(), "/calendar", "Scholarship Calendar");
  const events = await API.get("/api/calendar");
  const now = new Date();
  renderCalendarMonth(events, now.getFullYear(), now.getMonth());
}
function renderCalendarMonth(events, year, month) {
  const first = new Date(year, month, 1);
  const startDow = first.getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const byDate = {};
  events.forEach(e => { if (!e.date) return; const k = e.date; (byDate[k] = byDate[k] || []).push(e); });
  let cells = "";
  for (let i = 0; i < startDow; i++) cells += `<div class="cal-cell" style="visibility:hidden;"></div>`;
  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const evs = byDate[dateStr] || [];
    cells += `<div class="cal-cell"><div class="daynum">${day}</div>
      ${evs.slice(0, 3).map(e => `<div class="cal-event" title="${escapeHtml(e.title)} (${e.type})" onclick="navigate('/scholarships/${e.scholarship_id}')">${e.type === "Deadline" ? "⏰" : "🟢"} ${escapeHtml(e.title)}</div>`).join("")}
    </div>`;
  }
  const monthName = new Date(year, month, 1).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
  shell(`
    <div class="flex-between" style="margin-bottom:12px;">
      <button class="btn btn-outline btn-sm" onclick="shiftCalMonth(${year},${month},-1)">← Prev</button>
      <strong>${monthName}</strong>
      <button class="btn btn-outline btn-sm" onclick="shiftCalMonth(${year},${month},1)">Next →</button>
    </div>
    <div class="calendar-grid">
      ${["Sun","Mon","Tue","Wed","Thu","Fri","Sat"].map(d => `<div style="text-align:center;font-size:11px;font-weight:700;color:var(--text-muted);">${d}</div>`).join("")}
      ${cells}
    </div>
    <p class="text-muted" style="font-size:12px;margin-top:10px;">🟢 Application opens &nbsp; ⏰ Application deadline</p>
  `, "/calendar", "Scholarship Calendar");
  window._calEvents = events;
}
function shiftCalMonth(year, month, delta) {
  let m = month + delta, y = year;
  if (m < 0) { m = 11; y--; } if (m > 11) { m = 0; y++; }
  renderCalendarMonth(window._calEvents, y, m);
}

/* ===================== Profile ===================== */
route("/profile", renderProfile);
async function renderProfile() {
  shell(loadingHtml(), "/profile", "My Profile");
  const p = await API.get("/api/profile");
  const pr = p.profile || {};
  const f = (v) => v === null || v === undefined ? "" : v;
  shell(`
    <div class="card">
      <div class="flex-between"><strong>Profile Completion</strong><span>${p.profile_completion}%</span></div>
      <div class="progress-bar" style="margin-top:8px;"><div class="fill" style="width:${p.profile_completion}%"></div></div>
    </div>
    <form id="profileForm">
      <div class="section-title">Personal Information</div>
      <div class="card grid-2">
        <div class="field"><label>Full Name</label><input id="full_name" value="${escapeHtml(p.full_name)}"></div>
        <div class="field"><label>Email</label><input value="${escapeHtml(p.email)}" disabled></div>
        <div class="field"><label>Mobile Number</label><input id="mobile" value="${escapeHtml(p.mobile || "")}"></div>
        <div class="field"><label>Date of Birth</label><input type="date" id="dob" value="${f(pr.dob)}"></div>
        <div class="field"><label>Gender</label><select id="gender">${["","Male","Female","Other"].map(g=>`<option ${pr.gender===g?"selected":""}>${g}</option>`).join("")}</select></div>
        <div class="field"><label>Pincode</label><input id="pincode" value="${f(pr.pincode)}"></div>
        <div class="field"><label>Address</label><input id="address" value="${escapeHtml(f(pr.address))}"></div>
        <div class="field"><label>State</label><input id="state" value="${escapeHtml(f(pr.state))}"></div>
        <div class="field"><label>District</label><input id="district" value="${escapeHtml(f(pr.district))}"></div>
      </div>
      <div class="section-title">Academic Information</div>
      <div class="card grid-2">
        <div class="field"><label>College Name</label><input id="college_name" value="${escapeHtml(f(pr.college_name))}"></div>
        <div class="field"><label>University</label><input id="university" value="${escapeHtml(f(pr.university))}"></div>
        <div class="field"><label>Course</label><input id="course" value="${escapeHtml(f(pr.course))}" placeholder="e.g. B.Tech"></div>
        <div class="field"><label>Branch</label><input id="branch" value="${escapeHtml(f(pr.branch))}" placeholder="e.g. Computer Science"></div>
        <div class="field"><label>Year of Study</label><input id="year_of_study" value="${escapeHtml(f(pr.year_of_study))}"></div>
        <div class="field"><label>Semester</label><input id="semester" value="${escapeHtml(f(pr.semester))}"></div>
        <div class="field"><label>CGPA / Percentage</label><input type="number" step="0.01" id="cgpa" value="${f(pr.cgpa)}"></div>
      </div>
      <div class="section-title">Family Information</div>
      <div class="card grid-2">
        <div class="field"><label>Annual Family Income (₹)</label><input type="number" id="annual_family_income" value="${f(pr.annual_family_income)}"></div>
        <div class="field"><label>Category</label><select id="category">${["","General","OBC","SC/ST","EWS"].map(c=>`<option ${pr.category===c?"selected":""}>${c}</option>`).join("")}</select></div>
        <div class="field"><label>Minority Status</label><select id="minority_status">${["","Yes","No"].map(c=>`<option ${pr.minority_status===c?"selected":""}>${c}</option>`).join("")}</select></div>
        <div class="field"><label>Disability Status</label><select id="disability_status">${["","Yes","No"].map(c=>`<option ${pr.disability_status===c?"selected":""}>${c}</option>`).join("")}</select></div>
        <div class="field"><label>Sports Quota</label><select id="sports_quota">${["","Yes","No"].map(c=>`<option ${pr.sports_quota===c?"selected":""}>${c}</option>`).join("")}</select></div>
      </div>
      <div class="section-title">Additional Information</div>
      <div class="card grid-2">
        <div class="field"><label>Skills</label><textarea id="skills" rows="2">${escapeHtml(f(pr.skills))}</textarea></div>
        <div class="field"><label>Achievements</label><textarea id="achievements" rows="2">${escapeHtml(f(pr.achievements))}</textarea></div>
      </div>
      <div id="alertBox"></div>
      <button class="btn btn-primary" type="submit">Save Profile</button>
      <button class="btn btn-outline" type="button" onclick="downloadReport()">📄 Download PDF Report</button>
    </form>
  `, "/profile", "My Profile");

  document.getElementById("profileForm").onsubmit = async (e) => {
    e.preventDefault();
    const ids = ["full_name","mobile","dob","gender","address","state","district","pincode","college_name",
      "university","course","branch","year_of_study","semester","cgpa","annual_family_income","category",
      "minority_status","disability_status","sports_quota","skills","achievements"];
    const body = {};
    ids.forEach(id => body[id] = document.getElementById(id).value);
    try {
      const res = await API.put("/api/profile", body);
      document.getElementById("alertBox").innerHTML = `<div class="alert alert-success">Profile updated successfully.</div>`;
      toast("Profile saved", "success");
    } catch (err) {
      document.getElementById("alertBox").innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
    }
  };
}
function downloadReport() { window.open("/api/report/pdf", "_blank"); }

/* ===================== Chatbot Widget ===================== */
let chatOpen = false;
function chatbotWidgetHtml() {
  return `
  <button class="chat-fab" id="chatFab" onclick="toggleChat()">💬</button>
  <div class="chat-window" id="chatWindow" style="display:${chatOpen ? "flex" : "none"};">
    <div class="chat-header"><div>AI Scholarship Assistant<small>Rule-based assistant · uses your profile</small></div>
      <div style="display:flex;align-items:center;gap:10px;">
        <button class="modal-close" style="color:#fff;font-size:12px;" title="Clear conversation" onclick="clearChat()">Clear</button>
        <button class="modal-close" style="color:#fff;" onclick="toggleChat()">✕</button>
      </div>
    </div>
    <div class="chat-body" id="chatBody"></div>
    <div class="chat-input">
      <input id="chatInput" placeholder="Ask about scholarships…" maxlength="1000" onkeydown="if(event.key==='Enter')sendChat()">
      <button id="chatSendBtn" onclick="sendChat()">➤</button>
    </div>
  </div>`;
}
async function initChatbotWidget() {
  if (!chatOpen) return;
  await loadChatHistory();
}
function toggleChat() {
  chatOpen = !chatOpen;
  const win = document.getElementById("chatWindow");
  if (win) { win.style.display = chatOpen ? "flex" : "none"; if (chatOpen) loadChatHistory(); }
}
async function loadChatHistory() {
  const body = document.getElementById("chatBody");
  if (!body) return;
  body.innerHTML = "";
  try {
    const hist = await API.get("/api/chatbot/history");
    if (!hist.length) {
      appendChatMsg("bot", "Hi! I'm your rule-based Scholarship Assistant. Ask me about recommendations, eligibility, documents, deadlines, or the application process.");
    } else {
      hist.forEach(m => appendChatMsg(m.sender, m.message));
    }
  } catch (e) {}
}
function appendChatMsg(sender, msg) {
  const body = document.getElementById("chatBody");
  if (!body) return;
  const div = document.createElement("div");
  div.className = `chat-msg ${sender}`;
  div.textContent = msg;
  body.appendChild(div);
  body.scrollTop = body.scrollHeight;
  return div;
}
async function clearChat() {
  if (!confirm("Clear this conversation? This cannot be undone.")) return;
  try {
    await API.del("/api/chatbot/history");
    const body = document.getElementById("chatBody");
    if (body) body.innerHTML = "";
    appendChatMsg("bot", "Conversation cleared. Hi again! What would you like to know about scholarships?");
  } catch (e) {
    toast("Could not clear the conversation", "error");
  }
}
async function sendChat() {
  const input = document.getElementById("chatInput");
  const sendBtn = document.getElementById("chatSendBtn");
  const msg = input.value.trim();
  if (!msg) return;
  if (msg.length > 1000) { toast("Message is too long (max 1000 characters)", "error"); return; }
  input.value = "";
  input.disabled = true;
  if (sendBtn) sendBtn.disabled = true;
  appendChatMsg("user", msg);
  const typingEl = appendChatMsg("bot", "…thinking");
  try {
    const res = await API.post("/api/chatbot", { message: msg });
    typingEl.textContent = res.reply;
  } catch (e) {
    typingEl.textContent = e.message || "Sorry, I couldn't process that right now.";
  } finally {
    input.disabled = false;
    if (sendBtn) sendBtn.disabled = false;
    input.focus();
  }
}

/* ===================== ADMIN: Analytics Dashboard ===================== */
route("/admin/dashboard", renderAdminDashboard);
function bar(label, value, max, color) {
  const pct = max ? Math.round((value / max) * 100) : 0;
  return `<div style="margin-bottom:10px;">
    <div class="flex-between" style="font-size:12px;"><span>${escapeHtml(label)}</span><span>${value}</span></div>
    <div class="progress-bar"><div class="fill" style="width:${pct}%;background:${color || "var(--primary)"}"></div></div>
  </div>`;
}
async function renderAdminDashboard() {
  shell(loadingHtml(), "/admin/dashboard", "Analytics");
  const s = await API.get("/api/admin/stats");
  const maxPop = Math.max(1, ...s.scholarship_popularity.map(p => p.c));
  const maxMonth = Math.max(1, ...s.monthly_applications.map(m => m.c));
  const maxCat = Math.max(1, ...s.by_category.map(c => c.c));
  const maxState = Math.max(1, ...s.by_state.map(c => c.c));
  const statusColors = { Draft: "#9aa1c2", Submitted: "#0284c7", "Under Review": "#d97706", Approved: "#16a34a", Rejected: "#dc2626", Cancelled: "#9aa1c2" };
  shell(`
    <div class="stat-grid">
      <div class="stat-card"><div class="value">${s.total_students}</div><div class="label">Total Students</div></div>
      <div class="stat-card"><div class="value">${s.total_scholarships}</div><div class="label">Total Scholarships</div></div>
      <div class="stat-card"><div class="value">${s.total_applications}</div><div class="label">Total Applications</div></div>
      <div class="stat-card"><div class="value">${s.pending_applications}</div><div class="label">Pending</div></div>
      <div class="stat-card"><div class="value">${s.approved_applications}</div><div class="label">Approved</div></div>
      <div class="stat-card"><div class="value">${s.rejected_applications}</div><div class="label">Rejected</div></div>
    </div>
    <div class="grid-2">
      <div class="card"><strong>Applications by Status</strong><div style="margin-top:12px;">
        ${s.status_distribution.map(x => bar(x.status, x.c, Math.max(1, ...s.status_distribution.map(y=>y.c)), statusColors[x.status])).join("") || "<p class='text-muted'>No data yet</p>"}
      </div></div>
      <div class="card"><strong>Monthly Applications</strong><div style="margin-top:12px;">
        ${s.monthly_applications.map(m => bar(m.month, m.c, maxMonth)).join("") || "<p class='text-muted'>No data yet</p>"}
      </div></div>
      <div class="card"><strong>Scholarship Popularity (by applications)</strong><div style="margin-top:12px;">
        ${s.scholarship_popularity.map(p => bar(p.name, p.c, maxPop)).join("")}
      </div></div>
      <div class="card"><strong>Category-wise Applications</strong><div style="margin-top:12px;">
        ${s.by_category.map(c => bar(c.category, c.c, maxCat)).join("") || "<p class='text-muted'>No data yet</p>"}
      </div></div>
      <div class="card" style="grid-column:1/-1;"><strong>State-wise Applications</strong><div style="margin-top:12px;">
        ${s.by_state.map(c => bar(c.state, c.c, maxState)).join("") || "<p class='text-muted'>No data yet</p>"}
      </div></div>
    </div>
  `, "/admin/dashboard", "Analytics");
}

/* ===================== ADMIN: Students ===================== */
route("/admin/students", renderAdminStudents);
async function renderAdminStudents(page) {
  shell(loadingHtml(), "/admin/students", "Students");
  const data = await API.get(`/api/admin/students?page=${page || 1}&per_page=10`);
  renderAdminStudentsList(data);
}
function renderAdminStudentsList(data, q) {
  const list = data.items || [];
  const html = `
    <div class="filters-bar"><input id="sq" placeholder="Search students…" value="${escapeHtml(q || "")}" style="min-width:260px;"><button class="btn btn-primary btn-sm" id="sSearch">Search</button></div>
    <div class="card"><div class="table-wrap"><table><thead><tr><th>Name</th><th>Email</th><th>Mobile</th><th>Joined</th><th>Status</th><th>Actions</th></tr></thead><tbody>
    ${list.map(u => `<tr>
      <td>${escapeHtml(u.full_name)}</td><td>${escapeHtml(u.email)}</td><td>${escapeHtml(u.mobile || "-")}</td>
      <td>${fmtDate(u.created_at)}</td>
      <td><span class="pill ${u.is_active ? "pill-eligible" : "pill-not"}">${u.is_active ? "Active" : "Inactive"}</span></td>
      <td>
        <button class="btn btn-outline btn-sm" onclick="navigate('/admin/students/${u.id}')">View</button>
        <button class="btn ${u.is_active ? "btn-danger" : "btn-outline"} btn-sm" onclick="toggleStudentActive(${u.id}, ${u.is_active ? 0 : 1}, ${data.page})">${u.is_active ? "Deactivate" : "Activate"}</button>
      </td>
    </tr>`).join("") || `<tr><td colspan="6" class="text-muted">No students found</td></tr>`}
    </tbody></table></div>
    ${paginationControls(data.page, data.total_pages, data.total, "goToStudentsPage")}
    </div>`;
  shell(html, "/admin/students", "Students");
  window._studentsSearchQ = q || "";
  document.getElementById("sSearch").onclick = async () => {
    const query = document.getElementById("sq").value;
    window._studentsSearchQ = query;
    const newData = await API.get("/api/admin/students?q=" + encodeURIComponent(query) + "&page=1&per_page=10");
    renderAdminStudentsList(newData, query);
  };
}
async function goToStudentsPage(page) {
  const q = window._studentsSearchQ || "";
  const data = await API.get(`/api/admin/students?q=${encodeURIComponent(q)}&page=${page}&per_page=10`);
  renderAdminStudentsList(data, q);
}
async function toggleStudentActive(id, val, page) {
  await API.put(`/api/admin/students/${id}/active`, { is_active: val });
  toast("Updated", "success");
  goToStudentsPage(page || 1);
}

route("/admin/students/:id", renderAdminStudentDetail);
async function renderAdminStudentDetail(params) {
  shell(loadingHtml(), "/admin/students", "Student Profile");
  const s = await API.get(`/api/admin/students/${params.id}`);
  const pr = s.profile || {};
  shell(`
    <button class="btn btn-outline btn-sm" onclick="navigate('/admin/students')">← Back to students</button>
    <div class="card" style="margin-top:12px;">
      <h2 style="margin-top:0;">${escapeHtml(s.full_name)}</h2>
      <p class="text-muted">${escapeHtml(s.email)} · ${escapeHtml(s.mobile || "-")} · Joined ${fmtDate(s.created_at)}</p>
      <div class="grid-2" style="font-size:13px;">
        <div><strong>College:</strong> ${escapeHtml(pr.college_name || "-")}</div>
        <div><strong>Course/Branch:</strong> ${escapeHtml(pr.course || "-")} / ${escapeHtml(pr.branch || "-")}</div>
        <div><strong>CGPA:</strong> ${pr.cgpa ?? "-"}</div>
        <div><strong>Category:</strong> ${escapeHtml(pr.category || "-")}</div>
        <div><strong>State:</strong> ${escapeHtml(pr.state || "-")}</div>
        <div><strong>Family Income:</strong> ${fmtMoney(pr.annual_family_income)}</div>
      </div>
    </div>
    <div class="section-title">Applications</div>
    <div class="card"><div class="table-wrap"><table><thead><tr><th>Scholarship</th><th>Reference</th><th>Status</th></tr></thead><tbody>
      ${s.applications.map(a => `<tr><td>${escapeHtml(a.scholarship_name)}</td><td>${a.reference_id}</td><td><span class="pill ${pillClass(a.status)}">${a.status}</span></td></tr>`).join("") || `<tr><td colspan="3" class="text-muted">No applications</td></tr>`}
    </tbody></table></div></div>
  `, "/admin/students", "Student Profile");
}

/* ===================== ADMIN: Scholarships CRUD ===================== */
route("/admin/scholarships", renderAdminScholarships);
async function renderAdminScholarships(page) {
  shell(loadingHtml(), "/admin/scholarships", "Scholarships");
  page = page || 1;
  const data = await API.get(`/api/admin/scholarships?page=${page}&per_page=10`);
  const list = data.items || [];
  const html = `
    <button class="btn btn-primary btn-sm" style="margin-bottom:12px;" onclick="openScholarshipModal()">+ Add Scholarship</button>
    <div class="card"><div class="table-wrap"><table><thead><tr><th>Name</th><th>Provider</th><th>Amount</th><th>Deadline</th><th>Status</th><th>Actions</th></tr></thead><tbody>
    ${list.map(s => `<tr>
      <td>${escapeHtml(s.name)}</td><td>${escapeHtml(s.provider)}</td><td>${fmtMoney(s.amount)}</td><td>${fmtDate(s.application_deadline)}</td>
      <td><span class="pill ${s.status === "Published" ? "pill-eligible" : "pill-not"}">${s.status}</span> ${s.is_sample ? "<span class='pill pill-draft'>Sample</span>" : ""}</td>
      <td>
        <button class="btn btn-outline btn-sm" onclick='openScholarshipModal(${JSON.stringify(s).replace(/'/g, "&apos;")}, ${data.page})'>Edit</button>
        <button class="btn btn-outline btn-sm" onclick="togglePublish(${s.id}, '${s.status === "Published" ? "Unpublished" : "Published"}', ${data.page})">${s.status === "Published" ? "Unpublish" : "Publish"}</button>
        <button class="btn btn-danger btn-sm" onclick="deleteScholarship(${s.id}, ${data.page})">Delete</button>
      </td>
    </tr>`).join("") || `<tr><td colspan="6" class="text-muted">No scholarships found</td></tr>`}
    </tbody></table></div>
    ${paginationControls(data.page, data.total_pages, data.total, "renderAdminScholarships")}
    </div>`;
  shell(html, "/admin/scholarships", "Scholarships");
}
function openScholarshipModal(s, returnPage) {
  s = s || {};
  returnPage = returnPage || 1;
  const f = (v, d) => v === undefined || v === null ? (d || "") : v;
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal">
      <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">✕</button>
      <h2>${s.id ? "Edit" : "Add"} Scholarship</h2>
      <form id="schForm">
        <div class="field"><label>Name</label><input id="m_name" value="${escapeHtml(f(s.name))}" required></div>
        <div class="field"><label>Provider</label><input id="m_provider" value="${escapeHtml(f(s.provider))}" required></div>
        <div class="field"><label>Description</label><textarea id="m_description" rows="2">${escapeHtml(f(s.description))}</textarea></div>
        <div class="grid-2">
          <div class="field"><label>Type</label><select id="m_scholarship_type"><option ${s.scholarship_type==="Government"?"selected":""}>Government</option><option ${s.scholarship_type==="Private"?"selected":""}>Private</option></select></div>
          <div class="field"><label>Amount (₹)</label><input type="number" id="m_amount" value="${f(s.amount, 0)}"></div>
          <div class="field"><label>State (or All)</label><input id="m_state" value="${escapeHtml(f(s.state, "All"))}"></div>
          <div class="field"><label>Course (or All)</label><input id="m_course" value="${escapeHtml(f(s.course, "All"))}"></div>
          <div class="field"><label>Branch (or All)</label><input id="m_branch" value="${escapeHtml(f(s.branch, "All"))}"></div>
          <div class="field"><label>Category (or All)</label><input id="m_category" value="${escapeHtml(f(s.category, "All"))}"></div>
          <div class="field"><label>Min CGPA</label><input type="number" step="0.1" id="m_min_cgpa" value="${f(s.min_cgpa, 0)}"></div>
          <div class="field"><label>Max Family Income (₹)</label><input type="number" id="m_max_family_income" value="${f(s.max_family_income, 1000000)}"></div>
          <div class="field"><label>Gender Criteria</label><select id="m_gender_criteria"><option>Any</option><option>Male</option><option>Female</option></select></div>
          <div class="field"><label>Status</label><select id="m_status"><option ${s.status==="Published"?"selected":""}>Published</option><option ${s.status==="Unpublished"?"selected":""}>Unpublished</option></select></div>
          <div class="field"><label>Application Start</label><input type="date" id="m_application_start" value="${f(s.application_start)}"></div>
          <div class="field"><label>Application Deadline</label><input type="date" id="m_application_deadline" value="${f(s.application_deadline)}"></div>
        </div>
        <div class="field"><label>Required Documents (comma separated)</label><input id="m_required_documents" value="${escapeHtml(f(s.required_documents))}"></div>
        <div class="grid-2">
          <div class="field"><label>Official Website</label><input id="m_official_website" value="${escapeHtml(f(s.official_website))}"></div>
          <div class="field"><label>Application Link</label><input id="m_application_link" value="${escapeHtml(f(s.application_link))}"></div>
        </div>
        <button class="btn btn-primary btn-block" type="submit">${s.id ? "Save Changes" : "Create Scholarship"}</button>
      </form>
    </div>`;
  document.body.appendChild(overlay);
  document.getElementById("m_gender_criteria").value = s.gender_criteria || "Any";
  document.getElementById("schForm").onsubmit = async (e) => {
    e.preventDefault();
    const body = {
      name: document.getElementById("m_name").value, provider: document.getElementById("m_provider").value,
      description: document.getElementById("m_description").value, scholarship_type: document.getElementById("m_scholarship_type").value,
      amount: parseFloat(document.getElementById("m_amount").value || 0), state: document.getElementById("m_state").value,
      course: document.getElementById("m_course").value, branch: document.getElementById("m_branch").value,
      category: document.getElementById("m_category").value, min_cgpa: parseFloat(document.getElementById("m_min_cgpa").value || 0),
      max_family_income: parseFloat(document.getElementById("m_max_family_income").value || 0),
      gender_criteria: document.getElementById("m_gender_criteria").value,
      required_documents: document.getElementById("m_required_documents").value,
      application_start: document.getElementById("m_application_start").value,
      application_deadline: document.getElementById("m_application_deadline").value,
      official_website: document.getElementById("m_official_website").value,
      application_link: document.getElementById("m_application_link").value,
      status: document.getElementById("m_status").value,
    };
    try {
      if (s.id) await API.put(`/api/admin/scholarships/${s.id}`, body);
      else await API.post("/api/admin/scholarships", body);
      toast("Saved", "success");
      overlay.remove();
      renderAdminScholarships(s.id ? returnPage : 1);
    } catch (err) { toast(err.message, "error"); }
  };
}
async function togglePublish(id, status, page) {
  await API.put(`/api/admin/scholarships/${id}`, { status });
  toast("Updated", "success");
  renderAdminScholarships(page || 1);
}
async function deleteScholarship(id, page) {
  if (!confirm("Delete this scholarship? This cannot be undone.")) return;
  await API.del(`/api/admin/scholarships/${id}`);
  toast("Deleted", "success");
  renderAdminScholarships(page || 1);
}

/* ===================== ADMIN: Applications ===================== */
route("/admin/applications", renderAdminApplications);
async function renderAdminApplications(page, filterStatus) {
  shell(loadingHtml(), "/admin/applications", "Applications");
  page = page || 1;
  const qs = "page=" + page + "&per_page=10" + (filterStatus ? "&status=" + encodeURIComponent(filterStatus) : "");
  const data = await API.get("/api/admin/applications?" + qs);
  renderAdminApplicationsList(data, filterStatus);
}
function renderAdminApplicationsList(data, filterStatus) {
  const list = data.items || [];
  const statuses = ["", "Submitted", "Under Review", "Approved", "Rejected"];
  const html = `
    <div class="filters-bar">
      <select id="statusFilter">${statuses.map(s => `<option value="${s}" ${filterStatus===s?"selected":""}>${s || "All Statuses"}</option>`).join("")}</select>
    </div>
    <div class="card"><div class="table-wrap"><table><thead><tr><th>Student</th><th>Scholarship</th><th>Reference</th><th>Status</th><th>Actions</th></tr></thead><tbody>
    ${list.map(a => `<tr>
      <td>${escapeHtml(a.student_name)}<div class="text-muted" style="font-size:11px;">${escapeHtml(a.student_email)}</div></td>
      <td>${escapeHtml(a.scholarship_name)}</td><td>${a.reference_id}</td>
      <td><span class="pill ${pillClass(a.status)}">${a.status}</span></td>
      <td>
        ${["Submitted", "Under Review"].includes(a.status) ? `
          <button class="btn btn-outline btn-sm" onclick="setAppStatus(${a.id}, 'Under Review', ${data.page}, '${filterStatus || ""}')">Under Review</button>
          <button class="btn btn-outline btn-sm" onclick="setAppStatus(${a.id}, 'Approved', ${data.page}, '${filterStatus || ""}')">Approve</button>
          <button class="btn btn-danger btn-sm" onclick="setAppStatus(${a.id}, 'Rejected', ${data.page}, '${filterStatus || ""}')">Reject</button>` : "-"}
      </td>
    </tr>`).join("") || `<tr><td colspan="5" class="text-muted">No applications</td></tr>`}
    </tbody></table></div>
    ${paginationControls(data.page, data.total_pages, data.total, "goToApplicationsPage")}
    </div>`;
  shell(html, "/admin/applications", "Applications");
  document.getElementById("statusFilter").onchange = async (e) => {
    const status = e.target.value;
    renderAdminApplications(1, status);
  };
}
function goToApplicationsPage(page) {
  const status = document.getElementById("statusFilter") ? document.getElementById("statusFilter").value : "";
  renderAdminApplications(page, status);
}
async function setAppStatus(id, status, page, filterStatus) {
  try { await API.put(`/api/admin/applications/${id}/status`, { status }); toast("Status updated", "success"); renderAdminApplications(page || 1, filterStatus); }
  catch (e) { toast(e.message, "error"); }
}

/* ===================== ADMIN: Documents ===================== */
route("/admin/documents", renderAdminDocuments);
async function renderAdminDocuments(page) {
  shell(loadingHtml(), "/admin/documents", "Documents");
  page = page || 1;
  const data = await API.get(`/api/admin/documents?page=${page}&per_page=10`);
  const list = data.items || [];
  const html = `<div class="card"><div class="table-wrap"><table><thead><tr><th>Student</th><th>Type</th><th>File</th><th>Status</th><th>Actions</th></tr></thead><tbody>
    ${list.map(d => `<tr>
      <td>${escapeHtml(d.student_name)}</td><td>${escapeHtml(d.doc_type)}</td>
      <td><a href="/api/documents/${d.id}/file" target="_blank" rel="noopener">${escapeHtml(d.file_name)}</a></td>
      <td><span class="pill ${d.status === "Verified" ? "pill-eligible" : d.status === "Rejected" ? "pill-not" : "pill-partial"}">${d.status}</span></td>
      <td>
        <button class="btn btn-outline btn-sm" onclick="adminSetDocStatus(${d.id}, 'Verified', ${data.page})">Verify</button>
        <button class="btn btn-danger btn-sm" onclick="adminRejectDoc(${d.id}, ${data.page})">Reject</button>
      </td>
    </tr>`).join("") || `<tr><td colspan="5" class="text-muted">No documents uploaded yet</td></tr>`}
    </tbody></table></div>
    ${paginationControls(data.page, data.total_pages, data.total, "renderAdminDocuments")}
    </div>`;
  shell(html, "/admin/documents", "Documents");
}
async function adminSetDocStatus(id, status, page) {
  await API.put(`/api/admin/documents/${id}/status`, { status });
  toast("Updated", "success"); renderAdminDocuments(page || 1);
}
async function adminRejectDoc(id, page) {
  const reason = prompt("Reason for rejection?") || "Not specified";
  await API.put(`/api/admin/documents/${id}/status`, { status: "Rejected", reject_reason: reason });
  toast("Document rejected", "info"); renderAdminDocuments(page || 1);
}

/* ===================== ADMIN: Announcements ===================== */
route("/admin/announcements", renderAdminAnnouncements);
async function renderAdminAnnouncements() {
  shell(`
    <div class="card" style="max-width:520px;">
      <p class="text-muted mt-0">Send an announcement notification to all students.</p>
      <div id="alertBox"></div>
      <form id="annForm">
        <div class="field"><label>Title</label><input id="a_title" required></div>
        <div class="field"><label>Message</label><textarea id="a_message" rows="4" required></textarea></div>
        <button class="btn btn-primary" type="submit">Send Announcement</button>
      </form>
    </div>
  `, "/admin/announcements", "Announcements");
  document.getElementById("annForm").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await API.post("/api/admin/announcements", { title: document.getElementById("a_title").value, message: document.getElementById("a_message").value });
      document.getElementById("alertBox").innerHTML = `<div class="alert alert-success">Announcement sent to all students.</div>`;
      document.getElementById("annForm").reset();
    } catch (err) { document.getElementById("alertBox").innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`; }
  };
}

/* ===================== ADMIN: Reports ===================== */
route("/admin/reports", renderAdminReports);
const REPORT_TYPES_UI = [
  ["students", "🧑‍🎓", "Students", "All registered student accounts and their status."],
  ["scholarships", "🎓", "Scholarships", "Every scholarship in the database, published or not."],
  ["applications", "📄", "Applications", "All student applications with status and dates."],
  ["documents", "📁", "Documents", "All uploaded documents and their verification status."],
];
async function renderAdminReports() {
  shell(loadingHtml(), "/admin/reports", "Reports");
  let summary = {};
  try { summary = await API.get("/api/admin/reports/summary"); } catch (e) {}
  const cardsHtml = REPORT_TYPES_UI.map(([key, icon, label, desc]) => `
    <div class="card">
      <div class="flex-between">
        <div><h3 style="margin:0;">${icon} ${label}</h3><p class="text-muted" style="font-size:13px;margin:4px 0 0;">${desc}</p></div>
        <div class="stat-card" style="padding:8px 14px;"><div class="value" style="font-size:20px;">${summary[key] ?? "—"}</div><div class="label">records</div></div>
      </div>
      <div class="actions" style="margin-top:14px;">
        <button class="btn btn-outline btn-sm" onclick="downloadAdminReport('${key}','csv')">⬇ CSV</button>
        <button class="btn btn-outline btn-sm" onclick="downloadAdminReport('${key}','excel')">⬇ Excel</button>
        <button class="btn btn-outline btn-sm" onclick="downloadAdminReport('${key}','pdf')">⬇ PDF</button>
      </div>
    </div>`).join("");
  shell(`
    <p class="text-muted mt-0">Export any dataset below as CSV, Excel, or PDF for offline analysis or record-keeping.</p>
    <div class="list-grid">${cardsHtml}</div>
  `, "/admin/reports", "Reports");
}
function downloadAdminReport(type, fmt) {
  window.open(`/api/admin/reports/${type}/${fmt}`, "_blank");
}
