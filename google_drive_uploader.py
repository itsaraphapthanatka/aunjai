"""
google_drive_uploader.py - อัปโหลดวิดีโอไป Google Drive และดึง shareable link
"""

import os
import logging
import json
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import GOOGLE_DRIVE_CREDENTIALS_FILE, GOOGLE_DRIVE_FOLDER_ID

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive']

def _get_or_create_folder(service, folder_name: str, parent_id: str) -> str:
    """
    ค้นหาหรือสร้างโฟลเดอร์ตามชื่อในโฟลเดอร์แม่ที่กำหนด
    """
    query = f"name = '{folder_name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    
    try:
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if files:
            # พบโฟลเดอร์เดิม
            return files[0]['id']
        else:
            # สร้างโฟลเดอร์ใหม่
            folder_metadata = {
                'name': folder_name,
                'parents': [parent_id],
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = service.files().create(body=folder_metadata, fields='id').execute()
            logger.info(f"📁 สร้างโฟลเดอร์ใหม่: {folder_name} (ID: {folder['id']})")
            return folder['id']
            
    except Exception as e:
        logger.error(f"❌ เกิดข้อผิดพลาดในการตรวจสอบ/สร้างโฟลเดอร์: {e}")
        return parent_id  # Fallback ไปที่ parent_id เดิม

def upload_local_file_to_drive(local_file_path: str, mime_type: str = 'video/mp4', video_id: str = None) -> str:
    """
    อัปโหลดไฟล์ไปที่ Google Drive ตาม Folder ID ที่ระบุ
    และคืนค่า WebViewLink (Shareable link)
    
    Args:
        local_file_path: path ของไฟล์ในเครื่อง
        mime_type: mimetype ของไฟล์
        video_id: (Optional) ถ้าระบุ จะอัปโหลดเข้าไปในโฟลเดอร์ชื่อ video_id นั้นๆ
    """
    if not GOOGLE_DRIVE_CREDENTIALS_FILE or not os.path.exists(GOOGLE_DRIVE_CREDENTIALS_FILE):
        logger.warning(f"⚠️ ไม่พบไฟล์ Credentials '{GOOGLE_DRIVE_CREDENTIALS_FILE}' สำหรับ Google Drive ข้ามการอัปโหลด")
        return ""
    
    if not os.path.exists(local_file_path):
        logger.error(f"❌ ไม่พบไฟล์ต้นฉบับ: {local_file_path}")
        return ""

    filename = os.path.basename(local_file_path)
    
    try:
        # ตรวจสอบประเภท Credentials จากไฟล์ JSON
        with open(GOOGLE_DRIVE_CREDENTIALS_FILE, 'r') as f:
            info = json.load(f)
        
        cred_type = info.get('type')
        
        if cred_type == 'service_account':
            logger.info("🔑 ใช้ Credentials ประเภท Service Account")
            creds = service_account.Credentials.from_service_account_file(
                GOOGLE_DRIVE_CREDENTIALS_FILE, scopes=SCOPES)
        else:
            logger.info("🔑 ใช้ Credentials ประเภท Authorized User")
            creds = Credentials.from_authorized_user_file(
                GOOGLE_DRIVE_CREDENTIALS_FILE, SCOPES)
            
        service = build('drive', 'v3', credentials=creds)

        # กำหนดโฟลเดอร์ปลายทาง
        target_folder_id = GOOGLE_DRIVE_FOLDER_ID
        if video_id:
            target_folder_id = _get_or_create_folder(service, video_id, GOOGLE_DRIVE_FOLDER_ID)

        file_metadata = {
            'name': filename,
            'parents': [target_folder_id]
        }
        media = MediaFileUpload(local_file_path, mimetype=mime_type, resumable=True)
        
        logger.info(f"📤 กำลังอัปโหลด {filename} ไปยัง Google Drive...")
        uploaded_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()

        file_id = uploaded_file.get('id')
        web_view_link = uploaded_file.get('webViewLink')

        # กำหนดสิทธิ์ให้ทุกคนที่มีลิ้งก์สามารถดูได้
        service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()

        logger.info(f"✅ อัปโหลดสำเร็จ: {web_view_link}")
        return web_view_link

    except Exception as e:
        logger.error(f"❌ เกิดข้อผิดพลาดในการอัปโหลดไป Google Drive: {e}")
        return ""
