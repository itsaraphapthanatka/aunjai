import hmac
import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
import requests
from dotenv import load_dotenv
from db_handler import DatabaseHandler

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MAAC-Middleware")

load_dotenv()

class MAACMiddleware:
    def __init__(self):
        self.db = DatabaseHandler()
        self._load_config()

    def _load_config(self):
        """Loads configuration from database, falling back to environment variables."""
        self.active_env = self.db.get_setting("maac_active_env", "production")
        
        # Determine base URL
        if self.active_env == "production":
            self.base_url = "https://api.cresclab.com"
            self.api_token = self.db.get_setting("maac_prod_api_token") or os.getenv("MAAC_API_TOKEN")
            self.webhook_secret = self.db.get_setting("maac_prod_webhook_secret") or os.getenv("MAAC_WEBHOOK_SECRET")
        elif self.active_env == "sandbox":
            self.base_url = "https://api.jp.cresclab.com"
            self.api_token = self.db.get_setting("maac_sandbox_api_token")
            self.webhook_secret = self.db.get_setting("maac_sandbox_webhook_secret")
        else: # custom
            self.base_url = self.db.get_setting("maac_custom_base_url")
            self.api_token = self.db.get_setting("maac_prod_api_token") # Fallback to prod token for custom if not specified otherwise
            self.webhook_secret = self.db.get_setting("maac_prod_webhook_secret")

        self.base_url = (self.base_url or "https://api.user360.cresclab.com").rstrip("/")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "User-Agent": "NongUnjai-Middleware/1.0"
        }

    def refresh_config(self):
        """Forces a reload of configuration from the database."""
        self._load_config()
        logger.info("MAAC Middleware configuration refreshed from database.")

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Webhook Verification
    # ─────────────────────────────────────────────────────────────────────────
    def verify_webhook_signature(self, body: str, signature: str) -> bool:
        """
        Verifies the HMAC-SHA256 signature from MAAC.
        As per cresclaben.apib documentation.
        """
        if not self.webhook_secret:
            logger.error("MAAC_WEBHOOK_SECRET not set")
            return False
            
        expected_signature = hmac.new(
            self.webhook_secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Member/Contact Syncing
    # ─────────────────────────────────────────────────────────────────────────
    def get_contacts(self, start_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves contact list from MAAC OpenAPI.
        """
        params = {}
        if start_token:
            params["start"] = start_token
            
        response = requests.get(
            f"{self.base_url}/openapi/v1/member/",
            headers=self.headers,
            params=params
        )
        if response.status_code != 200:
            logger.error(f"API Error {response.status_code} for {response.url}: {response.text}")
        response.raise_for_status()
        return response.json()

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Performance Syncing
    # ─────────────────────────────────────────────────────────────────────────
    def get_performance_report(self, event_id: int, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """
        Retrieves performance report for a specific event.
        """
        params = {}
        if start_date: params["start_date"] = start_date
        if end_date: params["end_date"] = end_date
        
        response = requests.get(
            f"{self.base_url}/openapi/v1/event/{event_id}/report/",
            headers=self.headers,
            params=params
        )
        if response.status_code != 200:
            logger.error(f"API Error {response.status_code} for {response.url}: {response.text}")
        response.raise_for_status()
        return response.json()

    def get_message_events(self, start_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves message event list from MAAC.
        """
        params = {}
        if start_token:
            params["start"] = start_token
            
        response = requests.get(
            f"{self.base_url}/openapi/v1/event/",
            headers=self.headers,
            params=params
        )
        if response.status_code != 200:
            logger.error(f"API Error {response.status_code} for {response.url}: {response.text}")
        response.raise_for_status()
        return response.json()

    def get_api_tags(self, start_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves tag list from MAAC OpenAPI.
        """
        params = {}
        if start_token:
            params["start"] = start_token
            
        response = requests.get(
            f"{self.base_url}/openapi/v1/tag/",
            headers=self.headers,
            params=params
        )
        if response.status_code != 200:
            logger.error(f"API Error {response.status_code} for {response.url}: {response.text}")
        response.raise_for_status()
        return response.json()

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Message Orchestration
    # ─────────────────────────────────────────────────────────────────────────
    def send_push_message(self, template_id: int, line_uid: str, event_id: Optional[int] = None, data_vars: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Sends a single push message via MAAC.
        """
        payload = {
            "template_id": template_id,
            "data": {
                "line_uid": line_uid,
                **(data_vars or {})
            }
        }
        if event_id:
            payload["event_id"] = event_id
            
        response = requests.post(
            f"{self.base_url}/openapi/v1/direct_message/push/",
            headers=self.headers,
            json=payload
        )
        if response.status_code not in [200, 201]:
            logger.error(f"API Error {response.status_code} for {response.url}: {response.text}")
        response.raise_for_status()
        return response.json()

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Sync Orchestration
    # ─────────────────────────────────────────────────────────────────────────
    def sync_all_contacts(self):
        """
        Syncs all contacts from MAAC to the local database.
        """
        logger.info("Starting Contact Sync...")
        next_token = None
        total_synced = 0
        
        while True:
            data = self.get_contacts(start_token=next_token)
            contacts = data.get("results", [])
            for contact in contacts:
                # Map API fields to DB fields if necessary
                # The API uses e.g. line_uid, display_name
                self.db.upsert_contact(contact)
                # Store tags metadata
                if 'tags' in contact or 'tags_detail' in contact:
                    self.db.upsert_contact_tag_metadata(
                        contact['line_uid'], 
                        contact.get('tags', []), 
                        contact.get('tags_detail', [])
                    )
                total_synced += 1
            
            next_token = data.get("next")
            if not next_token:
                break
        
        logger.info(f"Contact Sync Complete. Total synced: {total_synced}")

    def sync_all_events(self):
        """
        Syncs all message events from MAAC.
        """
        logger.info("Starting Message Event Sync...")
        next_token = None
        total_synced = 0
        
        while True:
            data = self.get_message_events(start_token=next_token)
            events = data.get("results", [])
            for event in events:
                self.db.upsert_message_event(event)
                # Auto-sync performance for each event discovered
                try:
                    self.sync_performance(event['id'])
                except Exception as e:
                    logger.warning(f"Could not sync performance for event {event['id']}: {e}")
                total_synced += 1
            
            next_token = data.get("next")
            if not next_token:
                break
        logger.info(f"Event Sync Complete. Total events: {total_synced}")

    def sync_all_tags(self):
        """
        Syncs all tags from MAAC to the local database.
        """
        logger.info("Starting Tag Sync...")
        next_token = None
        total_synced = 0
        
        while True:
            data = self.get_api_tags(start_token=next_token)
            tags = data.get("results", [])
            if tags:
                self.db.upsert_tags(tags)
                total_synced += len(tags)
            
            next_token = data.get("next")
            if not next_token:
                break
        
        logger.info(f"Tag Sync Complete. Total tags synced: {total_synced}")

    def sync_performance(self, event_id: int, start_date: str = None, end_date: str = None):
        """
        Syncs performance report for a specific event.
        """
        logger.info(f"Syncing performance for event {event_id}...")
        report_data = self.get_performance_report(event_id, start_date, end_date)
        
        # Flatten structure for DB upsert
        report_total = report_data.get("report", {}).get("total", {})
        report_total["event_id"] = event_id
        report_total["start_date"] = start_date
        report_total["end_date"] = end_date
        
        self.db.save_event_performance_total(report_total)
        logger.info(f"Performance Sync Complete for event {event_id}")

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Webhook Processing
    # ─────────────────────────────────────────────────────────────────────────
    def handle_webhook(self, payload: Dict[str, Any]):
        """
        Main entry point for processing verified webhook payloads.
        """
        topic = payload.get("topic")
        data = payload.get("data", {})
        
        logger.info(f"Processing webhook topic: {topic}")
        
        if topic == "pnp.status_updated":
            # Real-time status update for messages
            logger.info(f"Message status update: {data.get('status')}")
            # Potential enhancement: save to a message_logs table
            
        elif topic == "pnp.profile_updated":
            # Real-time member profile/binding update
            self.db.upsert_contact(data)
            logger.info(f"Contact profile updated via webhook: {data.get('line_uid')}")
            
        elif topic == "prize.points_added":
            logger.info(f"Points added for contact: {data.get('line_uid')}")
            
        else:
            logger.warning(f"Unhandled webhook topic: {topic}")

# Example Usage
if __name__ == "__main__":
    # This would be used by the background sync job or the webhook endpoint
    mw = MAACMiddleware()
    logger.info("MAAC Middleware Initialized")
