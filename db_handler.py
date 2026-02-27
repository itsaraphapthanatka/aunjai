import psycopg2
from psycopg2.extras import execute_values
import logging
import os
from typing import Dict, Any, List

logger = logging.getLogger("MAAC-DB-Handler")

class DatabaseHandler:
    def __init__(self):
        self.conn_str = os.getenv("DATABASE_URL")
        # Example URL: "postgresql://user:password@localhost:5432/dbname"

    def _get_connection(self):
        return psycopg2.connect(self.conn_str)

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Contact Management
    # ─────────────────────────────────────────────────────────────────────────
    def upsert_contact(self, contact_data: Dict[str, Any]):
        """
        Upserts a contact into the 'contacts' table.
        """
        sql = """
        INSERT INTO contacts (
            line_uid, line_display_name, display_name, email, mobile, 
            customer_id, gender, birthday, status, created_at, updated_at
        ) VALUES (
            %(line_uid)s, %(line_display_name)s, %(display_name)s, %(email)s, %(mobile)s,
            %(customer_id)s, %(gender)s, %(birthday)s, %(status)s, %(created_at)s, %(updated_at)s
        )
        ON CONFLICT (line_uid) DO UPDATE SET
            line_display_name = EXCLUDED.line_display_name,
            display_name = EXCLUDED.display_name,
            email = EXCLUDED.email,
            mobile = EXCLUDED.mobile,
            customer_id = EXCLUDED.customer_id,
            status = EXCLUDED.status,
            updated_at = EXCLUDED.updated_at,
            last_synced_at = CURRENT_TIMESTAMP;
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, contact_data)

    def upsert_contact_tag_metadata(self, line_uid: str, tags: List[str], tags_detail: List[Dict[str, Any]]):
        """
        Stores the raw tags and tags_detail metadata for a contact.
        This is a simpler approach to store the requested nested data.
        """
        import json
        sql = """
        UPDATE contacts 
        SET tags = %s, tags_detail = %s, last_synced_at = CURRENT_TIMESTAMP
        WHERE line_uid = %s
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (json.dumps(tags), json.dumps(tags_detail), line_uid))

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Performance Tracking
    # ─────────────────────────────────────────────────────────────────────────
    def save_event_performance_total(self, performance_data: Dict[str, Any]):
        """
        Saves aggregated performance data.
        """
        sql = """
        INSERT INTO event_performance_total (
            event_id, report_start_date, report_end_date, opens, clicks, 
            unique_clicks, adds_to_cart, transactions, transaction_revenue
        ) VALUES (
            %(event_id)s, %(start_date)s, %(end_date)s, %(opens)s, %(clicks)s,
            %(unique_clicks)s, %(adds_to_cart)s, %(transactions)s, %(transaction_revenue)s
        );
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, performance_data)

    def upsert_message_event(self, event_data: Dict[str, Any]):
        """
        Upserts a message event (campaign).
        """
        sql = """
        INSERT INTO message_events (event_id, name, created_at)
        VALUES (%(id)s, %(name)s, CURRENT_TIMESTAMP)
        ON CONFLICT (event_id) DO UPDATE SET
            name = EXCLUDED.name,
            last_synced_at = CURRENT_TIMESTAMP;
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, event_data)

    def upsert_tags(self, tags: List[Dict[str, Any]]):
        """
        Upserts multiple tags.
        """
        sql = """
        INSERT INTO tags (tag_id, tag_name, available_days)
        VALUES %s
        ON CONFLICT (tag_id) DO UPDATE SET
            tag_name = EXCLUDED.tag_name,
            available_days = EXCLUDED.available_days;
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                execute_values(cur, sql, [(t['id'], t['name'], t.get('available_days')) for t in tags])

    def link_contact_tag(self, line_uid: str, tag_id: int):
        """
        Links a contact to a tag.
        """
        sql = """
        INSERT INTO contact_tags (line_uid, tag_id, tagged_at)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (line_uid, tag_id) DO NOTHING;
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (line_uid, tag_id))

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Dashboard Data Retrieval
    # ─────────────────────────────────────────────────────────────────────────
    def get_all_contacts(self, limit: int = 100, offset: int = 0, status: str = None, tag: str = None, search: str = None) -> Dict[str, Any]:
        """
        Retrieves paginated contact list with filtering and total count.
        """
        where_clauses = []
        params = []
        
        if status:
            where_clauses.append("status = %s")
            params.append(status)
        
        if tag:
            where_clauses.append("jsonb_exists(tags, %s)")
            params.append(tag)
            
        if search:
            search_pattern = f"%{search}%"
            where_clauses.append("(line_uid ILIKE %s OR line_display_name ILIKE %s OR display_name ILIKE %s OR email ILIKE %s OR mobile ILIKE %s)")
            params.extend([search_pattern] * 5)
            
        where_sql = ""
        if where_clauses:
            where_sql = " WHERE " + " AND ".join(where_clauses)
            
        count_sql = f"SELECT COUNT(*) FROM contacts{where_sql}"
        data_sql = f"SELECT * FROM contacts{where_sql} ORDER BY last_synced_at DESC LIMIT %s OFFSET %s"
        
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Get total count
                cur.execute(count_sql, params)
                total = cur.fetchone()['count']
                
                # Get paginated results
                data_params = params + [limit, offset]
                cur.execute(data_sql, data_params)
                results = [dict(row) for row in cur.fetchall()]
                
                # Convert JSON strings back to lists
                import json
                for row in results:
                    if row.get('tags'):
                        try:
                            row['tags'] = json.loads(row['tags']) if isinstance(row['tags'], str) else row['tags']
                        except: row['tags'] = []
                    if row.get('tags_detail'):
                        try:
                            row['tags_detail'] = json.loads(row['tags_detail']) if isinstance(row['tags_detail'], str) else row['tags_detail']
                        except: row['tags_detail'] = []
                
                return {
                    "total": total,
                    "contacts": results,
                    "limit": limit,
                    "offset": offset
                }

    def get_performance_summary(self) -> List[Dict[str, Any]]:
        """
        Retrieves latest performance data for all events.
        """
        sql = """
        SELECT e.name as event_name, p.* 
        FROM event_performance_total p
        JOIN message_events e ON p.event_id = e.event_id
        ORDER BY p.updated_at DESC LIMIT 20
        """
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                return [dict(row) for row in cur.fetchall()]

    def get_all_tags(self) -> List[str]:
        """
        Retrieves all unique tag names from the database.
        """
        sql = "SELECT tag_name FROM tags ORDER BY tag_name ASC"
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [row[0] for row in cur.fetchall()]
