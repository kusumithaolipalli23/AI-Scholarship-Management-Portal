const API = {
  csrfToken: null,
  async _req(method, url, body, isForm) {
    const opts = { method, credentials: "include", headers: {} };
    if (method !== "GET" && method !== "HEAD" && this.csrfToken) {
      opts.headers["X-CSRF-Token"] = this.csrfToken;
    }
    if (body && !isForm) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    } else if (body && isForm) {
      opts.body = body;
    }
    const res = await fetch(url, opts);
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (data && data.csrf_token) this.csrfToken = data.csrf_token;
    if (!res.ok) {
      const err = new Error((data && data.error) || "Request failed");
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  },
  get(url) { return this._req("GET", url); },
  post(url, body) { return this._req("POST", url, body); },
  put(url, body) { return this._req("PUT", url, body); },
  del(url) { return this._req("DELETE", url); },
  postForm(url, formData) { return this._req("POST", url, formData, true); },
};
