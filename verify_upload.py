import requests
import json
import os

BASE_URL = "http://localhost:8000/api/v1"

def test_file_upload():
    # 0. Register a new student
    new_user = {
        "name": "Test Student Upload",
        "email": f"test_student_upload_{os.urandom(4).hex()}@test.com",
        "password": "password123",
        "role": "student",
        "phone_number": "1234567890"
    }
    requests.post(f"{BASE_URL}/auth/register", json=new_user)

    # 1. Login
    login_data = {"email": new_user["email"], "password": "password123"}
    resp = requests.post(f"{BASE_URL}/auth/login", json=login_data)
    if resp.status_code != 200:
        print(f"Login failed: {resp.text}")
        return
    
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create dummy files
    img_path = "test_img.png"
    pdf_path = "test_doc.pdf"
    with open(img_path, "wb") as f:
        f.write(b"fake image data")
    with open(pdf_path, "wb") as f:
        f.write(b"fake pdf data")

    # 3. Submit request with files
    data = {
        "title": "Verifying Uploads Final",
        "subject": "System Test",
        "description": "This is a test request with attachments.",
        "deadline": "2026-03-01T12:00:00Z"
    }
    
    # Open files and keep handles in a list for closing later
    file_handles = [open(img_path, "rb"), open(pdf_path, "rb")]
    files = [
        ("files", (os.path.basename(img_path), file_handles[0], "image/png")),
        ("files", (os.path.basename(pdf_path), file_handles[1], "application/pdf"))
    ]

    try:
        resp = requests.post(f"{BASE_URL}/requests/", headers=headers, data=data, files=files)
        
        if resp.status_code == 200:
            print("Success!")
            print(json.dumps(resp.json(), indent=2))
        else:
            print(f"Upload failed: {resp.status_code}")
            print(resp.text)
    finally:
        # Close handles
        for h in file_handles:
            h.close()
        # Cleanup
        if os.path.exists(img_path): os.remove(img_path)
        if os.path.exists(pdf_path): os.remove(pdf_path)

if __name__ == "__main__":
    test_file_upload()
