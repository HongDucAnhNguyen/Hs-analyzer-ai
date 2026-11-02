"""Logfire configuration for crawl service to track token usage and costs"""
import os
import logfire
from dotenv import load_dotenv

load_dotenv()


def setup_logfire():
    """
    Configure Logfire for crawl service with Pydantic AI instrumentation.
    This will automatically track:
    - LLM token usage for query rewriting and reason generation
    - Cost per API call
    - Latency metrics
    - Message content (prompts and responses)
    """
    # Enable capturing of message content for LLM calls
    # This is CRITICAL for seeing prompts, responses, and costs
    os.environ['OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT'] = 'true'
    
    # Get Logfire token from environment variable
    logfire_token = os.getenv("LOGFIRE_TOKEN")
    
    if not logfire_token:
        print("⚠️ LOGFIRE_TOKEN not set in .env file. Logfire monitoring disabled.")
        print("   To enable monitoring, add LOGFIRE_TOKEN to your .env file")
        return
    
    environment = os.getenv("LOGFIRE_ENVIRONMENT", "production")
    
    try:
        # Configure Logfire
        logfire.configure(
            token=logfire_token,
            environment=environment,
            send_to_logfire='if-token-present',
            console=False  # Disable console logging to reduce noise
        )
        
        # Instrument Pydantic AI - this automatically tracks all LLM calls with costs!
        logfire.instrument_pydantic_ai()
        
        print("✅ Logfire configured for crawl service")
        print(f"📊 Environment: {environment}")
        print("📊 Pydantic AI instrumentation enabled")
        print("💰 Cost tracking enabled for crawl service LLM calls")
        
    except Exception as e:
        print(f"⚠️ Logfire setup failed for crawl service: {e}")
        print("Crawl service will continue without Logfire monitoring")
