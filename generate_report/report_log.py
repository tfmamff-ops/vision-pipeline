import logging
import os

import bleach
import psycopg  # psycopg v3

logger = logging.getLogger(__name__)

POSTGRES_URL = os.environ["POSTGRES_URL"]


def insert_report_log(
    instance_id: str,
    user_comment: str,
    accepted: bool,
    container: str,
    pdf_blob_name: str,
    docx_blob_name: str,
) -> None:
    """Insert a row into vision.report_log with the data of the generated report."""

    # Sanitize the user comment using bleach
    sanitized_comment = bleach.clean(user_comment)

    try:
        with psycopg.connect(POSTGRES_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO vision.report_log (
                        instance_id,
                        user_comment,
                        accepted,
                        container,
                        pdf_blob_name,
                        docx_blob_name
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        instance_id,
                        sanitized_comment,
                        accepted,
                        container,
                        pdf_blob_name,
                        docx_blob_name,
                    ),
                )
                # The connection context auto-commits if no error occurs.
    except Exception as exc:
        logger.error(
            "error inserting into vision.report_log for %s: %s", instance_id, exc
        )
        raise
