#!/usr/bin/env python3
import json
import os
import sys
from getpass import getpass
from passlib.hash import bcrypt

USERS_FILE = "data/users.json"

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    os.makedirs("data", exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def create_user():
    print("=" * 50)
    print("YTArchive - Create User")
    print("=" * 50)
    
    username = input("Username: ").strip()
    if not username:
        print("❌ Username cannot be empty")
        sys.exit(1)
    
    users = load_users()
    if username in users:
        print(f"❌ User '{username}' already exists")
        sys.exit(1)
    
    password = getpass("Password: ")
    password_confirm = getpass("Confirm password: ")
    
    if password != password_confirm:
        print("❌ Passwords don't match")
        sys.exit(1)
    
    if len(password) < 6:
        print("❌ Password must be at least 6 characters")
        sys.exit(1)
    
    password_hash = bcrypt.hash(password)
    
    users[username] = {
        "password_hash": password_hash,
        "created_at": str(__import__("datetime").datetime.now())
    }
    
    save_users(users)
    print(f"\n✅ User '{username}' created successfully!")
    print(f"You can now login at http://localhost:8000")

if __name__ == "__main__":
    create_user()