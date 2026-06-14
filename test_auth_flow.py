import requests

s = requests.Session()

# 1. Try to add without login
r = s.post('http://127.0.0.1:5003/api/watchlist', json={'code':'600519','name':'test','market':'cn'})
print('1. No login:', r.status_code, r.json().get('need_login'))

# 2. Login
r = s.post('http://127.0.0.1:5003/api/auth/login', json={'username':'test','password':'123456'})
print('2. Login:', r.status_code, r.json().get('success'))

# 3. Verify session
r = s.get('http://127.0.0.1:5003/api/auth/me')
print('3. Me:', r.status_code, r.json().get('logged_in'))

# 4. Add watchlist
r = s.post('http://127.0.0.1:5003/api/watchlist', json={'code':'000001','name':'pingan','market':'cn'})
print('4. Add wl:', r.status_code, r.json())

# 5. Get all
r = s.get('http://127.0.0.1:5003/api/watchlist')
items = r.json().get('items', [])
print('5. Total items:', len(items))

# 6. Force a new session (simulates browser without cookies)
s2 = requests.Session()
r = s2.post('http://127.0.0.1:5003/api/watchlist', json={'code':'000002','name':'test2','market':'cn'})
print('6. New session (no auth):', r.status_code, r.json().get('need_login'))
