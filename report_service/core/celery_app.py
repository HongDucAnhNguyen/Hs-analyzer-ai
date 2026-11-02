"""
Celery Application Configuration for Report Service
"""

import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

# Get Redis URL and RabbitMQ URL from environment or use defaults
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://admin:admin123@localhost:5672/")

# Create Celery app with RabbitMQ as broker and Redis as backend
celery_app = Celery(
    "report_service",
    broker=RABBITMQ_URL,
    backend=REDIS_URL,
    include=[
        "report_service.tasks.report_tasks",
        "report_service.tasks.etariff_dataset_tasks"
    ]
)

# Define queue for report service
REPORT_QUEUE = "report_queue"

# Configure Celery with better Redis connection handling
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=7200,       # 2 hours hard limit
    task_soft_time_limit=6600,  # 1h50m soft limit (graceful warning before hard kill)
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    
    # Task routing - send all report tasks to report_queue
    task_default_queue=REPORT_QUEUE,
    task_routes={
        'report_service.tasks.*': {'queue': REPORT_QUEUE},
    },
    
    # Redis broker settings for better reliability
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_pool_limit=10,
    
    # Result backend settings
    result_backend_transport_options={
        'socket_keepalive': True,
        'socket_keepalive_options': {},
        'socket_connect_timeout': 5,
        'socket_timeout': 5,
        'retry_on_timeout': True,
        'health_check_interval': 30,
    },
    
    # Broker transport options
    broker_transport_options={
        'socket_keepalive': True,
        'socket_keepalive_options': {},
        'socket_connect_timeout': 5,
        'socket_timeout': 5,
        'retry_on_timeout': True,
        'health_check_interval': 30,
        'visibility_timeout': 7200,  # 2 hours (must be >= task_time_limit)
    },
)

