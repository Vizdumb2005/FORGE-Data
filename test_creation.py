import requests
import sys

BASE_URL = "http://localhost:8000/api/v1"

def register():
    url = f"{BASE_URL}/auth/register"
    data = {
        "email": "testuser_fix@example.com",
        "password": "StrongPassword123!@#",
        "full_name": "Test User"
    }
    print(f"Registering user: {data['email']}")
    resp = requests.post(url, json=data)
    if resp.status_code == 201:
        print("Registration successful")
        return True
    elif resp.status_code == 400 and "already registered" in resp.text:
        print("User already exists")
        return True
    else:
        print(f"Registration failed: {resp.status_code} {resp.text}")
        return False

def login():
    url = f"{BASE_URL}/auth/login"
    data = {
        "email": "testuser_fix@example.com",
        "password": "StrongPassword123!@#"
    }
    print("Logging in...")
    resp = requests.post(url, json=data)
    if resp.status_code == 200:
        print("Login successful")
        return resp.json()["access_token"]
    else:
        print(f"Login failed: {resp.status_code} {resp.text}")
        return None

def create_workspace(token):
    url = f"{BASE_URL}/workspaces/"
    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "name": "Test Workspace",
        "description": "Created via test script"
    }
    print("Creating workspace...")
    resp = requests.post(url, json=data, headers=headers)
    if resp.status_code == 201:
        print("Workspace created successfully!")
        print(resp.json())
        return True
    else:
        print(f"Workspace creation failed: {resp.status_code} {resp.text}")
        return False

if __name__ == "__main__":
    if register():
        token = login()
        if token:
            create_workspace(token)
