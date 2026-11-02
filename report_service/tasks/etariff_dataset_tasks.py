"""Celery tasks for E-tariff dataset input processing."""

import asyncio
import logging
from typing import Any, Dict

from report_service.core.celery_app import celery_app
from shared.llm_error_utils import is_quota_error, quota_error_detail

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="report_service.tasks.process_etariff_dataset",
    time_limit=7200,       # 2 hours hard limit
    soft_time_limit=6600,  # 1h50m soft limit
)
def process_etariff_dataset_task(self, object_name: str) -> Dict[str, Any]:
	"""Process an uploaded dataset Excel file and return a download URL."""
	from report_service.services.etariff_dataset_processor import (
		build_output_excel,
		parse_dataset_rows,
		process_dataset_rows
	)
	from report_service.utils.minio_client import (
		download_file,
		upload_result_file,
		check_file_exists,
		is_minio_available
	)

	if not is_minio_available():
		raise RuntimeError("MinIO storage service is not available. Please start MinIO first.")

	if not check_file_exists(object_name):
		raise FileNotFoundError(f"File not found in storage: {object_name}")

	logger.info("Processing E-tariff dataset from MinIO: %s", object_name)
	content = download_file(object_name)
	if not content:
		raise ValueError("Empty file")

	rows = parse_dataset_rows(content, object_name)
	if not rows:
		raise ValueError("No valid data rows found in Excel file")

	total_rows = len(rows)

	def update_progress(current: int, total: int) -> None:
		self.update_state(
			state="PROGRESS",
			meta={
				"status": f"Processing row {current}/{total}",
				"current_step": "processing_rows",
				"rows_processed": current,
				"total_rows": total
			}
		)

	try:
		results = asyncio.run(process_dataset_rows(rows, update_progress))
	except Exception as exc:
		if is_quota_error(exc):
			message = quota_error_detail()
			logger.error("E-tariff dataset processing failed due to quota: %s", exc)
			raise RuntimeError(message) from exc
		raise

	self.update_state(
		state="PROGRESS",
		meta={
			"status": "Generating Excel output",
			"current_step": "building_excel",
			"rows_processed": total_rows,
			"total_rows": total_rows
		}
	)

	excel_content = build_output_excel(results, content)
	upload_result = upload_result_file(
		excel_content,
		object_name,
		suffix="_etariff_results"
	)

	logger.info("Uploaded E-tariff result file: %s", upload_result["object_name"])

	return {
		"status": "SUCCESS",
		"object_name": upload_result["object_name"],
		"download_url": upload_result["download_url"],
		"expires_in_seconds": upload_result["expires_in_seconds"],
		"message": f"Processed {total_rows} rows successfully"
	}
