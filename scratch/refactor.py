import re

with open("frontend/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# Insert apiFetch
api_fetch_code = """let allDoctors = [];

let isRefreshing = false;
let refreshPromise = null;
async function apiFetch(url, options = {}) {
  let res = await fetch(url, options);
  if (res.status === 401 && !url.includes('/api/login') && !url.includes('/api/refresh') && !url.includes('/api/logout') && !url.includes('/api/register')) {
    if (!isRefreshing) {
      isRefreshing = true;
      refreshPromise = fetch('/api/refresh', { method: 'POST' }).then(async r => {
        if (r.ok) {
           const data = await r.json();
           token = data.token;
           return token;
        }
        throw new Error('Refresh failed');
      }).finally(() => {
        isRefreshing = false;
      });
    }
    
    try {
      await refreshPromise;
      if(options.headers && options.headers['Authorization']) {
         options.headers['Authorization'] = 'Bearer ' + token;
      }
      res = await fetch(url, options);
    } catch (e) {
      if (!url.includes('/api/me')) {
        doLogout();
      }
    }
  }
  return res;
}
"""

content = content.replace("let allDoctors = [];", api_fetch_code)

# Replace fetch calls
content = re.sub(r'await fetch\(', 'await apiFetch(', content)

# But we shouldn't replace the fetch calls INSIDE apiFetch itself!
content = content.replace("await apiFetch(url, options);", "await fetch(url, options);")
content = content.replace("apiFetch('/api/refresh'", "fetch('/api/refresh'")

with open("frontend/index.html", "w", encoding="utf-8") as f:
    f.write(content)

print("Done")
