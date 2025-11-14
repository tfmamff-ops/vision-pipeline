def get_report_replacements_and_image_paths(instance_id, user_comment):
    """
    Build the replacements dictionary and image path metadata used to fill the DOCX template.
    """
    replacements = {
        "{{instance_id}}": instance_id,
        "{{created_date}}": "2025/10/10",
        "{{created_time}}": "13:00:45",
        "{{requested_by_user_id}}": "user123",
        "{{requested_by_user_name}}": "Álvaro Morales",
        "{{requested_by_user_email}}": "alvaro.m@company.com",
        "{{requested_by_user_role}}": "Operator",
        "{{client_app_version}}": "1.5.2",
        "{{expected_prod_code}}": "PROD-ABC-456",
        "{{expected_prod_desc}}": "Paracetamol 500mg - Tablets",
        "{{expected_lot}}": "LOT-2025-09-001",
        "{{validation_lot_ok}}": "✔",
        "{{expected_exp_date}}": "2027/12/31",
        "{{validation_exp_date_ok}}": "✔",
        "{{expected_pack_date}}": "2025/09/20",
        "{{validation_pack_date_ok}}": "✘",
        "{{validation_barcode_detected_ok}}": "✘",
        "{{validation_barcode_legible_ok}}": "✔",
        "{{barcode_payload_decoded_value}}": "GS1-98765432101234",
        "{{barcode_payload_barcode_symbology}}": "DataMatrix",
        "{{input_container}}": "cont-in-2025",
        "{{input_blob_name}}": "input_001.jpg",
        "{{processed_image_container}}": "cont-proc-2025",
        "{{processed_image_blob_name}}": "processed_001.jpg",
        "{{ocr_overlay_container}}": "cont-ocr-2025",
        "{{ocr_overlay_blob_name}}": "ocr_overlay_001.png",
        "{{barcode_overlay_container}}": "cont-bar-2025",
        "{{barcode_overlay_blob_name}}": "barcode_overlay_001.png",
        "{{barcode_roi_container}}": "cont-roi-2025",
        "{{barcode_roi_blob_name}}": "barcode_roi_001.png",
        "{{VALOR_AND}}": "✔",
        "{{validation_barcode_ok}}": "✔",
        "{{validation_summary}}": "✘",
        "{{user_comment}}": user_comment,
        "{{report_container}}": "cont-report-2025",
        "{{report_blob_name}}": "report_001.docx",
    }

    image_paths = {
        "input_image": {
            "container": "input",
            "blobName": "uploads/0a0643fc-fd95-480f-94cc-459f21d03aeb.jpg",
            "resizePercentage": 40,
            "jpegQuality": 70,
            "widthCm": 10.0,
        },
        "processed_image": {
            "container": "output",
            "blobName": "final/ocr/processed/03de1e46-ede1-4354-a890-69b550c08c33.png",
            "resizePercentage": 40,
            "jpegQuality": 70,
            "widthCm": 10.0,
        },
        "ocr_overlay_image": {
            "container": "output",
            "blobName": "final/ocr/overlay/04f75521-4400-4d79-8e30-ded2952200a9.png",
            "resizePercentage": 40,
            "jpegQuality": 70,
            "widthCm": 10.0,
        },
        "barcode_overlay_image": {
            "container": "output",
            "blobName": "final/barcode/overlay/02d7cd2d-5913-4778-a7ea-b0093bb75f45.png",
            "resizePercentage": 40,
            "jpegQuality": 70,
            "widthCm": 7.0,
        },
        "barcode_roi_image": {
            "container": "output",
            "blobName": "final/barcode/roi/02d7cd2d-5913-4778-a7ea-b0093bb75f45.png",
            "resizePercentage": 40,
            "jpegQuality": 70,
            "widthCm": 7.0,
        },
    }

    return replacements, image_paths
